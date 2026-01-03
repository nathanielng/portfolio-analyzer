# src/fetchers/yfinance_fetcher.py
"""Yahoo Finance fetcher implementation."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import yfinance as yf

from .base import BaseFetcher

logger = logging.getLogger('portfolio_analyzer.yfinance')


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
        for attempt in range(self.max_retries):
            try:
                ticker = yf.Ticker(symbol)
                
                # Get currency info
                info = ticker.info
                currency = info.get('currency', 'USD')
                
                if date:
                    # Fetch historical data for specific date
                    hist = ticker.history(
                        start=date,
                        end=datetime.strptime(date, '%Y-%m-%d') + timedelta(days=5)
                    )
                    if not hist.empty:
                        price = hist['Close'].iloc[0]
                        actual_date = hist.index[0].strftime('%Y-%m-%d')
                    else:
                        logger.warning(f"No data available for {symbol} on {date}")
                        return {'price': None, 'date': date, 'currency': currency}
                else:
                    # Get most recent price
                    hist = ticker.history(period='5d')
                    if not hist.empty:
                        price = hist['Close'].iloc[-1]
                        actual_date = hist.index[-1].strftime('%Y-%m-%d')
                    else:
                        logger.warning(f"No recent data available for {symbol}")
                        return {'price': None, 'date': None, 'currency': currency}
                
                return {'price': price, 'date': actual_date, 'currency': currency}
                
            except Exception as e:
                logger.error(f"Error fetching data for {symbol} (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    import time
                    delay = self.exponential_backoff(attempt)
                    time.sleep(delay)
                else:
                    return {'price': None, 'date': None, 'currency': 'USD'}