# tests/test_fx.py
"""Tests for FXConverter — cache logic and currency conversion."""

import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.fetchers.fx import FXConverter


@pytest.fixture
def tmp_fx(tmp_path):
    return FXConverter(base_currency='SGD', cache_dir=str(tmp_path))


def _make_prices(symbols, n=60, base=100.0, seed=1):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2025-01-01', periods=n, freq='B')
    data = {s: base * np.cumprod(1 + rng.normal(0.0003, 0.01, n)) for s in symbols}
    return pd.DataFrame(data, index=dates)


def _make_fx_series(n=60, rate=1.35, seed=2):
    """Synthetic USDSGD series."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2025-01-01', periods=n, freq='B')
    rates = rate + rng.normal(0, 0.005, n).cumsum()
    return pd.Series(rates, index=dates, name='USD/SGD')


# ---------------------------------------------------------------------------
# Conversion cost
# ---------------------------------------------------------------------------

def test_conversion_drag(tmp_fx):
    assert tmp_fx.conversion_drag(10_000) == pytest.approx(20.0)  # 0.002 × 10000


# ---------------------------------------------------------------------------
# to_base_currency — same-currency passthrough
# ---------------------------------------------------------------------------

def test_to_base_currency_sgd_passthrough(tmp_fx):
    prices = _make_prices(['A', 'B'])
    cmap = {'A': 'SGD', 'B': 'SGD'}
    result = tmp_fx.to_base_currency(prices, cmap)
    pd.testing.assert_frame_equal(result, prices.astype(float))


def test_to_base_currency_empty(tmp_fx):
    result = tmp_fx.to_base_currency(pd.DataFrame(), {})
    assert result.empty


# ---------------------------------------------------------------------------
# to_base_currency — USD conversion (monkeypatched)
# ---------------------------------------------------------------------------

def test_to_base_currency_usd(tmp_fx, monkeypatch):
    prices = _make_prices(['NVDA'])
    fx = _make_fx_series(n=len(prices))

    monkeypatch.setattr(tmp_fx, '_fetch_with_cache', lambda ccy, s, e: fx)
    cmap = {'NVDA': 'USD'}
    result = tmp_fx.to_base_currency(prices, cmap)

    expected = prices['NVDA'] * fx
    pd.testing.assert_series_equal(result['NVDA'], expected, check_names=False, rtol=1e-6)


# ---------------------------------------------------------------------------
# to_base_currency — GBp (pence) conversion
# ---------------------------------------------------------------------------

def test_to_base_currency_gbp_pence(tmp_fx, monkeypatch):
    """GBp prices should be divided by 100 before applying GBP/SGD rate."""
    prices = _make_prices(['CSPX.L'], base=82000)  # ~820 GBP in pence
    fx = _make_fx_series(n=len(prices), rate=1.68)  # GBPSGD

    monkeypatch.setattr(tmp_fx, '_fetch_with_cache', lambda ccy, s, e: fx)
    cmap = {'CSPX.L': 'GBp'}
    result = tmp_fx.to_base_currency(prices, cmap)

    expected = prices['CSPX.L'] / 100.0 * fx
    pd.testing.assert_series_equal(result['CSPX.L'], expected, check_names=False, rtol=1e-6)


# ---------------------------------------------------------------------------
# to_base_currency — mixed currencies
# ---------------------------------------------------------------------------

def test_to_base_currency_mixed(tmp_fx, monkeypatch):
    prices = _make_prices(['A', 'B', 'C'])
    usd_fx = _make_fx_series(n=len(prices), rate=1.35)
    twd_fx = _make_fx_series(n=len(prices), rate=0.042, seed=3)

    def mock_fetch(ccy, s, e):
        return usd_fx if ccy == 'USD' else twd_fx

    monkeypatch.setattr(tmp_fx, '_fetch_with_cache', mock_fetch)
    cmap = {'A': 'USD', 'B': 'TWD', 'C': 'SGD'}
    result = tmp_fx.to_base_currency(prices, cmap)

    pd.testing.assert_series_equal(result['A'], prices['A'] * usd_fx, check_names=False, rtol=1e-6)
    pd.testing.assert_series_equal(result['B'], prices['B'] * twd_fx, check_names=False, rtol=1e-6)
    pd.testing.assert_series_equal(result['C'], prices['C'].astype(float), check_names=False)


# ---------------------------------------------------------------------------
# fetch_fx_series — identity for base currency
# ---------------------------------------------------------------------------

def test_fetch_fx_series_same_currency_is_ones(tmp_fx):
    series = tmp_fx.fetch_fx_series('SGD', '2025-01-01', '2025-01-31')
    assert (series == 1.0).all()
    assert len(series) > 0


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def test_fx_cache_roundtrip(tmp_fx):
    series = _make_fx_series(60)
    tmp_fx._write_cache('USD', series)
    loaded = tmp_fx._read_cache('USD')
    pd.testing.assert_series_equal(series, loaded, check_names=False, rtol=1e-6, check_freq=False)


def test_fx_cache_missing_returns_empty(tmp_fx):
    result = tmp_fx._read_cache('XXX')
    assert result.empty
