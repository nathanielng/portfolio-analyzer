# tests/test_risk_metrics.py
"""Smoke tests for the existing per-asset RiskMetrics (renamed from PortfolioAnalyzer)."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.analyzers import PortfolioAnalyzer, RiskMetrics


@pytest.fixture
def prices():
    """Two synthetic price series over 60 business days."""
    dates = pd.date_range('2025-01-01', periods=60, freq='B')
    rng = np.random.default_rng(42)
    a = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, len(dates)))
    b = 50 * np.cumprod(1 + rng.normal(0.0003, 0.02, len(dates)))
    return pd.DataFrame({'AAA': a, 'BBB': b}, index=dates)


def test_backward_compat_alias():
    assert PortfolioAnalyzer is RiskMetrics


def test_returns_and_correlation(prices):
    rm = RiskMetrics(risk_free_rate=0.04)
    returns = rm.calculate_returns(prices)
    assert list(returns.columns) == ['AAA', 'BBB']
    assert len(returns) == len(prices) - 1  # one row dropped by pct_change

    corr = rm.calculate_correlation_matrix(returns)
    assert corr.shape == (2, 2)
    assert corr.loc['AAA', 'AAA'] == pytest.approx(1.0)


def test_volatility_and_ratios(prices):
    rm = RiskMetrics(risk_free_rate=0.04)
    returns = rm.calculate_returns(prices)

    vol = rm.calculate_volatility(returns)
    assert (vol > 0).all()
    # BBB was generated with higher daily vol than AAA
    assert vol['BBB'] > vol['AAA']

    sharpe = rm.calculate_sharpe_ratio(returns)
    assert set(sharpe.index) == {'AAA', 'BBB'}


def test_max_drawdown_non_positive(prices):
    rm = RiskMetrics()
    mdd = rm.calculate_max_drawdown(prices)
    assert (mdd <= 0).all()
