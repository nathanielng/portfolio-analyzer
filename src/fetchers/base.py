# src/fetchers/base.py
"""Base fetcher interface."""

import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional

logger = logging.getLogger('portfolio_analyzer.fetcher')


class BaseFetcher(ABC):
    """Base class for stock price fetchers."""
    
    def __init__(self, max_retries: int = 3):
        """
        Initialize fetcher.
        
        Args:
            max_retries: Maximum number of retry attempts
        """
        self.max_retries = max_retries
    
    def exponential_backoff(self, attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
        """Calculate exponential backoff delay."""
        delay = min(base_delay * (2 ** attempt), max_delay)
        logger.info(f"Backing off for {delay:.2f} seconds (attempt {attempt + 1})")
        return delay
    
    @abstractmethod
    def fetch_price(self, symbol: str, date: Optional[str] = None) -> Dict:
        """
        Fetch stock price.
        
        Args:
            symbol: Stock symbol
            date: Date in 'YYYY-MM-DD' format or None for most recent
        
        Returns:
            Dict with 'price', 'date', 'currency' keys
        """
        pass