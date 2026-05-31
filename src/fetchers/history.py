# src/fetchers/history.py
"""Bulk historical OHLC fetching (INVESTMENT_PLAN.md §11).

STUB — structure only. This will replace the per-date loop currently living in
``analyzers.risk_metrics.RiskMetrics.fetch_historical_data``, which calls
``fetch_price`` once per symbol per day (N×M API calls). yfinance/Polygon can
bulk-download a full date range in one request, so this module centralizes
efficient historical retrieval as a proper fetcher concern.
"""

import logging
from typing import List, Optional

import pandas as pd

logger = logging.getLogger('portfolio_analyzer.history')

_NOT_IMPLEMENTED = (
    "Not implemented yet — structural stub. Migrate the bulk-fetch logic here "
    "from risk_metrics.fetch_historical_data. See INVESTMENT_PLAN.md §11."
)


class HistoryFetcher:
    """Fetch aligned historical close prices for many symbols in one shot."""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def fetch(
        self,
        symbols: List[str],
        start_date: str,
        end_date: Optional[str] = None,
        interval: str = 'daily',
    ) -> pd.DataFrame:
        """Return a DataFrame of close prices (dates × symbols)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)
