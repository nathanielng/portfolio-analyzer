# src/utils/quote_cache.py
"""Disk-backed TTL cache for live quotes and FX rates.

daily_report.py and portfolio_snapshot.py both fetch current prices + FX.
When both run in the same window (e.g. the 08:00 and 08:10 cron jobs, or an
interactive skill invocation minutes after the morning run), this cache lets
the later run reuse the earlier run's quotes instead of hitting yfinance / the
FX API again.

Cache file: data/.quotes.json   (gitignored via data/*.json)
TTL: default 60 min; override with the QUOTE_CACHE_TTL_MIN env var.
Set quote_cache.ENABLED = False to bypass entirely (e.g. a --no-cache flag).

Only *successful* results are cached (see cache_if) so a transient fetch
failure never poisons the cache.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / 'data' / '.quotes.json'
DEFAULT_TTL_MIN = float(os.getenv('QUOTE_CACHE_TTL_MIN', '60'))
ENABLED = True


def _load() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(data: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(_CACHE_PATH)  # atomic on POSIX


def cached(
    key: str,
    producer: Callable[[], Any],
    ttl_minutes: Optional[float] = None,
    cache_if: Callable[[Any], bool] = lambda v: True,
) -> Any:
    """
    Return the cached value for `key` if younger than the TTL, else call
    `producer()`, store its result (only if `cache_if(result)`), and return it.

    Args:
        key: Cache key, e.g. 'quote:NVDA' or 'fx:USD>SGD'.
        producer: Zero-arg callable that performs the actual fetch.
        ttl_minutes: Override the default TTL.
        cache_if: Predicate — only store when it returns True (skip failures).
    """
    if ttl_minutes is None:
        ttl_minutes = DEFAULT_TTL_MIN
    if not ENABLED:
        return producer()

    data = _load()
    entry = data.get(key)
    now = time.time()
    if entry and (now - entry.get('ts', 0)) <= ttl_minutes * 60:
        return entry['value']

    value = producer()
    if cache_if(value):
        data[key] = {'ts': now, 'value': value}
        _save(data)
    return value


def clear() -> None:
    """Delete the entire quote cache (force fresh fetches next run)."""
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()


def age_minutes(key: str) -> Optional[float]:
    """Age of a cached key in minutes, or None if absent."""
    entry = _load().get(key)
    return (time.time() - entry['ts']) / 60.0 if entry else None
