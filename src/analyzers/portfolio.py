# src/analyzers/portfolio.py
"""Weighted whole-portfolio metrics (INVESTMENT_PLAN.md §6.2).

All return series must be in the base currency (SGD) before being passed here
— use FXConverter.to_base_currency() first. See INVESTMENT_PLAN.md §6.5.

Core metrics implemented:
  covariance_matrix       Annualized Σ
  portfolio_volatility    σₚ = √(wᵀ Σ w)
  risk_contribution       Per-holding share of total risk (sums to σₚ)
  diversification_ratio   (Σ wᵢσᵢ) / σₚ  — 1.0 = zero benefit
  effective_number_of_bets  1 / Σ wᵢ²
  portfolio_sharpe        (μₚ − rf) / σₚ  (annualised)
  portfolio_sortino       (μₚ − rf) / downside_σₚ
  max_drawdown            Worst peak-to-trough on portfolio price series
  currency_exposure       Weight aggregated by listing currency (§6.5.1)
  summary                 All of the above in one call
"""

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger('portfolio_analyzer.portfolio')


class PortfolioMetrics:
    """
    Compute risk/return metrics for a *weighted basket* of assets.

    Args:
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino (default 4%).
        trading_days: Periods per year for annualisation (252 daily, 52 weekly).
    """

    def __init__(self, risk_free_rate: float = 0.04, trading_days: int = 252):
        self.risk_free_rate = risk_free_rate
        self.trading_days = trading_days

    # ------------------------------------------------------------------
    # Core building blocks
    # ------------------------------------------------------------------

    def covariance_matrix(
        self, returns: pd.DataFrame, annualize: bool = True
    ) -> pd.DataFrame:
        """
        Annualized covariance matrix Σ from a returns DataFrame.

        Args:
            returns: DataFrame of period returns (dates × assets).
            annualize: Multiply by trading_days to annualize (default True).

        Returns:
            Square DataFrame with same index/columns as returns.columns.
        """
        cov = returns.cov()
        if annualize:
            cov = cov * self.trading_days
        return cov

    def portfolio_volatility(
        self, weights: pd.Series, cov: pd.DataFrame
    ) -> float:
        """
        Portfolio volatility σₚ = √(wᵀ Σ w).

        Args:
            weights: Asset weights (need not sum to 1; will be used as-is).
            cov: Annualized covariance matrix (from covariance_matrix()).

        Returns:
            Annualized portfolio volatility as a fraction (e.g. 0.15 = 15%).
        """
        w = _align_weights(weights, cov.columns)
        variance = float(w @ cov.values @ w)
        return float(np.sqrt(max(variance, 0.0)))

    def risk_contribution(
        self, weights: pd.Series, cov: pd.DataFrame
    ) -> pd.Series:
        """
        Each holding's absolute contribution to portfolio risk (sums to σₚ).

        Marginal contribution to risk: MCRᵢ = (Σw)ᵢ / σₚ
        Risk contribution:             RCᵢ  = wᵢ × MCRᵢ

        Args:
            weights: Asset weights.
            cov: Annualized covariance matrix.

        Returns:
            Series of risk contributions indexed by asset name.
        """
        w = _align_weights(weights, cov.columns)
        sigma = self.portfolio_volatility(weights, cov)
        if sigma == 0:
            return pd.Series(0.0, index=cov.columns, name='risk_contribution')
        mcr = cov.values @ w / sigma
        rc = w * mcr
        return pd.Series(rc, index=cov.columns, name='risk_contribution')

    def risk_contribution_pct(
        self, weights: pd.Series, cov: pd.DataFrame
    ) -> pd.Series:
        """Risk contribution as % of total portfolio risk (sums to 100%)."""
        rc = self.risk_contribution(weights, cov)
        sigma = rc.sum()
        return (rc / sigma * 100).rename('risk_contribution_pct') if sigma else rc

    def diversification_ratio(
        self, weights: pd.Series, returns: pd.DataFrame
    ) -> float:
        """
        Diversification ratio = (Σ wᵢσᵢ) / σₚ.

        1.0 means no diversification benefit (all assets perfectly correlated).
        Higher is better.
        """
        vols = returns.std() * np.sqrt(self.trading_days)
        w = _align_weights(weights, returns.columns)
        weighted_vol_sum = float(w @ vols.reindex(returns.columns).fillna(0).values)
        cov = self.covariance_matrix(returns)
        sigma = self.portfolio_volatility(weights, cov)
        return float(weighted_vol_sum / sigma) if sigma > 0 else 1.0

    def effective_number_of_bets(self, weights: pd.Series) -> float:
        """
        1 / Σ wᵢ² — how many independent positions the portfolio effectively holds.

        Equal-weight N-asset portfolio → ENB = N.
        Concentrated portfolio → ENB → 1.
        """
        w = weights.dropna()
        w = w[w > 0]
        sq_sum = float((w ** 2).sum())
        return float(1.0 / sq_sum) if sq_sum > 0 else 0.0

    # ------------------------------------------------------------------
    # Return-based metrics
    # ------------------------------------------------------------------

    def portfolio_returns(
        self, weights: pd.Series, returns: pd.DataFrame
    ) -> pd.Series:
        """Weighted portfolio return series."""
        w = weights.reindex(returns.columns).fillna(0)
        return (returns * w).sum(axis=1)

    def portfolio_sharpe(
        self,
        weights: pd.Series,
        returns: pd.DataFrame,
        risk_free_rate: Optional[float] = None,
    ) -> float:
        """Annualized Sharpe ratio of the weighted portfolio."""
        rfr = risk_free_rate if risk_free_rate is not None else self.risk_free_rate
        port_ret = self.portfolio_returns(weights, returns)
        ann_return = float(port_ret.mean() * self.trading_days)
        cov = self.covariance_matrix(returns)
        sigma = self.portfolio_volatility(weights, cov)
        return float((ann_return - rfr) / sigma) if sigma > 0 else 0.0

    def portfolio_sortino(
        self,
        weights: pd.Series,
        returns: pd.DataFrame,
        risk_free_rate: Optional[float] = None,
    ) -> float:
        """Annualized Sortino ratio (uses downside deviation only)."""
        rfr = risk_free_rate if risk_free_rate is not None else self.risk_free_rate
        port_ret = self.portfolio_returns(weights, returns)
        ann_return = float(port_ret.mean() * self.trading_days)
        downside = port_ret[port_ret < 0]
        downside_vol = float(downside.std() * np.sqrt(self.trading_days)) if len(downside) > 1 else 0.0
        return float((ann_return - rfr) / downside_vol) if downside_vol > 0 else 0.0

    def max_drawdown(
        self, weights: pd.Series, prices: pd.DataFrame
    ) -> float:
        """
        Maximum portfolio drawdown over the price history.

        Args:
            weights: Asset weights.
            prices: Price DataFrame (dates × assets) in base currency.

        Returns:
            Most negative fraction (e.g. -0.35 = worst peak-to-trough was -35%).
        """
        w = weights.reindex(prices.columns).fillna(0)
        port_value = (prices * w).sum(axis=1)
        rolling_max = port_value.cummax()
        drawdown = (port_value - rolling_max) / rolling_max
        return float(drawdown.min())

    # ------------------------------------------------------------------
    # Portfolio composition
    # ------------------------------------------------------------------

    def currency_exposure(
        self, weights: pd.Series, currency_map: Dict[str, str]
    ) -> pd.Series:
        """
        Portfolio weight aggregated by listing currency (INVESTMENT_PLAN.md §6.5.1).

        Args:
            weights: Asset weights.
            currency_map: {symbol: currency_code}, e.g. {'NVDA': 'USD', '2330.TW': 'TWD'}.

        Returns:
            Series {currency: total_weight}, sorted descending.
        """
        exposure: Dict[str, float] = {}
        for symbol, weight in weights.items():
            ccy = currency_map.get(str(symbol), 'USD')
            exposure[ccy] = exposure.get(ccy, 0.0) + float(weight)
        return pd.Series(exposure, name='currency_exposure').sort_values(ascending=False)

    # ------------------------------------------------------------------
    # One-call summary (§8 monthly workflow)
    # ------------------------------------------------------------------

    def summary(
        self,
        weights: pd.Series,
        returns: pd.DataFrame,
        prices: Optional[pd.DataFrame] = None,
        currency_map: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        Full portfolio risk report for the §8 monthly workflow.

        Args:
            weights: Asset weights (fractions, should sum to ~1).
            returns: Period returns in base currency (from FXConverter).
            prices: Optional price DataFrame for drawdown calculation.
            currency_map: Optional {symbol: currency} for FX exposure report.

        Returns:
            Dict with all portfolio metrics.
        """
        cov = self.covariance_matrix(returns)
        sigma = self.portfolio_volatility(weights, cov)
        rc = self.risk_contribution(weights, cov)
        rc_pct = self.risk_contribution_pct(weights, cov)
        dr = self.diversification_ratio(weights, returns)
        enb = self.effective_number_of_bets(weights)
        sharpe = self.portfolio_sharpe(weights, returns)
        sortino = self.portfolio_sortino(weights, returns)

        result: Dict = {
            'portfolio_volatility':     round(sigma, 6),
            'diversification_ratio':    round(dr, 4),
            'effective_number_of_bets': round(enb, 2),
            'portfolio_sharpe':         round(sharpe, 4),
            'portfolio_sortino':        round(sortino, 4),
            'risk_contribution':        rc,
            'risk_contribution_pct':    rc_pct,
        }

        if prices is not None:
            result['max_drawdown'] = round(self.max_drawdown(weights, prices), 6)

        if currency_map is not None:
            result['currency_exposure'] = self.currency_exposure(weights, currency_map)

        logger.info(
            f"Portfolio summary: σ={sigma:.2%} DR={dr:.2f} ENB={enb:.1f} "
            f"Sharpe={sharpe:.2f}"
        )
        return result


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _align_weights(weights: pd.Series, columns: pd.Index) -> np.ndarray:
    """Align weights to covariance matrix columns, filling missing with 0."""
    return weights.reindex(columns).fillna(0.0).values.astype(float)
