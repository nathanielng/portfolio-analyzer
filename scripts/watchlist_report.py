#!/usr/bin/env python3
"""Generate watchlist performance metrics across multiple timeframes.

Reads data/watchlist.csv, loads cached historical data for each symbol across
multiple presets (7d, 30d, 3m, 6m, 1y, 2y, 5y), calculates metrics
(returns, volatility, max drawdown, Sharpe, Sortino, Beta, Alpha, Info ratio),
and writes a JSON report to output/watchlist-data.json.

Includes SPY benchmark for comparison.

Usage:
    python scripts/watchlist_report.py
"""

import csv
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.analyzers.risk_metrics import RiskMetrics
from src.fetchers.history import HistoryFetcher, PRESETS, _preset_dates

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

PROJECT_ROOT = Path(__file__).parent.parent
WATCHLIST_PATH = PROJECT_ROOT / 'data' / 'watchlist.csv'
OUTPUT_PATH = PROJECT_ROOT / 'output' / 'watchlist-data.json'


def read_watchlist(csv_path: Path) -> List[Dict[str, str]]:
    """Read watchlist.csv and return list of symbol dicts."""
    watchlist = []
    if not csv_path.exists():
        logger.error(f"Watchlist not found: {csv_path}")
        return watchlist

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            watchlist.append(row)

    logger.info(f"Loaded {len(watchlist)} symbols from watchlist")
    return watchlist


