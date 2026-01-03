# src/utils/csv_handler.py
"""CSV file handling utilities."""

import csv
import logging
import os
from typing import Dict, List

logger = logging.getLogger('portfolio_analyzer.csv')


class CSVHandler:
    """Handle CSV file operations."""
    
    @staticmethod
    def load_stocks(filename: str) -> Dict[str, str]:
        """
        Load stock symbols and company names from CSV file.
        
        Args:
            filename: Path to CSV file containing stock data
        
        Returns:
            Dictionary mapping symbols to company names
        """
        stock_data = {}
        
        try:
            with open(filename, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    symbol = row['Symbol'].strip()
                    company = row['Company'].strip()
                    stock_data[symbol] = company
            
            logger.info(f"Loaded {len(stock_data)} stocks from {filename}")
            return stock_data
        
        except FileNotFoundError:
            logger.error(f"Stock data file not found: {filename}")
            raise
        except Exception as e:
            logger.error(f"Error loading stock data from {filename}: {str(e)}")
            raise
    
    @staticmethod
    def write_prices(data: List[Dict], filename: str):
        """
        Write stock price data to CSV file.
        
        Args:
            data: List of dictionaries containing stock price data
            filename: Output CSV file path
        """
        if not data:
            logger.warning("No data to write to CSV")
            return
        
        fieldnames = ['Company', 'Symbol', 'Price', 'Currency', 'Price_USD', 'Date']
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else '.', exist_ok=True)
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        logger.info(f"Data written to {filename}")