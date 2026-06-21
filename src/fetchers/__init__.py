# src/fetchers/__init__.py
"""Data fetchers.

- ``base``/``yfinance_fetcher``/``polygon_fetcher`` : per-quote price fetching (implemented)
- ``stooq_fetcher`` : free daily quotes fallback, no API key (US equities only)
- ``macro``   : FRED rates/oil/CPI + VIX regime dashboard (§6.5)
- ``news``    : per-ticker news headlines via Yahoo Finance RSS
- ``dividends``: per-share dividend history (cached)
- ``history`` : bulk historical OHLC
- ``fx``      : historical FX + base-currency (SGD) conversion (§6.5)
"""

from .base import BaseFetcher
from .yfinance_fetcher import YFinanceFetcher
from .polygon_fetcher import PolygonFetcher
from .stooq_fetcher import StooqFetcher
from .macro import MacroFetcher
from .news import NewsFetcher
from .dividends import DividendFetcher
from .history import HistoryFetcher
from .fx import FXConverter

__all__ = [
    'BaseFetcher',
    'YFinanceFetcher',
    'PolygonFetcher',
    'StooqFetcher',
    'MacroFetcher',
    'NewsFetcher',
    'DividendFetcher',
    'HistoryFetcher',
    'FXConverter',
]
