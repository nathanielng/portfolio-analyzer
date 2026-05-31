# src/fetchers/macro.py
"""Macro-factor data: rates, oil, inflation, sentiment (INVESTMENT_PLAN.md §6.5 / §3).

STUB — structure only. Pulls a small macro-regime dashboard used as *context*
(not as a trade signal, see §6.5.5):

    - Interest rates : FRED DGS10, DGS2, FEDFUNDS, T10Y2Y  (discount-rate / regime)
    - Commodities    : FRED DCOILWTICO / DCOILBRENTEU       (inflation context)
    - Inflation      : FRED CPIAUCSL
    - Sentiment      : yfinance ^VIX                         (risk-off gauge)

FRED requires a free API key (FRED_API_KEY); the series endpoints are otherwise
open. Follows the repo's exponential-backoff convention.
"""

import logging
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger('portfolio_analyzer.macro')

_NOT_IMPLEMENTED = (
    "Not implemented yet — structural stub. See INVESTMENT_PLAN.md §6.5 and §11."
)


class MacroFetcher:
    """Fetch macro indicators and summarize the current regime."""

    def __init__(self, fred_api_key: Optional[str] = None, max_retries: int = 3):
        self.fred_api_key = fred_api_key
        self.max_retries = max_retries

    def fetch_series(self, series_id: str, start_date: str, end_date: Optional[str] = None) -> pd.Series:
        """Fetch a single FRED series by ID."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def risk_free_rate(self) -> float:
        """Latest 10Y Treasury yield (DGS10) — risk-free input for DCF/Sharpe."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def regime_dashboard(self) -> Dict:
        """Snapshot: rates trend, USD/SGD, inflation, oil, VIX (§8 step 1)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)
