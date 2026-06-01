# src/utils/freshness.py
"""Shared data-freshness marker.

Scripts that refresh data (daily_report.py, portfolio_snapshot.py) call
``mark_refreshed(tag)`` on success. Skills and scripts check ``is_fresh(tag)``
before re-fetching — so an interactive invocation skips the (slow) refresh if
the morning cron already ran today.

Marker file: data/.refresh.json   (gitignored via data/*.json)
    {
      "daily_report":   "2026-06-01T08:00:12+08:00",
      "portfolio_data": "2026-06-01T08:10:45+08:00"
    }

CLI (for use inside skills / shell):
    python -m src.utils.freshness check portfolio_data 18
        exit 0 + "FRESH ..."  if refreshed within 18h
        exit 1 + "STALE ..."  otherwise (caller should refresh)
    python -m src.utils.freshness mark daily_report
    python -m src.utils.freshness status
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_MARKER = Path(__file__).resolve().parent.parent.parent / 'data' / '.refresh.json'
_DEFAULT_MAX_AGE_HOURS = 18.0


def _load() -> dict:
    if _MARKER.exists():
        try:
            return json.loads(_MARKER.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def mark_refreshed(tag: str) -> None:
    """Record that data tagged `tag` was just refreshed (local time, ISO-8601)."""
    data = _load()
    data[tag] = datetime.now().astimezone().isoformat(timespec='seconds')
    _MARKER.parent.mkdir(parents=True, exist_ok=True)
    _MARKER.write_text(json.dumps(data, indent=2))


def last_refreshed(tag: str) -> Optional[datetime]:
    ts = _load().get(tag)
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def age_hours(tag: str) -> Optional[float]:
    last = last_refreshed(tag)
    if last is None:
        return None
    return (datetime.now().astimezone() - last).total_seconds() / 3600.0


def is_fresh(tag: str, max_age_hours: float = _DEFAULT_MAX_AGE_HOURS) -> bool:
    """True if `tag` was refreshed within `max_age_hours`."""
    age = age_hours(tag)
    return age is not None and age <= max_age_hours


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv) -> int:
    if not argv:
        print("usage: freshness {check <tag> [hours] | mark <tag> | status}", file=sys.stderr)
        return 2

    cmd = argv[0]

    if cmd == 'check':
        if len(argv) < 2:
            print("usage: freshness check <tag> [hours]", file=sys.stderr)
            return 2
        tag = argv[1]
        hours = float(argv[2]) if len(argv) > 2 else _DEFAULT_MAX_AGE_HOURS
        age = age_hours(tag)
        if age is None:
            print(f"STALE {tag}: never refreshed → refresh needed")
            return 1
        if age <= hours:
            print(f"FRESH {tag}: refreshed {age:.1f}h ago (≤ {hours:.0f}h) → skip refresh")
            return 0
        print(f"STALE {tag}: refreshed {age:.1f}h ago (> {hours:.0f}h) → refresh needed")
        return 1

    if cmd == 'mark':
        if len(argv) < 2:
            print("usage: freshness mark <tag>", file=sys.stderr)
            return 2
        mark_refreshed(argv[1])
        print(f"marked {argv[1]} refreshed at {last_refreshed(argv[1])}")
        return 0

    if cmd == 'status':
        data = _load()
        if not data:
            print("no refresh marker yet")
            return 0
        for tag in sorted(data):
            a = age_hours(tag)
            print(f"  {tag:<16} {data[tag]}  ({a:.1f}h ago)" if a is not None else f"  {tag}: {data[tag]}")
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(_cli(sys.argv[1:]))
