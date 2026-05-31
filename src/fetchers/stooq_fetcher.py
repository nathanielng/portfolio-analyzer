# src/fetchers/stooq_fetcher.py
"""Stooq fetcher — free daily quotes, no API key required.

URL pattern: https://stooq.com/q/l/?f=sd2t2ohlcv&h&e=csv&s={ticker}.us
Returns a one-row CSV with columns: Symbol, Date, Time, Open, High, Low, Close, Volume.

Useful as a third fallback after yfinance and Polygon. Stooq covers US equities
and major indices well; non-US listings (e.g. 2330.TW) are not available and
will return None so the caller can fall through to a snapshot.
"""

import csv
import io
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import requests

from .base import BaseFetcher

logger = logging.getLogger('portfolio_analyzer.stooq')

_BASE_URL = "https://stooq.com/q/l/"
_HIST_URL = "https://stooq.com/q/d/l/"  # historical daily CSV


def _stooq_symbol(symbol: str) -> Optional[str]:
    """Convert internal symbol to Stooq format, or None if unsupported."""
    if symbol.endswith('.TW') or symbol.endswith('.SI'):
        return None  # Stooq doesn't carry these; let caller use snapshot
    # Strip any exchange suffix and append .US
    base = symbol.split('.')[0]
    return f"{base}.US".lower()


class StooqFetcher(BaseFetcher):
    """Fetch daily stock quotes from Stooq (free, no API key)."""

    def fetch_price(self, symbol: str, date: Optional[str] = None) -> Dict:
        """
        Fetch most-recent or historical close price from Stooq.

        Args:
            symbol: Ticker (Yahoo Finance format accepted, e.g. 'AAPL', '2330.TW').
            date: 'YYYY-MM-DD' or None for most recent close.

        Returns:
            Dict with 'price', 'date', 'currency' (always 'USD').
            price is None when unsupported or unavailable.
        """
        stooq_sym = _stooq_symbol(symbol)
        if stooq_sym is None:
            logger.info(f"Stooq: {symbol} not supported (non-US listing) — skipping")
            return {'price': None, 'date': date, 'currency': 'USD'}

        for attempt in range(self.max_retries):
            try:
                if date:
                    # Fetch a narrow date range to find the requested date
                    dt = datetime.strptime(date, '%Y-%m-%d')
                    d_to = (dt + timedelta(days=5)).strftime('%Y%m%d')
                    params = {
                        's': stooq_sym,
                        'i': 'd',
                        'd1': dt.strftime('%Y%m%d'),
                        'd2': d_to,
                        'o': 1,
                    }
                    url = _HIST_URL
                else:
                    params = {'s': stooq_sym, 'f': 'sd2t2ohlcv', 'h': '', 'e': 'csv'}
                    url = _BASE_URL

                logger.info(f"Stooq: fetching {stooq_sym}")
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()

                reader = csv.DictReader(io.StringIO(resp.text))
                rows = list(reader)

                if not rows:
                    logger.warning(f"Stooq: empty response for {stooq_sym}")
                    return {'price': None, 'date': date, 'currency': 'USD'}

                row = rows[0]
                close = float(row.get('Close', 0) or 0)
                actual_date = row.get('Date', date)

                if close == 0:
                    return {'price': None, 'date': actual_date, 'currency': 'USD'}

                return {'price': close, 'date': actual_date, 'currency': 'USD'}

            except Exception as e:
                logger.error(
                    f"Stooq: error fetching {stooq_sym} (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.exponential_backoff(attempt))
                else:
                    return {'price': None, 'date': date, 'currency': 'USD'}
