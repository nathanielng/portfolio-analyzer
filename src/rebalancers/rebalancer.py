# src/rebalancers/rebalancer.py
"""Band-based rebalancing → suggested trades (INVESTMENT_PLAN.md §7).

STUB — structure only. Compares current vs target weights, flags holdings that
have drifted beyond the rebalance band (±5pp), and proposes trades —
contributions-first to avoid FX churn (§6.5.2 / §7). Enforces the single-name
and AI/semi caps from ``config``.
"""

import logging
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger('portfolio_analyzer.rebalancer')

_NOT_IMPLEMENTED = (
    "Not implemented yet — structural stub. See INVESTMENT_PLAN.md §7 and §11."
)


class Rebalancer:
    """
    Generate rebalancing trades from current holdings and target weights.

    Args:
        band: Drift threshold (in weight fraction) that triggers a rebalance (default 0.05 = ±5pp).
        fx_conversion_cost: Per-conversion FX cost fraction for the trade-cost estimate.
    """

    def __init__(self, band: float = 0.05, fx_conversion_cost: float = 0.002):
        self.band = band
        self.fx_conversion_cost = fx_conversion_cost

    def drift(self, current_weights: pd.Series, target_weights: pd.Series) -> pd.Series:
        """Per-holding deviation (current − target), in weight fraction."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def proposed_trades(
        self,
        current_weights: pd.Series,
        target_weights: pd.Series,
        portfolio_value: float,
        new_contribution: float = 0.0,
    ) -> pd.DataFrame:
        """Trades to bring drifted holdings back within band (contributions-first)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)
