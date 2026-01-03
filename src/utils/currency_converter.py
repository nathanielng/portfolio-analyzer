# src/utils/currency_converter.py
"""Currency conversion utilities."""

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger('portfolio_analyzer.currency')


class CurrencyConverter:
    """Handle currency conversions with caching."""
    
    def __init__(self):
        self._cache = {}
    
    def _exponential_backoff(self, attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
        """Calculate exponential backoff delay."""
        delay = min(base_delay * (2 ** attempt), max_delay)
        logger.info(f"Backing off for {delay:.2f} seconds (attempt {attempt + 1})")
        return delay
    
    def get_rate(self, from_currency: str, to_currency: str = 'USD', max_retries: int = 3) -> Optional[float]:
        """
        Get exchange rate from one currency to another.
        
        Args:
            from_currency: Source currency code (e.g., 'TWD')
            to_currency: Target currency code (default: 'USD')
            max_retries: Maximum retry attempts
        
        Returns:
            Exchange rate or None if unavailable
        """
        if from_currency == to_currency:
            return 1.0
        
        # Check cache
        cache_key = f"{from_currency}_{to_currency}"
        if cache_key in self._cache:
            logger.info(f"Using cached exchange rate for {from_currency} to {to_currency}")
            return self._cache[cache_key]
        
        for attempt in range(max_retries):
            try:
                # Using exchangerate-api.com - free tier, no API key required
                url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
                
                logger.info(f"Fetching exchange rate: {from_currency} to {to_currency}")
                response = requests.get(url, timeout=10)
                
                if response.status_code == 429:
                    logger.warning("Rate limit hit on exchange rate API")
                    if attempt < max_retries - 1:
                        delay = self._exponential_backoff(attempt, base_delay=2.0)
                        time.sleep(delay)
                        continue
                    else:
                        return None
                
                response.raise_for_status()
                data = response.json()
                
                rates = data.get('rates', {})
                rate = rates.get(to_currency)
                
                if rate:
                    self._cache[cache_key] = rate
                    logger.info(f"Exchange rate {from_currency}/{to_currency}: {rate:.6f}")
                    return rate
                else:
                    logger.warning(f"No exchange rate found for {from_currency} to {to_currency}")
                    return None
                    
            except Exception as e:
                logger.error(f"Error fetching exchange rate (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    delay = self._exponential_backoff(attempt)
                    time.sleep(delay)
                else:
                    return None
        
        return None
    
    def convert(self, price: Optional[float], from_currency: str, to_currency: str = 'USD') -> Optional[float]:
        """
        Convert price from one currency to another.
        
        Args:
            price: Price in original currency
            from_currency: Source currency code
            to_currency: Target currency code
        
        Returns:
            Converted price or None if conversion fails
        """
        if price is None or from_currency == to_currency:
            return price
        
        exchange_rate = self.get_rate(from_currency, to_currency)
        if exchange_rate:
            converted_price = price * exchange_rate
            logger.info(f"Converted {price:.2f} {from_currency} to {converted_price:.2f} {to_currency} (rate: {exchange_rate:.6f})")
            return converted_price
        else:
            logger.warning(f"Could not convert {from_currency} to {to_currency} - using original price")
            return price