def fetch_all_data(
    symbols: List[str],
    presets: List[str],
    fetcher: HistoryFetcher,
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """
    Fetch historical data for all symbols and presets.

    Returns:
        {symbol: {preset: DataFrame}}
    """
    data = {}
    for symbol in symbols:
        data[symbol] = {}
        for preset in presets:
            try:
                df = fetcher.fetch_preset([symbol], preset)
                data[symbol][preset] = df
                logger.info(f"Fetched {symbol} for {preset}: {len(df)} rows")
            except Exception as e:
                logger.error(f"Failed to fetch {symbol} for {preset}: {e}")
                data[symbol][preset] = pd.DataFrame()

    return data


def calculate_metrics(
    prices_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    symbol: str,
) -> Dict[str, float]:
    """
    Calculate all metrics for a symbol given price history and benchmark.

    Args:
        prices_df: Single-column DataFrame with Close prices
        benchmark_df: SPY Close prices
        symbol: Symbol name (for logging)

    Returns:
        Dictionary of metrics
    """
    if prices_df.empty or benchmark_df.empty:
        return {}

    # Align dates between symbol and benchmark
    common_dates = prices_df.index.intersection(benchmark_df.index)
    if len(common_dates) < 2:
        logger.warning(f"Insufficient data for {symbol} (only {len(common_dates)} common dates)")
        return {}

    prices_aligned = prices_df.loc[common_dates].copy()
    benchmark_aligned = benchmark_df.loc[common_dates].copy()

    analyzer = RiskMetrics(risk_free_rate=0.04)

    try:
        # Simple calculation of total return
        if len(prices_aligned) < 2:
            return {}

        prices_arr = prices_aligned.values.flatten()
        benchmark_arr = benchmark_aligned.values.flatten()

        total_return = float((prices_arr[-1] / prices_arr[0] - 1) * 100)
        benchmark_total_return = float((benchmark_arr[-1] / benchmark_arr[0] - 1) * 100)

        # Calculate daily returns for volatility and other metrics
        price_returns = pd.Series(prices_arr).pct_change().dropna() * 100
        benchmark_returns_series = pd.Series(benchmark_arr).pct_change().dropna() * 100

        # Calculate volatility (annualized)
        volatility = float(price_returns.std() * (252 ** 0.5))  # Annualized

        # Calculate max drawdown
        cumulative = (1 + price_returns / 100).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = float(drawdown.min() * 100)

        # Calculate Sharpe ratio
        excess_return = price_returns.mean() - (0.04 / 252 * 100)  # Daily risk-free rate
        sharpe_ratio = float((excess_return / price_returns.std()) * (252 ** 0.5)) if price_returns.std() > 0 else 0

        # Calculate Sortino ratio
        downside_returns = price_returns[price_returns < 0]
        downside_std = downside_returns.std()
        sortino_ratio = float((excess_return / downside_std) * (252 ** 0.5)) if downside_std > 0 else 0

        # Calculate beta
        covariance = price_returns.cov(benchmark_returns_series)
        variance = benchmark_returns_series.var()
        beta = float(covariance / variance) if variance > 0 else 0

        # Calculate alpha (expected vs actual return)
        expected_return = 0.04 + beta * (benchmark_returns_series.mean() * 252 / 100 - 0.04)
        alpha = (price_returns.mean() * 252 / 100) - expected_return

        # Calculate information ratio
        tracking_error = (price_returns - benchmark_returns_series).std() * (252 ** 0.5)
        info_ratio = float((excess_return * 252 / 100) / tracking_error) if tracking_error > 0 else 0

        return {
            'return': round(total_return, 2),
            'volatility': round(volatility, 2),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'sortino_ratio': round(sortino_ratio, 2),
            'beta': round(beta, 2),
            'alpha': round(alpha * 100, 2),
            'information_ratio': round(info_ratio, 2),
            'benchmark_return': round(benchmark_total_return, 2),
        }
    except Exception as e:
        logger.error(f"Error calculating metrics for {symbol}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return {}


def main():
    """Generate watchlist report."""
    logger.info("Starting watchlist report generation")

    # Read watchlist
    watchlist = read_watchlist(WATCHLIST_PATH)
    if not watchlist:
        logger.error("No symbols in watchlist")
        return

    symbols = [row['Symbol'] for row in watchlist]

    # Presets to analyze: 7d, 30d, 3m, 6m, 1y, 2y, 5y
    # Note: 30d and 6m don't have built-in presets, we'll map them
    presets = ['7d', '1m', '3m', '1y', '5y']  # available presets
    preset_display_names = {
        '7d': '7d',
        '1m': '30d',
        '3m': '3m',
        '1y': '1y',
        '5y': '5y',
    }

    # We'll add 6m and 2y manually by calculating dates
    presets_with_dates = {
        '7d': (7, '1d'),
        '30d': (30, '1d'),
        '3m': (90, '1d'),
        '6m': (180, '1d'),
        '1y': (365, '1d'),
        '2y': (730, '1d'),
        '5y': (1825, '1d'),
    }

    # Initialize fetcher
    fetcher = HistoryFetcher()

    # Fetch all data for all presets with custom dates
    logger.info("Fetching historical data for all symbols and timeframes...")
    all_data = {}

    for symbol in symbols:
        all_data[symbol] = {}
        for preset_name, (days, interval) in presets_with_dates.items():
            try:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                end_date = datetime.now().strftime('%Y-%m-%d')
                df = fetcher.fetch([symbol], start_date, end_date, interval)
                all_data[symbol][preset_name] = df
                logger.info(f"Fetched {symbol} for {preset_name}: {len(df)} rows")
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol} for {preset_name}: {e}")
                all_data[symbol][preset_name] = pd.DataFrame()

    # Fetch SPY benchmark
    logger.info("Fetching SPY benchmark data...")
    spy_data = {}
    for preset_name, (days, interval) in presets_with_dates.items():
        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
            df = fetcher.fetch(['SPY'], start_date, end_date, interval)
            spy_data[preset_name] = df
            logger.info(f"Fetched SPY for {preset_name}: {len(df)} rows")
        except Exception as e:
            logger.warning(f"Failed to fetch SPY for {preset_name}: {e}")
            spy_data[preset_name] = pd.DataFrame()

    # Calculate metrics for each symbol and preset
    logger.info("Calculating metrics...")
    watchlist_metrics = []

    for symbol_entry in watchlist:
        symbol = symbol_entry['Symbol']
        logger.info(f"Processing {symbol}...")

        metrics_by_preset = {}
        for preset_name in presets_with_dates.keys():
            symbol_df = all_data.get(symbol, {}).get(preset_name, pd.DataFrame())
            spy_df = spy_data.get(preset_name, pd.DataFrame())

            if not symbol_df.empty:
                metrics = calculate_metrics(symbol_df, spy_df, symbol)
            else:
                metrics = {}

            metrics_by_preset[preset_name] = metrics

        watchlist_metrics.append({
            'symbol': symbol,
            'company': symbol_entry.get('Company', ''),
            'notes': symbol_entry.get('Notes', ''),
            'metrics': metrics_by_preset,
        })

    # Generate output
    output = {
        'generated_at': datetime.now().isoformat(),
        'watchlist': watchlist_metrics,
    }

    # Write JSON
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    logger.info(f"Report written to {OUTPUT_PATH}")
    logger.info("Done")


if __name__ == '__main__':
    main()
