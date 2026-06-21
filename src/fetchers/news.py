# src/fetchers/news.py
"""Per-ticker news headlines via Yahoo Finance RSS (no API key, stdlib only)."""

import logging
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List
from urllib.parse import quote_plus

logger = logging.getLogger('portfolio_analyzer.news')

_RSS_URL = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline"
    "?s={ticker}&region=US&lang=en-US"
)
_HEADERS = {'User-Agent': 'Mozilla/5.0'}


class NewsFetcher:
    """Fetch recent news headlines for stock tickers from Yahoo Finance RSS.

    Uses stdlib urllib + xml.etree only — no extra dependencies.

    Args:
        max_per_ticker: Max headlines to return per symbol (default 3).
        timeout: HTTP timeout in seconds.
        max_retries: Retry attempts on network failure.
    """

    def __init__(self, max_per_ticker: int = 3, timeout: int = 10, max_retries: int = 2):
        self.max_per_ticker = max_per_ticker
        self.timeout = timeout
        self.max_retries = max_retries

    def fetch(self, symbol: str) -> List[Dict[str, str]]:
        """Return up to max_per_ticker headlines with links for symbol. Empty list on failure.

        Returns list of dicts: [{'title': '...', 'link': '...'}, ...]
        """
        # Strip exchange suffix for Yahoo RSS (2330.TW → 2330.TW works; ASML.AS → ASML)
        url = _RSS_URL.format(ticker=quote_plus(symbol))
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(url, headers=_HEADERS)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                articles = _parse_rss(raw, self.max_per_ticker)
                logger.info(f"News: {symbol} → {len(articles)} headlines")
                return articles
            except Exception as e:
                logger.warning(f"News fetch {symbol} attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)
        return []

    def fetch_many(self, symbols: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """Fetch headlines for multiple symbols. Returns {symbol: [{'title': '...', 'link': '...'}, ...]}."""
        return {symbol: self.fetch(symbol) for symbol in symbols}


def _parse_rss(raw: bytes, max_items: int) -> List[Dict[str, str]]:
    """Parse RSS feed and extract title + link for each item."""
    try:
        root = ET.fromstring(raw)
        articles = []
        for item in root.findall('.//item')[:max_items]:
            title = item.findtext('title')
            link = item.findtext('link')
            if title:
                articles.append({'title': title.strip(), 'link': link.strip() if link else ''})
        return articles
    except ET.ParseError as e:
        logger.warning(f"RSS parse error: {e}")
        return []
