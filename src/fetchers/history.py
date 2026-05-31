# src/fetchers/history.py
"""Bulk historical OHLCV fetching with append-only CSV cache.

Design
------
- One cache file per (symbol, interval): ``data/cache/{SYMBOL}_{interval}.csv``
- Append-only: on each call, read the existing cache, find the last cached date,
  fetch only missing trading days from yfinance, append, dedup, and save.
- Historical closes are immutable once a trading day ends, so only the most
  recent (potentially intraday-incomplete) bar needs re-fetching. We handle
  this by always re-fetching the last cached day on update.
- Returns prices in the *native listing currency* (e.g. TWD for 2330.TW,
  GBp for CSPX.L on LSE). Currency conversion to SGD base happens at the
  portfolio-math layer (FXConverter / daily_report).

Granularity guide (see INVESTMENT_PLAN.md §3)
---------------------------------------------
  ≤ 5 years  →  ``1d``  (daily, ~252 rows/yr)   — preserves all signal
  > 5 years  →  ``1wk`` (weekly, ~52 rows/yr)   — manageable file size

Standard presets (used by scripts/fetch_history.py):
  7d, 1m, 3m, 1y, ytd, 5y   → interval ``1d``
  max (~10y)                 → interval ``1wk``

Note on CSPX.L / LSE listings: yfinance returns GBp (pence) for UK equities;
currency will show as 'GBp'. Divide by 100 to get GBP if needed downstream.
"""

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

logger = logging.getLogger('portfolio_analyzer.history')

# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

@dataclass
class Preset:
    label: str
    interval: str       # yfinance interval string: '1d', '1wk', '1mo'
    days: Optional[int] = None   # calendar days back from today
    ytd: bool = False            # if True, start = Jan 1 of current year


PRESETS: Dict[str, Preset] = {
    '7d':  Preset('7 days',      interval='1d',  days=7),
    '1m':  Preset('1 month',     interval='1d',  days=30),
    '3m':  Preset('3 months',    interval='1d',  days=90),
    '1y':  Preset('1 year',      interval='1d',  days=365),
    'ytd': Preset('Year-to-date', interval='1d', ytd=True),
    '5y':  Preset('5 years',     interval='1d',  days=1825),
    'max': Preset('Max (~10y)',   interval='1wk', days=3650),
}

_INTERVAL_MAP = {
    'daily': '1d', 'weekly': '1wk', 'monthly': '1mo',
    '1d': '1d', '1wk': '1wk', '1mo': '1mo',
}


# ---------------------------------------------------------------------------
# HistoryFetcher
# ---------------------------------------------------------------------------

