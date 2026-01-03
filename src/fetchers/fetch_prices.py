# scripts/fetch_prices.py
"""Script to fetch stock prices and save to CSV."""

import logging
import os
from typing import Dict, List, Optional

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
    stocks_csv: str = 'data/stocks.csv'
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
    
    for symbol, company in stock_data.items():
        logger.info(f"Fetching data for {symbol} ({company})")
        
        result = fetcher.fetch_price(symbol, date)
        
        price = result['price']
        currency = result['currency']
        
        # Convert to USD if requested and price exists
        price_usd = None
        if convert_usd and price is not None:
            price_usd = converter.convert(price, currency, 'USD')
        
        price_str = f"{price:.2f}" if price else "N/A"
        price_usd_str = f"{price_usd:.2f}" if price_usd else "N/A"
        
        results.append({
            'Company': company,
            'Symbol': symbol,
            'Price': price_str,
            'Currency': currency,
            'Price_USD': price_usd_str,
            'Date': result['date']
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
    # Get configuration from environment
    stocks_csv = os.getenv('STOCKS_CSV', 'data/stocks.csv')
    output_file = os.getenv('OUTPUT_FILE', 'output/stock_prices.csv')
    
    # Example 1: Get most recent prices
    logger.info("=" * 60)
    logger.info("Fetching most recent stock prices")
    logger.info("=" * 60)
    data_recent = get_stock_prices(stocks_csv=stocks_csv)
    print_table(data_recent)
    
    # Example 2: Get prices for a specific date
    logger.info("\n" + "=" * 60)
    logger.info("Fetching stock prices for 2025-01-03")
    logger.info("=" * 60)
    data_specific = get_stock_prices(date='2025-01-03', stocks_csv=stocks_csv)
    print_table(data_specific)
    
    # Save to CSV
    CSVHandler.write_prices(data_recent, output_file)


if __name__ == "__main__":
    main()