# src/analyzers/__init__.py
"""Portfolio analysis modules.

- ``risk_metrics``  : per-asset risk / risk-return metrics (volatility, Sharpe, beta…)
- ``portfolio``     : weighted whole-portfolio metrics (σ=√(wᵀΣw), risk contribution…)  [stub]
- ``allocation``    : weighting engines (equal, inverse-vol, risk parity, min-var…)      [stub]
"""

from .risk_metrics import RiskMetrics
from .portfolio import PortfolioMetrics
from .allocation import AllocationEngine

# Backward-compatible alias (the class was formerly named PortfolioAnalyzer).
PortfolioAnalyzer = RiskMetrics

__all__ = ['RiskMetrics', 'PortfolioMetrics', 'AllocationEngine', 'PortfolioAnalyzer']
