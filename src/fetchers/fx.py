# src/fetchers/fx.py
"""Historical FX series + base-currency conversion (INVESTMENT_PLAN.md §6.5).

All portfolio risk/return math must use a single base currency (SGD by default)
so that FX risk is automatically captured in the covariance matrix and drawdowns.
This module fetches *historical* FX rates via yfinance and converts price
DataFrames from their listing currencies into the base currency.

Cache: data/cache/FX_{PAIR}_1d.csv  (same directory as HistoryFetcher)

GBp note
--------
London Stock Exchange prices for many ETFs (e.g. CSPX.L) are quoted in GBp
(pence), not GBP. yfinance returns the price in the *listing* currency.
To convert GBp → SGD:  price_sgd = (price_gbp_pence / 100) × GBPSGD_rate
Pass currency='GBp' in the currency_map and this is handled automatically.
"""

import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

from src import config

logger = logging.getLogger('portfolio_analyzer.fx')

# yfinance ticker format: {FROM}{TO}=X gives units of TO per 1 unit of FROM
# e.g. USDSGD=X → SGD per 1 USD
_YF_PAIR = "{from_}{to}=X"

# Currencies quoted in sub-units that need a /100 correction
_PENCE_CURRENCIES = {'GBp', 'GBX'}


class FXConverter:
    """
    Convert price DataFrames to a single base currency using historical FX rates.

    Args:
        base_currency: Target home currency (default from config: 'SGD').
        conversion_cost: Per-conversion cost fraction for trade-cost estimates (§6.5.2).
        cache_dir: Directory for cached FX CSV files (default: data/cache/).
        max_retries: yfinance retry attempts.
    """

    def __init__(
        self,
        base_currency: Optional[str] = None,
        conversion_cost: float = config.FX_CONVERSION_COST,
        cache_dir: Optional[str] = None,
        max_retries: int = 3,
    ):
        self.base_currency = base_currency or config.BASE_CURRENCY
        self.conversion_cost = conversion_cost
        self.max_retries = max_retries
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / 'data' / 'cache'
        self.cache_dir = Path(cache_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_fx_series(
        self,
        from_currency: str,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> pd.Series:
        """
        Historical daily FX rate: from_currency → base_currency.

        Fetches from cache if available; downloads and caches otherwise.
        GBp (pence) returns the GBP/base rate — callers divide price by 100.

        Args:
            from_currency: Source currency code (e.g. 'USD', 'TWD', 'GBp').
            start_date: 'YYYY-MM-DD'
            end_date: 'YYYY-MM-DD' (default: today)

        Returns:
            pd.Series indexed by date, values = base_currency per 1 from_currency.
            Empty Series on failure.
        """
        end_date = end_date or date.today().isoformat()

        # Treat GBp as GBP for the rate fetch; caller divides price by 100
        fetch_ccy = 'GBP' if from_currency in _PENCE_CURRENCIES else from_currency

        if fetch_ccy == self.base_currency:
            idx = pd.date_range(start_date, end_date, freq='B')
            return pd.Series(1.0, index=idx, name=f'{fetch_ccy}/{self.base_currency}')

        return self._fetch_with_cache(fetch_ccy, start_date, end_date)

    def to_base_currency(
        self,
        prices: pd.DataFrame,
        currency_map: Dict[str, str],
    ) -> pd.DataFrame:
        """
        Convert each column of prices to the base currency.

        Args:
            prices: DataFrame of close prices (dates × symbols), native currencies.
            currency_map: {symbol: currency_code} e.g. {'NVDA': 'USD', 'CSPX.L': 'GBp'}.

        Returns:
            DataFrame with same shape, all values in base_currency.
        """
        if prices.empty:
            return prices

        start = prices.index.min().strftime('%Y-%m-%d')
        end = prices.index.max().strftime('%Y-%m-%d')

        # Fetch FX series for each unique currency (cached per unique pair)
        fx_cache: Dict[str, pd.Series] = {}
        for ccy in set(currency_map.values()):
            fetch_ccy = 'GBP' if ccy in _PENCE_CURRENCIES else ccy
            if fetch_ccy == self.base_currency:
                continue
            if fetch_ccy not in fx_cache:
                fx_cache[fetch_ccy] = self._fetch_with_cache(fetch_ccy, start, end)

        result = prices.copy().astype(float)

        for symbol in prices.columns:
            ccy = currency_map.get(str(symbol), 'USD')
            fetch_ccy = 'GBP' if ccy in _PENCE_CURRENCIES else ccy
            is_pence = ccy in _PENCE_CURRENCIES

            if fetch_ccy == self.base_currency and not is_pence:
                continue  # already in base currency

            fx = fx_cache.get(fetch_ccy)
            if fx is None or fx.empty:
                logger.warning(
                    f"{symbol}: no FX rate for {fetch_ccy}→{self.base_currency}, "
                    "column left in native currency"
                )
                continue

            # Align FX series to the price index using forward-fill then back-fill
            fx_aligned = fx.reindex(prices.index, method='ffill').bfill()

            if is_pence:
                result[symbol] = prices[symbol] / 100.0 * fx_aligned
            else:
                result[symbol] = prices[symbol] * fx_aligned

        return result

    def conversion_drag(self, notional: float) -> float:
        """Estimated FX conversion cost on notional (§6.5.2 trade-cost model)."""
        return notional * self.conversion_cost

    # ------------------------------------------------------------------
    # Cache I/O
    # ------------------------------------------------------------------

    def _cache_path(self, from_ccy: str) -> Path:
        pair = f"{from_ccy}{self.base_currency}"
        return self.cache_dir / f"FX_{pair}_1d.csv"

    def _read_cache(self, from_ccy: str) -> pd.Series:
        path = self._cache_path(from_ccy)
        if not path.exists():
            return pd.Series(dtype=float)
        try:
            df = pd.read_csv(path, index_col='Date', parse_dates=True)
            series = df.iloc[:, 0].sort_index()
            series.name = f'{from_ccy}/{self.base_currency}'
            return series
        except Exception as e:
            logger.warning(f"FX cache read failed ({from_ccy}): {e}")
            return pd.Series(dtype=float)

    def _write_cache(self, from_ccy: str, series: pd.Series) -> None:
        path = self._cache_path(from_ccy)
        path.parent.mkdir(parents=True, exist_ok=True)
        df = series.to_frame(name='Rate')
        df.index.name = 'Date'
        df.to_csv(path)
        logger.info(f"FX cache written: {path} ({len(df)} rows)")

    # ------------------------------------------------------------------
    # Fetch + cache logic
    # ------------------------------------------------------------------

    def _fetch_with_cache(
        self, from_ccy: str, start_date: str, end_date: str
    ) -> pd.Series:
        """Read cache, fetch only missing dates, return merged series."""
        existing = self._read_cache(from_ccy)

        if existing.empty:
            fetch_from = start_date
        else:
            last = existing.index.max()
            if last.date() >= date.today() - timedelta(days=1):
                return existing.loc[start_date:end_date]
            fetch_from = (last - timedelta(days=1)).strftime('%Y-%m-%d')

        new = self._fetch_yfinance(from_ccy, fetch_from, end_date)

        if new is None or new.empty:
            return existing.loc[start_date:end_date] if not existing.empty else pd.Series(dtype=float)

        if existing.empty:
            combined = new
        else:
            combined = pd.concat([existing, new])
            combined = combined[~combined.index.duplicated(keep='last')].sort_index()

        self._write_cache(from_ccy, combined)
        return combined.loc[start_date:end_date]

    def _fetch_yfinance(
        self, from_ccy: str, start_date: str, end_date: str
    ) -> Optional[pd.Series]:
        """Download FX rate via yfinance. Returns None on failure."""
        ticker = _YF_PAIR.format(from_=from_ccy, to=self.base_currency)

        for attempt in range(self.max_retries):
            try:
                end_excl = (
                    pd.Timestamp(end_date) + pd.Timedelta(days=1)
                ).strftime('%Y-%m-%d')
                df = yf.Ticker(ticker).history(
                    start=start_date, end=end_excl, interval='1d', auto_adjust=True
                )
                if df.empty:
                    logger.warning(f"FX: yfinance returned empty for {ticker}")
                    return None

                series = df['Close'].copy()
                series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
                series = series.dropna().sort_index()
                series.name = f'{from_ccy}/{self.base_currency}'
                logger.info(f"FX: fetched {ticker} — {len(series)} rows ({start_date}→{end_date})")
                return series

            except Exception as e:
                logger.error(f"FX fetch {ticker} attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(min(1.0 * (2 ** attempt), 30.0))

        return None
