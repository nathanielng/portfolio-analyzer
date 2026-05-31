# src/analyzers/portfolio.py
"""Weighted whole-portfolio metrics (INVESTMENT_PLAN.md §6.2).

STUB — structure only. The actual math (covariance, σₚ = √(wᵀΣw), risk
contribution, diversification ratio, effective number of bets, portfolio
Sharpe) is implemented in a follow-up.

All return series passed in are expected to already be expressed in the base
currency (SGD) — see ``fetchers.fx`` and INVESTMENT_PLAN.md §6.5.
"""

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger('portfolio_analyzer.portfolio')

_NOT_IMPLEMENTED = (
    "Not implemented yet — structural stub. See INVESTMENT_PLAN.md §6.2 and §11."
)


class PortfolioMetrics:
    """
    Compute risk/return metrics for a *weighted basket* of assets.

    Args:
        risk_free_rate: Annual risk-free rate used for the portfolio Sharpe ratio.
        trading_days: Periods per year for annualization (252 daily / 52 weekly).
    """

    def __init__(self, risk_free_rate: float = 0.04, trading_days: int = 252):
        self.risk_free_rate = risk_free_rate
        self.trading_days = trading_days

    def covariance_matrix(self, returns: pd.DataFrame, annualize: bool = True) -> pd.DataFrame:
        """Annualized covariance matrix Σ from a returns DataFrame."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def portfolio_volatility(self, weights: pd.Series, cov: pd.DataFrame) -> float:
        """Portfolio volatility σₚ = √(wᵀ Σ w)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def risk_contribution(self, weights: pd.Series, cov: pd.DataFrame) -> pd.Series:
        """Each holding's contribution to total portfolio risk (sums to σₚ)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def diversification_ratio(self, weights: pd.Series, returns: pd.DataFrame) -> float:
        """(Σ wᵢσᵢ) / σₚ — ~1.0 means no diversification benefit."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def effective_number_of_bets(self, weights: pd.Series) -> float:
        """1 / Σ wᵢ² — how many independent positions you effectively hold."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def portfolio_sharpe(self, weights: pd.Series, returns: pd.DataFrame) -> float:
        """Sharpe ratio of the weighted portfolio."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def currency_exposure(
        self, weights: pd.Series, currency_map: Dict[str, str]
    ) -> pd.Series:
        """% of portfolio by currency of listing (INVESTMENT_PLAN.md §6.5.1)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def summary(
        self, weights: pd.Series, returns: pd.DataFrame, prices: Optional[pd.DataFrame] = None
    ) -> Dict:
        """One-call portfolio report used by the monthly workflow (§8)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)
