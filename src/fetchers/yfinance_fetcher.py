# src/fetchers/yfinance_fetcher.py
"""Yahoo Finance fetcher implementation."""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import yfinance as yf

from .base import BaseFetcher

logger = logging.getLogger('portfolio_analyzer.yfinance')

# Infer listing currency from symbol suffix without calling ticker.info.
# ticker.info is unreliable (frequent timeouts, empty dicts for ADRs and non-US
# tickers like ASML, 2330.TW, VRT) — calling it blocks for 5-10s per symbol
# and often returns currency='USD' even for TWD/EUR-listed stocks.
_SUFFIX_CURRENCY = {
    '.TW': 'TWD',
    '.SI': 'SGD',
    '.L':  'GBp',    # London SE quotes in pence (GBp), not GBP
    '.AS': 'EUR',    # Amsterdam (Euronext)
    '.PA': 'EUR',    # Paris
    '.DE': 'EUR',    # Frankfurt
    '.HK': 'HKD',
    '.KS': 'KRW',    # Korea Stock Exchange
    '.KQ': 'KRW',    # KOSDAQ
    '.T':  'JPY',
    '.AX': 'AUD',
    '.TO': 'CAD',
}


def _infer_currency(symbol: str) -> str:
    for suffix, ccy in _SUFFIX_CURRENCY.items():
        if symbol.upper().endswith(suffix.upper()):
            return ccy
    return 'USD'


class YFinanceFetcher(BaseFetcher):
    """Fetch stock prices using Yahoo Finance."""

    def fetch_price(self, symbol: str, date: Optional[str] = None) -> Dict:
        """
        Fetch stock price using yfinance.

        Args:
            symbol: Stock symbol in Yahoo Finance format
            date: Date in 'YYYY-MM-DD' format or None for most recent

        Returns:
            Dict with 'price', 'date', 'currency' keys
        """
        currency = _infer_currency(symbol)

        for attempt in range(self.max_retries):
            try:
                ticker = yf.Ticker(symbol)

                if date:
                    # Fetch a short window around the requested date to find
                    # the nearest trading day (markets may be closed on that date)
                    end_dt = datetime.strptime(date, '%Y-%m-%d') + timedelta(days=5)
                    hist = ticker.history(
                        start=date,
                        end=end_dt.strftime('%Y-%m-%d'),
                        auto_adjust=True,
                    )
                    if not hist.empty:
                        price = float(hist['Close'].iloc[0])
                        actual_date = hist.index[0].strftime('%Y-%m-%d')
                    else:
                        logger.warning(f"No data for {symbol} on or after {date}")
                        return {'price': None, 'date': date, 'currency': currency}
                else:
                    hist = ticker.history(period='5d', auto_adjust=True)
                    if not hist.empty:
                        price = float(hist['Close'].iloc[-1])
                        actual_date = hist.index[-1].strftime('%Y-%m-%d')
                    else:
                        logger.warning(f"No recent data for {symbol}")
                        return {'price': None, 'date': None, 'currency': currency}

                return {'price': price, 'date': actual_date, 'currency': currency}

            except Exception as e:
                logger.error(
                    f"Error fetching {symbol} (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.exponential_backoff(attempt))
                else:
                    return {'price': None, 'date': None, 'currency': currency}
