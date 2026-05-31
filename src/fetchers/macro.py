# src/fetchers/macro.py
"""Macro-factor data: rates, oil, inflation, sentiment (INVESTMENT_PLAN.md §6.5 / §3).

Pulls a macro-regime dashboard used as context (not as a trade signal, §6.5.5):

    - Interest rates : FRED DGS10, DGS2, FEDFUNDS, T10Y2Y  (discount-rate / regime)
    - Commodities    : FRED DCOILWTICO                       (inflation context)
    - Inflation      : FRED CPIAUCSL
    - Sentiment      : yfinance ^VIX                         (risk-off gauge)

FRED CSV endpoint works without an API key. If FRED_API_KEY is set the JSON
API is used instead (higher rate limits). Follows the repo's exponential-backoff
convention.
"""

import logging
import time
from typing import Dict, Optional

import pandas as pd
import requests

logger = logging.getLogger('portfolio_analyzer.macro')

_FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_FRED_API = "https://api.stlouisfed.org/fred/series/observations"

_SERIES = {
    'DGS10':      '10Y Treasury yield (%)',
    'DGS2':       '2Y Treasury yield (%)',
    'FEDFUNDS':   'Fed funds rate (%)',
    'T10Y2Y':     '10Y-2Y spread (bp)',
    'DCOILWTICO': 'WTI crude oil ($/bbl)',
    'CPIAUCSL':   'CPI (index)',
}


class MacroFetcher:
    """Fetch macro indicators and summarize the current regime."""

    def __init__(self, fred_api_key: Optional[str] = None, max_retries: int = 3):
        self.fred_api_key = fred_api_key
        self.max_retries = max_retries

    def fetch_series(self, series_id: str, start_date: str, end_date: Optional[str] = None) -> pd.Series:
        """
        Fetch a single FRED series by ID.

        Args:
            series_id: FRED series identifier (e.g. 'DGS10').
            start_date: Start date 'YYYY-MM-DD'.
            end_date: End date 'YYYY-MM-DD', defaults to today.

        Returns:
            pd.Series indexed by date (datetime), values as floats. Empty on failure.
        """
        for attempt in range(self.max_retries):
            try:
                if self.fred_api_key:
                    data = self._fetch_api(series_id, start_date, end_date)
                else:
                    data = self._fetch_csv(series_id, start_date, end_date)
                return data
            except Exception as e:
                logger.error(f"FRED {series_id} attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    delay = min(1.0 * (2 ** attempt), 60.0)
                    logger.info(f"Backing off {delay:.1f}s")
                    time.sleep(delay)
        return pd.Series(dtype=float)

    def _fetch_csv(self, series_id: str, start_date: str, end_date: Optional[str]) -> pd.Series:
        params = {'id': series_id}
        resp = requests.get(_FRED_CSV, params=params, timeout=15)
        resp.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text), parse_dates=['observation_date'], index_col='observation_date')
        df = df.replace('.', float('nan')).astype(float)
        series = df.iloc[:, 0].dropna()
        series.index = pd.to_datetime(series.index)
        mask = series.index >= pd.Timestamp(start_date)
        if end_date:
            mask &= series.index <= pd.Timestamp(end_date)
        return series[mask]

    def _fetch_api(self, series_id: str, start_date: str, end_date: Optional[str]) -> pd.Series:
        params = {
            'series_id': series_id,
            'api_key': self.fred_api_key,
            'file_type': 'json',
            'observation_start': start_date,
        }
        if end_date:
            params['observation_end'] = end_date
        resp = requests.get(_FRED_API, params=params, timeout=15)
        resp.raise_for_status()
        obs = resp.json().get('observations', [])
        dates, values = [], []
        for o in obs:
            try:
                values.append(float(o['value']))
                dates.append(pd.Timestamp(o['date']))
            except (ValueError, KeyError):
                pass  # '.' sentinel for missing data
        return pd.Series(values, index=dates, dtype=float)

    def latest(self, series_id: str) -> Optional[float]:
        """Return the most recent non-null value for a FRED series."""
        from datetime import date, timedelta
        start = (date.today() - timedelta(days=90)).strftime('%Y-%m-%d')
        s = self.fetch_series(series_id, start_date=start)
        return float(s.iloc[-1]) if not s.empty else None

    def risk_free_rate(self) -> Optional[float]:
        """Latest 10Y Treasury yield (DGS10) as a decimal — risk-free input for DCF/Sharpe."""
        val = self.latest('DGS10')
        return val / 100.0 if val is not None else None

    def regime_dashboard(self) -> Dict:
        """
        Snapshot of macro regime indicators.

        Returns:
            Dict with keys: dgs10, dgs2, spread_10y2y, fedfunds, wti, cpi, vix.
            Values are floats (latest available) or None on fetch failure.
        """
        dgs10 = self.latest('DGS10')
        dgs2 = self.latest('DGS2')

        # T10Y2Y is pre-computed by FRED; also derive it locally as a cross-check
        spread_fred = self.latest('T10Y2Y')
        spread_derived = (dgs10 - dgs2) if (dgs10 is not None and dgs2 is not None) else None
        spread = spread_fred if spread_fred is not None else spread_derived

        vix = self._fetch_vix()

        dashboard = {
            'dgs10':        dgs10,
            'dgs2':         dgs2,
            'spread_10y2y': spread,
            'inverted':     (spread < 0) if spread is not None else None,
            'fedfunds':     self.latest('FEDFUNDS'),
            'wti':          self.latest('DCOILWTICO'),
            'cpi':          self.latest('CPIAUCSL'),
            'vix':          vix,
        }
        logger.info(f"Macro dashboard: {dashboard}")
        return dashboard

    def _fetch_vix(self) -> Optional[float]:
        try:
            import yfinance as yf
            hist = yf.Ticker('^VIX').history(period='5d')
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception as e:
            logger.warning(f"VIX fetch failed: {e}")
        return None
