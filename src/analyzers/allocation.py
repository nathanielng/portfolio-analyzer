# src/analyzers/allocation.py
"""Portfolio weighting engines (INVESTMENT_PLAN.md §6.3).

STUB — structure only. Implements (in a follow-up) the allocation methods,
simplest → most complex, each honoring the exposure caps in ``config`` (§1):

    equal_weight  → inverse_volatility → risk_parity → min_variance → max_sharpe

The plan's recommendation for this investor is equal-weight or risk-parity
within the satellite, subject to hard caps — NOT unconstrained mean-variance,
which tends to over-concentrate (§6.3, "the honest take").
"""

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger('portfolio_analyzer.allocation')

_NOT_IMPLEMENTED = (
    "Not implemented yet — structural stub. See INVESTMENT_PLAN.md §6.3 and §11."
)


class AllocationEngine:
    """
    Produce target weights for a basket of assets.

    Args:
        single_name_cap: Max weight for any single holding (default from config, 8%).
        ai_semi_cap: Max aggregate AI/semi exposure (default from config, 40%).
    """

    def __init__(self, single_name_cap: float = 0.08, ai_semi_cap: float = 0.40):
        self.single_name_cap = single_name_cap
        self.ai_semi_cap = ai_semi_cap

    def equal_weight(self, symbols: List[str]) -> pd.Series:
        """1/N across all names."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def inverse_volatility(self, returns: pd.DataFrame) -> pd.Series:
        """Weight ∝ 1/σ (correlation-blind risk weighting)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def risk_parity(self, returns: pd.DataFrame) -> pd.Series:
        """Equal risk contribution from each holding (needs covariance)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def min_variance(self, returns: pd.DataFrame) -> pd.Series:
        """Weights minimizing portfolio variance (scipy.optimize)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def max_sharpe(self, returns: pd.DataFrame, risk_free_rate: float = 0.04) -> pd.Series:
        """Tangency portfolio. FRAGILE — see §6.3 caveats; use as diagnostic only."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def efficient_frontier(self, returns: pd.DataFrame, n_points: int = 50) -> pd.DataFrame:
        """Risk/return points along the frontier (diagnostic plot)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def apply_caps(self, weights: pd.Series, ai_semi_flags: Optional[pd.Series] = None) -> pd.Series:
        """Clip weights to the single-name and AI/semi caps, then renormalize (§1)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)
