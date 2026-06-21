# src/fetchers/dividends.py
"""Dividend history fetching with a per-symbol CSV cache.

yfinance exposes the full dividend record via ``Ticker.dividends`` — a Series of
dividend-per-share amounts indexed by ex-date, in the stock's listing currency.

Cache: data/cache/{SYMBOL}_div.csv  (Date, Dividend). Refreshed if older than
``ttl_hours`` (dividends are announced periodically, so daily is plenty). On a
network failure we fall back to the cached copy.

Amounts are in the LISTING currency (SGD for .SI, USD for US stocks). Convert to
the base currency at the portfolio layer (FXConverter / the dividends script).
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger('portfolio_analyzer.dividends')


class DividendFetcher:
    """Fetch and cache per-share dividend history for symbols."""

    def __init__(self, cache_dir: Optional[str] = None, ttl_hours: float = 24.0,
                 max_retries: int = 3):
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / 'data' / 'cache'
        self.cache_dir = Path(cache_dir)
        self.ttl_hours = ttl_hours
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    def cache_path(self, symbol: str) -> Path:
        safe = symbol.replace('/', '_').replace('\\', '_')
        return self.cache_dir / f"{safe}_div.csv"

    def fetch(self, symbol: str) -> pd.Series:
        """
        Return a Series of dividend-per-share by ex-date (listing currency).
        Empty Series for non-payers or on total failure.
        """
        path = self.cache_path(symbol)

        # Fresh cache → use it
        if path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600.0
            if age_h <= self.ttl_hours:
                return self._read(path)

        # Otherwise fetch fresh
        series = self._fetch_yf(symbol)
        if series is not None:
            self._write(path, series)
            return series

        # Network failed → fall back to any cached copy
        if path.exists():
            logger.warning(f"{symbol}: dividend fetch failed, using stale cache")
            return self._read(path)
        return pd.Series(dtype=float, name='Dividend')

    def fetch_many(self, symbols: List[str], delay: float = 0.2) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        for i, sym in enumerate(symbols):
            if i > 0:
                time.sleep(delay)
            out[sym] = self.fetch(sym)
        return out

    # ------------------------------------------------------------------
    def _fetch_yf(self, symbol: str) -> Optional[pd.Series]:
        for attempt in range(self.max_retries):
            try:
                div = yf.Ticker(symbol).dividends
                if div is None:
                    return pd.Series(dtype=float, name='Dividend')
                div = div.copy()
                div.index = pd.to_datetime(div.index).tz_localize(None).normalize()
                div.name = 'Dividend'
                logger.info(f"{symbol}: {len(div)} dividend records")
                return div
            except Exception as e:
                logger.error(f"{symbol} dividend fetch attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(min(1.0 * (2 ** attempt), 20.0))
        return None

    def _read(self, path: Path) -> pd.Series:
        try:
            df = pd.read_csv(path, index_col='Date', parse_dates=True)
            s = df['Dividend'].sort_index()
            s.name = 'Dividend'
            return s
        except Exception as e:
            logger.warning(f"Dividend cache read failed ({path.name}): {e}")
            return pd.Series(dtype=float, name='Dividend')

    def _write(self, path: Path, series: pd.Series) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        df = series.to_frame('Dividend')
        df.index.name = 'Date'
        df.to_csv(path)
        logger.info(f"Dividend cache written: {path} ({len(df)} rows)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def trailing_12m(series: pd.Series, asof: Optional[datetime] = None) -> float:
    """Sum of dividends-per-share over the trailing 12 months."""
    if series is None or series.empty:
        return 0.0
    asof = asof or datetime.now()
    cutoff = pd.Timestamp(asof) - pd.Timedelta(days=365)
    return float(series[series.index >= cutoff].sum())


def received_since(series: pd.Series, since: datetime, until: Optional[datetime] = None) -> float:
    """Sum of dividends-per-share with ex-date in [since, until]."""
    if series is None or series.empty:
        return 0.0
    lo = pd.Timestamp(since)
    hi = pd.Timestamp(until or datetime.now())
    mask = (series.index >= lo) & (series.index <= hi)
    return float(series[mask].sum())
