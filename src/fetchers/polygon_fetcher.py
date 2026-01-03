# src/fetchers/polygon_fetcher.py
"""Polygon.io fetcher implementation."""

import logging
import os
import time
from datetime import datetime
from typing import Dict, Optional

import requests

from .base import BaseFetcher

logger = logging.getLogger('portfolio_analyzer.polygon')


class PolygonFetcher(BaseFetcher):
    """Fetch stock prices using Polygon.io API."""
    
    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3):
        """
        Initialize Polygon fetcher.
        
        Args:
            api_key: Polygon API key (if None, reads from environment)
            max_retries: Maximum number of retry attempts
        """
        super().__init__(max_retries)
        self.api_key = api_key or os.getenv('POLYGON_API_KEY')
        
        if not self.api_key:
            raise ValueError("Polygon API key not provided")
    
    def fetch_price(self, symbol: str, date: Optional[str] = None) -> Dict:
        """
        Fetch stock price using Polygon.io API.
        
        Args:
            symbol: Stock symbol
            date: Date in 'YYYY-MM-DD' format or None for most recent
        
        Returns:
            Dict with 'price', 'date', 'currency' keys
        """
        # Convert Yahoo Finance format to standard format
        clean_symbol = symbol.replace('.TW', '')
        
        for attempt in range(self.max_retries):
            try:
                if date:
                    url = f"https://api.polygon.io/v1/open-close/{clean_symbol}/{date}"
                else:
                    # Get most recent trading day
                    url = f"https://api.polygon.io/v2/aggs/ticker/{clean_symbol}/prev"
                
                params = {'apiKey': self.api_key}
                
                logger.info(f"Calling Polygon API for {clean_symbol}")
                response = requests.get(url, params=params)
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    logger.warning(f"Rate limit hit for {clean_symbol}")
                    if attempt < self.max_retries - 1:
                        delay = self.exponential_backoff(attempt, base_delay=2.0)
                        time.sleep(delay)
                        continue
                    else:
                        return {'price': None, 'date': None, 'currency': 'USD'}
                
                response.raise_for_status()
                data = response.json()
                
                if date:
                    price = data.get('close')
                    actual_date = date
                else:
                    results = data.get('results', [])
                    if results:
                        price = results[0].get('c')  # Close price
                        timestamp = results[0].get('t')
                        actual_date = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d')
                    else:
                        price = None
                        actual_date = None
                
                # Add delay to avoid rate limits (free tier: 5 calls/minute)
                time.sleep(12.5)  # ~4.8 calls/minute to be safe
                
                return {'price': price, 'date': actual_date, 'currency': 'USD'}
                
            except Exception as e:
                logger.error(f"Error fetching data from Polygon for {clean_symbol} (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    delay = self.exponential_backoff(attempt)
                    time.sleep(delay)
                else:
                    return {'price': None, 'date': None, 'currency': 'USD'}