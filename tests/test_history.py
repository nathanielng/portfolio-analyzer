# tests/test_history.py
"""Tests for HistoryFetcher — cache logic tested with synthetic data; live fetch not required."""

import os
import sys
import tempfile
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.fetchers.history import HistoryFetcher, PRESETS, _preset_dates, _slice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(start: str, days: int, price_start: float = 100.0) -> pd.DataFrame:
    """Synthetic OHLCV DataFrame with DatetimeIndex."""
    dates = pd.date_range(start=start, periods=days, freq='B')
    prices = [price_start + i for i in range(days)]
    return pd.DataFrame({
        'Open': prices, 'High': [p + 1 for p in prices],
        'Low': [p - 1 for p in prices], 'Close': prices, 'Volume': [1_000_000] * days,
    }, index=dates)


@pytest.fixture
def tmp_fetcher(tmp_path):
    return HistoryFetcher(cache_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Preset dates
# ---------------------------------------------------------------------------

def test_preset_keys():
    assert set(PRESETS.keys()) == {'7d', '1m', '3m', '1y', 'ytd', '5y', 'max'}


def test_preset_dates_intervals():
    for name, preset in PRESETS.items():
        start, end, interval = _preset_dates(preset)
        assert interval in ('1d', '1wk', '1mo'), f"{name} bad interval"
        assert start <= end


def test_ytd_preset_starts_jan1():
    start, _, _ = _preset_dates(PRESETS['ytd'])
    assert start.endswith('-01-01'), f"YTD should start Jan 1, got {start}"


def test_max_preset_uses_weekly():
    _, _, interval = _preset_dates(PRESETS['max'])
    assert interval == '1wk'


def test_all_under_5y_daily():
    for name in ('7d', '1m', '3m', '1y', 'ytd', '5y'):
        _, _, interval = _preset_dates(PRESETS[name])
        assert interval == '1d', f"{name} should be daily"


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def test_read_empty_cache(tmp_fetcher):
    df = tmp_fetcher._read_cache('FAKE', '1d')
    assert df.empty


def test_write_and_read_cache(tmp_fetcher):
    df = _make_df('2026-01-01', 10)
    tmp_fetcher._write_cache('TEST', '1d', df)
    loaded = tmp_fetcher._read_cache('TEST', '1d')
    assert len(loaded) == 10
    assert 'Close' in loaded.columns


def test_cache_path_safe_symbol(tmp_fetcher):
    path = tmp_fetcher.cache_path('2330.TW', '1d')
    assert '/' not in path.name  # no slash in filename
    assert path.suffix == '.csv'


def test_cache_info_none_when_missing(tmp_fetcher):
    assert tmp_fetcher.cache_info('MISSING', '1d') is None


def test_cache_info_populated(tmp_fetcher):
    df = _make_df('2026-01-05', 5)
    tmp_fetcher._write_cache('INFO', '1d', df)
    info = tmp_fetcher.cache_info('INFO', '1d')
    assert info is not None
    assert info['rows'] == 5
    assert '2026-01-05' == info['start']


# ---------------------------------------------------------------------------
# Cache merge / dedup logic
# ---------------------------------------------------------------------------

def test_slice_filters_date_range():
    df = _make_df('2026-01-01', 20)
    sliced = _slice(df, '2026-01-05', '2026-01-10')
    assert sliced.index.min() >= pd.Timestamp('2026-01-05')
    assert sliced.index.max() <= pd.Timestamp('2026-01-10')


def test_update_cache_appends_new_rows(tmp_fetcher, monkeypatch):
    """Simulate existing cache + genuinely new rows — written cache should be larger."""
    # Pre-populate cache with 10 rows ending 2026-01-15
    existing = _make_df('2026-01-02', 10)
    tmp_fetcher._write_cache('FAKE', '1d', existing)

    # New rows start well after the existing end — 5 genuinely new dates
    new_rows = _make_df('2026-01-20', 5, price_start=110.0)
    monkeypatch.setattr(tmp_fetcher, '_fetch_yfinance', lambda *a, **kw: new_rows)

    _, cached, fetched = tmp_fetcher.update_cache('FAKE', '1d', '2026-01-02', '2026-01-25')
    assert cached == 10
    assert fetched == 5
    # verify the written cache grew
    written = tmp_fetcher._read_cache('FAKE', '1d')
    assert len(written) == 15


def test_update_cache_cold_start(tmp_fetcher, monkeypatch):
    """First fetch (no cache) should work cleanly."""
    fresh = _make_df('2026-01-02', 20)
    monkeypatch.setattr(tmp_fetcher, '_fetch_yfinance', lambda *a, **kw: fresh)
    df, cached, fetched = tmp_fetcher.update_cache('NEW', '1d', '2026-01-02', '2026-01-30')
    assert cached == 0
    assert fetched == 20
    assert len(df) == 20
