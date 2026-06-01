# tests/test_freshness.py
"""Tests for the data-freshness marker utility."""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import src.utils.freshness as fr


def _redirect_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, '_MARKER', tmp_path / '.refresh.json')


def test_never_refreshed_is_stale(tmp_path, monkeypatch):
    _redirect_marker(tmp_path, monkeypatch)
    assert fr.last_refreshed('foo') is None
    assert fr.age_hours('foo') is None
    assert fr.is_fresh('foo') is False


def test_mark_then_fresh(tmp_path, monkeypatch):
    _redirect_marker(tmp_path, monkeypatch)
    fr.mark_refreshed('daily_report')
    assert fr.is_fresh('daily_report', 18) is True
    assert fr.age_hours('daily_report') < 0.1


def test_zero_threshold_is_stale(tmp_path, monkeypatch):
    _redirect_marker(tmp_path, monkeypatch)
    fr.mark_refreshed('x')
    assert fr.is_fresh('x', 0) is False  # 0h tolerance → anything counts as stale


def test_independent_tags(tmp_path, monkeypatch):
    _redirect_marker(tmp_path, monkeypatch)
    fr.mark_refreshed('a')
    assert fr.is_fresh('a') is True
    assert fr.is_fresh('b') is False  # untouched tag stays stale


def test_stale_after_threshold(tmp_path, monkeypatch):
    _redirect_marker(tmp_path, monkeypatch)
    # Manually write an old timestamp
    old = (datetime.now().astimezone() - timedelta(hours=30)).isoformat(timespec='seconds')
    (tmp_path / '.refresh.json').write_text('{"daily_report": "%s"}' % old)
    assert fr.is_fresh('daily_report', 18) is False
    assert fr.age_hours('daily_report') > 18


def test_corrupt_marker_is_stale(tmp_path, monkeypatch):
    _redirect_marker(tmp_path, monkeypatch)
    (tmp_path / '.refresh.json').write_text('not json{{{')
    assert fr.is_fresh('daily_report') is False  # graceful, no crash
