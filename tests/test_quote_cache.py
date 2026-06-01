# tests/test_quote_cache.py
"""Tests for the shared quote/FX TTL cache."""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import src.utils.quote_cache as qc


def _redirect(tmp_path, monkeypatch):
    monkeypatch.setattr(qc, '_CACHE_PATH', tmp_path / '.quotes.json')
    monkeypatch.setattr(qc, 'ENABLED', True)


def test_producer_called_once_within_ttl(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    calls = []
    def producer():
        calls.append(1)
        return {'price': 100.0}
    r1 = qc.cached('quote:X', producer, ttl_minutes=60)
    r2 = qc.cached('quote:X', producer, ttl_minutes=60)
    assert r1 == r2 == {'price': 100.0}
    assert len(calls) == 1  # second call served from cache


def test_ttl_expiry_refetches(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    calls = []
    def producer():
        calls.append(1)
        return len(calls)
    qc.cached('k', producer, ttl_minutes=60)
    # Force the stored entry to look old
    import json
    data = json.loads((tmp_path / '.quotes.json').read_text())
    data['k']['ts'] = time.time() - 3601  # >60 min ago
    (tmp_path / '.quotes.json').write_text(json.dumps(data))
    qc.cached('k', producer, ttl_minutes=60)
    assert len(calls) == 2  # expired → producer called again


def test_failures_not_cached(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    calls = []
    def producer():
        calls.append(1)
        return None  # simulate failed fetch
    qc.cached('q', producer, cache_if=lambda v: v is not None)
    qc.cached('q', producer, cache_if=lambda v: v is not None)
    assert len(calls) == 2  # nothing cached, so producer runs both times


def test_disabled_bypasses(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    monkeypatch.setattr(qc, 'ENABLED', False)
    calls = []
    def producer():
        calls.append(1)
        return 42
    qc.cached('k', producer)
    qc.cached('k', producer)
    assert len(calls) == 2  # cache off → always calls producer
    assert not (tmp_path / '.quotes.json').exists()  # nothing written


def test_independent_keys(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    qc.cached('fx:USD>SGD', lambda: 1.28)
    qc.cached('quote:NVDA', lambda: {'price': 211.0})
    assert qc.cached('fx:USD>SGD', lambda: 999) == 1.28      # cached
    assert qc.cached('quote:NVDA', lambda: {})['price'] == 211.0


def test_clear(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    qc.cached('k', lambda: 1)
    assert (tmp_path / '.quotes.json').exists()
    qc.clear()
    assert not (tmp_path / '.quotes.json').exists()