class HistoryFetcher:
    """
    Fetch and cache bulk historical OHLCV data for a list of symbols.

    Args:
        cache_dir: Directory for CSV cache files (default: ``data/cache``
                   relative to the project root).
        max_retries: Retry attempts per symbol on network failure.
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        max_retries: int = 3,
    ):
        if cache_dir is None:
            # Locate project root (two levels up from this file)
            cache_dir = Path(__file__).parent.parent.parent / 'data' / 'cache'
        self.cache_dir = Path(cache_dir)
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        symbols: List[str],
        start_date: str,
        end_date: Optional[str] = None,
        interval: str = '1d',
    ) -> pd.DataFrame:
        """
        Return a wide DataFrame of adjusted close prices (dates × symbols).

        Pulls from cache where available; fetches and caches missing dates.
        This is the entry point for portfolio-math code (correlation matrices,
        risk metrics, etc.) that previously used the per-day loop in
        ``RiskMetrics.fetch_historical_data``.

        Args:
            symbols: List of ticker symbols.
            start_date: 'YYYY-MM-DD'
            end_date: 'YYYY-MM-DD' (default: today)
            interval: '1d' / '1wk' / '1mo'  (or 'daily' / 'weekly')

        Returns:
            DataFrame with DatetimeIndex and one column per symbol.
            Missing symbols are silently omitted if fetch fails entirely.
        """
        interval = _INTERVAL_MAP.get(interval, interval)
        end_date = end_date or date.today().isoformat()

        frames: Dict[str, pd.Series] = {}
        for symbol in symbols:
            df, _, _ = self.update_cache(symbol, interval, start_date, end_date)
            if df is not None and not df.empty:
                series = df['Close'].copy()
                series = series[series.index >= pd.Timestamp(start_date)]
                series = series[series.index <= pd.Timestamp(end_date)]
                frames[symbol] = series

        if not frames:
            return pd.DataFrame()

        wide = pd.DataFrame(frames)
        wide.index = pd.to_datetime(wide.index)
        wide.sort_index(inplace=True)
        return wide

    def fetch_preset(self, symbols: List[str], preset: str) -> pd.DataFrame:
        """Convenience wrapper — fetch using a named preset (e.g. '1y', '5y')."""
        p = PRESETS[preset]
        start, end, interval = _preset_dates(p)
        return self.fetch(symbols, start, end, interval)

    def update_cache(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> Tuple[Optional[pd.DataFrame], int, int]:
        """
        Update the cache for one (symbol, interval), fetching only missing dates.

        Returns:
            (full_df, cached_rows, fetched_rows)
            full_df covers start_date..end_date from cache + new fetch combined.
        """
        interval = _INTERVAL_MAP.get(interval, interval)
        end_date = end_date or date.today().isoformat()

        existing = self._read_cache(symbol, interval)
        cached_rows = len(existing)

        # Determine what to fetch
        if existing.empty:
            fetch_from = start_date
        else:
            first_cached = existing.index.min()
            last_cached  = existing.index.max()

            # Back-fill: cache doesn't reach back far enough for the requested range
            needs_backfill = first_cached.date() > pd.Timestamp(start_date).date()

            if needs_backfill:
                # Fetch from requested start to end, merge with existing
                fetch_from = start_date
                logger.info(f"{symbol} {interval}: back-filling {start_date} → {first_cached.date()}")
            elif last_cached.date() >= date.today() - timedelta(days=1):
                # Cache is fully up to date — nothing to fetch
                logger.info(f"{symbol} {interval}: cache up to date ({last_cached.date()})")
                return _slice(existing, start_date, end_date), cached_rows, 0
            else:
                # Normal forward append: re-fetch last bar in case it was intraday
                fetch_from = (last_cached - timedelta(days=1)).strftime('%Y-%m-%d')

        logger.info(f"{symbol} {interval}: fetching {fetch_from} → {end_date}")
        new_df = self._fetch_yfinance(symbol, fetch_from, end_date, interval)

        if new_df is None:
            return _slice(existing, start_date, end_date) if not existing.empty else None, cached_rows, 0

        # Merge: concat existing + new, dedup on index (keep last = newest data)
        if existing.empty:
            combined = new_df
        else:
            combined = pd.concat([existing, new_df])
            combined = combined[~combined.index.duplicated(keep='last')]
            combined.sort_index(inplace=True)

        fetched_rows = len(new_df)
        self._write_cache(symbol, interval, combined)

        return _slice(combined, start_date, end_date), cached_rows, fetched_rows

    # ------------------------------------------------------------------
    # Cache I/O
    # ------------------------------------------------------------------

    def cache_path(self, symbol: str, interval: str) -> Path:
        safe_symbol = symbol.replace('/', '_').replace('\\', '_')
        return self.cache_dir / f"{safe_symbol}_{interval}.csv"

    def cache_info(self, symbol: str, interval: str) -> Optional[Dict]:
        """Return {'rows', 'start', 'end'} for a cached file, or None."""
        path = self.cache_path(symbol, interval)
        if not path.exists():
            return None
        df = self._read_cache(symbol, interval)
        if df.empty:
            return None
        return {
            'rows': len(df),
            'start': df.index.min().date().isoformat(),
            'end': df.index.max().date().isoformat(),
            'path': str(path),
        }

    def _read_cache(self, symbol: str, interval: str) -> pd.DataFrame:
        path = self.cache_path(symbol, interval)
        if not path.exists():
            return pd.DataFrame()
        try:
            df = pd.read_csv(path, index_col='Date', parse_dates=True)
            df.sort_index(inplace=True)
            return df
        except Exception as e:
            logger.warning(f"Cache read failed for {symbol}/{interval}: {e}")
            return pd.DataFrame()

    def _write_cache(self, symbol: str, interval: str, df: pd.DataFrame) -> None:
        path = self.cache_path(symbol, interval)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.index.name = 'Date'
        df.to_csv(path)
        logger.info(f"Cache written: {path} ({len(df)} rows)")

    # ------------------------------------------------------------------
    # yfinance fetch (single symbol, bulk)
    # ------------------------------------------------------------------

    def _fetch_yfinance(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str,
    ) -> Optional[pd.DataFrame]:
        for attempt in range(self.max_retries):
            try:
                ticker = yf.Ticker(symbol)
                # end date is exclusive in yfinance — add one day
                end_exclusive = (
                    datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                ).strftime('%Y-%m-%d')
                df = ticker.history(
                    start=start_date,
                    end=end_exclusive,
                    interval=interval,
                    auto_adjust=True,   # adjusted close in 'Close' column
                )
                if df.empty:
                    logger.warning(f"{symbol}: yfinance returned empty DataFrame")
                    return None

                # Normalise index to timezone-naive date
                df.index = pd.to_datetime(df.index).tz_localize(None)
                df.index = df.index.normalize()  # strip time component

                # Keep standard OHLCV columns only
                keep = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df.columns]
                df = df[keep]
                df.dropna(subset=['Close'], inplace=True)

                logger.info(f"{symbol} {interval}: fetched {len(df)} rows ({start_date}→{end_date})")
                return df

            except Exception as e:
                logger.error(f"{symbol} fetch attempt {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    delay = min(1.0 * (2 ** attempt), 30.0)
                    time.sleep(delay)

        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preset_dates(p: Preset) -> Tuple[str, str, str]:
    """Return (start_date, end_date, interval) for a Preset."""
    today = date.today()
    end = today.isoformat()
    if p.ytd:
        start = date(today.year, 1, 1).isoformat()
    else:
        start = (today - timedelta(days=p.days)).isoformat()
    return start, end, p.interval


def _slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
    return df.loc[mask]
