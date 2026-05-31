# src/fetchers/__init__.py
"""Data fetchers.

- ``base``/``yfinance_fetcher``/``polygon_fetcher`` : per-quote price fetching (existing)
- ``history`` : bulk historical OHLC                                          [stub]
- ``fx``      : historical FX + base-currency (SGD) conversion (§6.5)         [stub]
- ``macro``   : FRED rates/oil/CPI + VIX regime dashboard (§6.5)              [stub]
"""

from .base import BaseFetcher
from .yfinance_fetcher import YFinanceFetcher
from .polygon_fetcher import PolygonFetcher
from .history import HistoryFetcher
from .fx import FXConverter
from .macro import MacroFetcher

__all__ = [
    'BaseFetcher',
    'YFinanceFetcher',
    'PolygonFetcher',
    'HistoryFetcher',
    'FXConverter',
    'MacroFetcher',
]
