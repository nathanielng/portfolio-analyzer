# scripts/fetch_prices.py
"""Script to fetch stock prices and save to CSV."""

import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

# Add parent directory to path so we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

from src.fetchers import PolygonFetcher, YFinanceFetcher
from src.utils import CSVHandler, CurrencyConverter, setup_logger

# Load environment variables
load_dotenv()

# Setup logging
logger = setup_logger()


def determine_backend() -> str:
    """
    Determine which backend to use based on environment variables.
    Priority: Polygon (if API key exists) > YFinance (default)
    """
    polygon_key = os.getenv('POLYGON_API_KEY')

    if polygon_key:
        logger.info("Polygon API key found - using Polygon as default backend")
        return 'polygon'
    else:
        logger.info("No Polygon API key found - using YFinance as default backend")
        return 'yfinance'


def get_stock_prices(
    date: Optional[str] = None,
    backend: Optional[str] = None,
    convert_usd: bool = True,
    stocks_csv: str = 'data/tickers.csv'
) -> List[Dict]:
    """
    Fetch stock prices for a given date (or most recent if date is None).

    Args:
        date: Date in 'YYYY-MM-DD' format. If None, fetches most recent price.
        backend: 'yfinance' or 'polygon'. If None, auto-determined.
        convert_usd: Whether to convert prices to USD
        stocks_csv: Path to CSV file containing stock symbols and company names

    Returns:
        List of dicts with keys: Company, Symbol, Price, Currency, Price_USD, Date
    """
    if backend is None:
        backend = determine_backend()

    # Load stock data from CSV
    stock_data = CSVHandler.load_stocks(stocks_csv)

    # Initialize fetcher
    if backend == 'yfinance':
        fetcher = YFinanceFetcher()
    elif backend == 'polygon':
        fetcher = PolygonFetcher()
    else:
        raise ValueError(f"Unknown backend: {backend}")

    # Initialize currency converter
    converter = CurrencyConverter()

    logger.info(f"Fetching stock prices using {backend} backend for date: {date if date else 'most recent'}")

    results = []

    for i, (symbol, company) in enumerate(stock_data.items()):
        logger.info(f"Fetching data for {symbol} ({company})")
        if i > 0:
            time.sleep(0.3)  # polite pacing — avoids yfinance rate limits on bulk runs

        result = fetcher.fetch_price(symbol, date)

        price = result['price']
        currency = result['currency']

        # Convert to USD if requested and price exists
        price_usd = None
        if convert_usd and price is not None:
            price_usd = converter.convert(price, currency, 'USD')

        price_str = f"{price:.2f}" if price else "N/A"
        price_usd_str = f"{price_usd:.2f}" if price_usd else "N/A"

        # Format date as yyyymmdd
        date_str = result['date']
        if date_str and date_str != 'N/A':
            try:
                # Convert from YYYY-MM-DD to yyyymmdd
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                date_str = date_obj.strftime('%Y%m%d')
            except ValueError:
                # If date is already in different format, keep as is
                pass

        results.append({
            'Company': company,
            'Symbol': symbol,
            'Price': price_str,
            'Currency': currency,
            'Price_USD': price_usd_str,
            'Date': date_str
        })

    logger.info(f"Successfully fetched data for {len(results)} stocks")
    return results


def print_table(data: List[Dict]):
    """Print data as a formatted table."""
    if not data:
        logger.warning("No data to print")
        return

    # Calculate column widths
    headers = ['Company', 'Symbol', 'Price', 'Currency', 'Price_USD', 'Date']
    col_widths = {h: len(h) for h in headers}

    for row in data:
        for header in headers:
            col_widths[header] = max(col_widths[header], len(str(row.get(header, ''))))

    # Print header
    header_row = ' | '.join(h.ljust(col_widths[h]) for h in headers)
    print('\n' + header_row)
    print('-' * len(header_row))

    # Print rows
    for row in data:
        print(' | '.join(str(row.get(h, '')).ljust(col_widths[h]) for h in headers))


def main():
    """Main function to fetch and display stock prices."""
    import argparse
    parser = argparse.ArgumentParser(description='Fetch current (or historical) stock prices')
    parser.add_argument(
        '--date', default=None,
        help='Fetch for a specific date (YYYY-MM-DD). Default: most recent close.'
    )
    parser.add_argument('--stocks-csv', default=os.getenv('STOCKS_CSV', 'data/tickers.csv'))
    parser.add_argument('--output', default=os.getenv('OUTPUT_FILE', 'output/stock_prices.csv'))
    args = parser.parse_args()

    label = f"for {args.date}" if args.date else "(most recent)"
    logger.info("=" * 60)
    logger.info(f"Fetching stock prices {label}")
    logger.info("=" * 60)

    data = get_stock_prices(date=args.date, stocks_csv=args.stocks_csv)
    print_table(data)
    CSVHandler.write_prices(data, args.output)


if __name__ == "__main__":
    main()
