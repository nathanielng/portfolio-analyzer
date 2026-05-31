# src/fetchers/fx.py
"""Historical FX + base-currency conversion (INVESTMENT_PLAN.md §6.5).

STUB — structure only. The plan requires all return/risk math to be computed in
the investor's BASE currency (SGD) so that FX risk is automatically captured.
This module fetches *historical* FX series (yfinance ``<PAIR>=X`` or FRED
``DEXSGUS``) and converts a price DataFrame from listing currencies into the
base currency before it reaches the §6 portfolio math.

This complements ``utils.currency_converter.CurrencyConverter``, which only
handles *spot* conversion (and defaults to USD).
"""

import logging
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger('portfolio_analyzer.fx')

_NOT_IMPLEMENTED = (
    "Not implemented yet — structural stub. See INVESTMENT_PLAN.md §6.5 and §11."
)


class FXConverter:
    """
    Convert price series into a single base currency using historical FX rates.

    Args:
        base_currency: Target/home currency for all returns (default 'SGD').
        conversion_cost: Per-conversion cost as a fraction, for trade-cost models (§6.5.2).
    """

    def __init__(self, base_currency: str = 'SGD', conversion_cost: float = 0.002):
        self.base_currency = base_currency
        self.conversion_cost = conversion_cost

    def fetch_fx_series(
        self, from_currency: str, start_date: str, end_date: Optional[str] = None
    ) -> pd.Series:
        """Historical FX rate (from_currency → base_currency) indexed by date."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def to_base_currency(
        self, prices: pd.DataFrame, currency_map: Dict[str, str]
    ) -> pd.DataFrame:
        """Convert each column of `prices` to the base currency via aligned FX series."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def conversion_drag(self, notional: float) -> float:
        """Estimated FX cost on converting `notional` (for rebalancing math, §6.5.2)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)
