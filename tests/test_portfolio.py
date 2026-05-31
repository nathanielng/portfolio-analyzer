# tests/test_portfolio.py
"""Contract stubs for weighted portfolio metrics (analyzers.portfolio).

These document the intended API. They assert the current stub behavior
(NotImplementedError) and should be fleshed out into real assertions when the
math lands — see INVESTMENT_PLAN.md §6.2 / §11.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.analyzers import PortfolioMetrics


def test_portfolio_metrics_constructs():
    pm = PortfolioMetrics(risk_free_rate=0.04)
    assert pm.risk_free_rate == 0.04


def test_portfolio_volatility_not_yet_implemented():
    pm = PortfolioMetrics()
    with pytest.raises(NotImplementedError):
        pm.portfolio_volatility(pd.Series(dtype=float), pd.DataFrame())
