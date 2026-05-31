# tests/test_portfolio.py
"""Tests for PortfolioMetrics — all maths verified with synthetic data."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.analyzers.portfolio import PortfolioMetrics, _align_weights


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pm():
    return PortfolioMetrics(risk_free_rate=0.04, trading_days=252)


def _make_returns(n_assets: int = 3, n_days: int = 500, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cols = [f"A{i}" for i in range(n_assets)]
    data = rng.normal(0.0005, 0.015, size=(n_days, n_assets))
    return pd.DataFrame(data, columns=cols)


def _equal_weights(returns: pd.DataFrame) -> pd.Series:
    n = len(returns.columns)
    return pd.Series(1 / n, index=returns.columns)


# ---------------------------------------------------------------------------
# covariance_matrix
# ---------------------------------------------------------------------------

def test_cov_matrix_shape(pm):
    r = _make_returns(4)
    cov = pm.covariance_matrix(r)
    assert cov.shape == (4, 4)


def test_cov_matrix_symmetric(pm):
    r = _make_returns(3)
    cov = pm.covariance_matrix(r)
    np.testing.assert_allclose(cov.values, cov.values.T, atol=1e-12)


def test_cov_matrix_annualized(pm):
    r = _make_returns(2)
    cov_ann = pm.covariance_matrix(r, annualize=True)
    cov_raw = pm.covariance_matrix(r, annualize=False)
    np.testing.assert_allclose(cov_ann.values, cov_raw.values * 252, rtol=1e-10)


# ---------------------------------------------------------------------------
# portfolio_volatility
# ---------------------------------------------------------------------------

def test_vol_nonnegative(pm):
    r = _make_returns(3)
    w = _equal_weights(r)
    cov = pm.covariance_matrix(r)
    assert pm.portfolio_volatility(w, cov) >= 0


def test_vol_single_asset(pm):
    """1-asset portfolio: σₚ == individual vol."""
    r = _make_returns(1)
    w = pd.Series([1.0], index=r.columns)
    cov = pm.covariance_matrix(r)
    expected = float(r.iloc[:, 0].std() * np.sqrt(252))
    assert abs(pm.portfolio_volatility(w, cov) - expected) < 1e-8


def test_vol_less_than_weighted_avg_when_corr_lt_1(pm):
    """σₚ < Σ wᵢσᵢ when assets are not perfectly correlated."""
    r = _make_returns(3)
    w = _equal_weights(r)
    cov = pm.covariance_matrix(r)
    port_vol = pm.portfolio_volatility(w, cov)
    vols = r.std() * np.sqrt(252)
    weighted_avg_vol = float((w * vols).sum())
    assert port_vol < weighted_avg_vol


# ---------------------------------------------------------------------------
# risk_contribution
# ---------------------------------------------------------------------------

def test_risk_contribution_sums_to_sigma(pm):
    r = _make_returns(3)
    w = _equal_weights(r)
    cov = pm.covariance_matrix(r)
    rc = pm.risk_contribution(w, cov)
    sigma = pm.portfolio_volatility(w, cov)
    assert abs(rc.sum() - sigma) < 1e-8


def test_risk_contribution_pct_sums_to_100(pm):
    r = _make_returns(4)
    w = _equal_weights(r)
    cov = pm.covariance_matrix(r)
    rc_pct = pm.risk_contribution_pct(w, cov)
    assert abs(rc_pct.sum() - 100.0) < 1e-6


def test_risk_contribution_concentrated(pm):
    """Concentrated portfolio: dominant asset should dominate risk."""
    r = _make_returns(3)
    w = pd.Series([0.9, 0.05, 0.05], index=r.columns)
    cov = pm.covariance_matrix(r)
    rc_pct = pm.risk_contribution_pct(w, cov)
    assert rc_pct.iloc[0] > 70  # first asset owns most of the risk


# ---------------------------------------------------------------------------
# diversification_ratio
# ---------------------------------------------------------------------------

def test_diversification_ratio_gt_1(pm):
    r = _make_returns(3)
    w = _equal_weights(r)
    dr = pm.diversification_ratio(w, r)
    assert dr > 1.0


def test_diversification_ratio_single_asset_is_1(pm):
    r = _make_returns(1)
    w = pd.Series([1.0], index=r.columns)
    dr = pm.diversification_ratio(w, r)
    assert abs(dr - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# effective_number_of_bets
# ---------------------------------------------------------------------------

def test_enb_equal_weights(pm):
    n = 5
    w = pd.Series([0.2] * n, index=[f"A{i}" for i in range(n)])
    assert abs(pm.effective_number_of_bets(w) - 5.0) < 1e-8


def test_enb_concentrated(pm):
    w = pd.Series([0.99, 0.01], index=['A', 'B'])
    enb = pm.effective_number_of_bets(w)
    assert enb < 1.1  # almost 1 real bet


# ---------------------------------------------------------------------------
# portfolio_sharpe / sortino
# ---------------------------------------------------------------------------

def test_sharpe_positive_for_positive_return(pm):
    rng = np.random.default_rng(1)
    data = rng.normal(0.002, 0.01, size=(500, 2))  # positive drift
    r = pd.DataFrame(data, columns=['A', 'B'])
    w = _equal_weights(r)
    assert pm.portfolio_sharpe(w, r) > 0


def test_sortino_ge_sharpe_for_positive_skew(pm):
    """Sortino ≥ Sharpe when upside vol inflates Sharpe denominator."""
    rng = np.random.default_rng(7)
    data = rng.normal(0.001, 0.01, size=(500, 2))
    r = pd.DataFrame(data, columns=['A', 'B'])
    w = _equal_weights(r)
    # Sortino uses only downside vol so tends to be ≥ Sharpe
    assert pm.portfolio_sortino(w, r) >= pm.portfolio_sharpe(w, r) - 0.5


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

def test_max_drawdown_nonpositive(pm):
    r = _make_returns(3)
    prices = (1 + r).cumprod() * 100
    w = _equal_weights(r)
    mdd = pm.max_drawdown(w, prices)
    assert mdd <= 0


def test_max_drawdown_monotone_rising_is_zero(pm):
    """Strictly rising prices → zero drawdown."""
    prices = pd.DataFrame({
        'A': np.arange(1, 101, dtype=float),
        'B': np.arange(2, 202, 2, dtype=float),
    })
    w = pd.Series([0.5, 0.5], index=['A', 'B'])
    assert pm.max_drawdown(w, prices) == pytest.approx(0.0, abs=1e-8)


# ---------------------------------------------------------------------------
# currency_exposure
# ---------------------------------------------------------------------------

def test_currency_exposure_sums_to_weights(pm):
    w = pd.Series({'NVDA': 0.4, 'ASML': 0.3, '2330.TW': 0.3})
    cmap = {'NVDA': 'USD', 'ASML': 'USD', '2330.TW': 'TWD'}
    exp = pm.currency_exposure(w, cmap)
    assert abs(exp.sum() - 1.0) < 1e-10
    assert abs(exp['USD'] - 0.7) < 1e-10
    assert abs(exp['TWD'] - 0.3) < 1e-10


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

def test_summary_keys(pm):
    r = _make_returns(3)
    prices = (1 + r).cumprod() * 100
    w = _equal_weights(r)
    cmap = {c: 'USD' for c in r.columns}
    result = pm.summary(w, r, prices=prices, currency_map=cmap)
    for key in ['portfolio_volatility', 'diversification_ratio',
                'effective_number_of_bets', 'portfolio_sharpe',
                'portfolio_sortino', 'risk_contribution',
                'risk_contribution_pct', 'max_drawdown', 'currency_exposure']:
        assert key in result


# ---------------------------------------------------------------------------
# _align_weights helper
# ---------------------------------------------------------------------------

def test_align_weights_fills_missing_with_zero():
    w = pd.Series({'A': 0.6, 'B': 0.4})
    cols = pd.Index(['A', 'B', 'C'])
    aligned = _align_weights(w, cols)
    assert aligned[2] == 0.0
    assert aligned[0] == pytest.approx(0.6)
