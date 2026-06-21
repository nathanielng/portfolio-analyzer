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

import numpy as np
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
    benchmark_name: str = 'SPY',
) -> Dict:
    """
    Calculate all metrics for a symbol given price history and benchmark.

    Args:
        prices_df: Single-column DataFrame with Close prices
        benchmark_df: Benchmark Close prices (SPY, QQQ, IWM, or VTI)
        symbol: Symbol name (for logging)
        benchmark_name: Name of benchmark ('SPY', 'QQQ', 'IWM', 'VTI')

    Returns:
        Dictionary of metrics and sparkline data
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

        # Generate sparkline data (all points for this timeframe, chronological order)
        sparkline_prices = [float(p) for p in prices_arr]
        sparkline_dates = [d.strftime('%Y-%m-%d') for d in prices_aligned.index]

        bench_key = f'benchmark_return_{benchmark_name.lower()}'
        sparkline_key_prices = f'sparkline_prices_{benchmark_name.lower()}'
        sparkline_key_dates = f'sparkline_dates_{benchmark_name.lower()}'

        result = {
            'return': round(total_return, 2),
            'volatility': round(volatility, 2),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'sortino_ratio': round(sortino_ratio, 2),
            'beta': round(beta, 2),
            'alpha': round(alpha * 100, 2),
            'information_ratio': round(info_ratio, 2),
            bench_key: round(benchmark_total_return, 2),
        }

        # Add sparkline data for all benchmarks
        if benchmark_name == 'SPY':
            result['sparkline_prices'] = sparkline_prices
            result['sparkline_dates'] = sparkline_dates
        else:
            result[sparkline_key_prices] = sparkline_prices
            result[sparkline_key_dates] = sparkline_dates

        return result
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

    # Fetch benchmark data (SPY, QQQ, IWM, VTI)
    logger.info("Fetching benchmark data...")
    benchmarks = ['SPY', 'QQQ', 'IWM', 'VTI']
    benchmark_data = {b: {} for b in benchmarks}

    for bench_symbol in benchmarks:
        for preset_name, (days, interval) in presets_with_dates.items():
            try:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                end_date = datetime.now().strftime('%Y-%m-%d')
                df = fetcher.fetch([bench_symbol], start_date, end_date, interval)
                benchmark_data[bench_symbol][preset_name] = df
                logger.info(f"Fetched {bench_symbol} for {preset_name}: {len(df)} rows")
            except Exception as e:
                logger.warning(f"Failed to fetch {bench_symbol} for {preset_name}: {e}")
                benchmark_data[bench_symbol][preset_name] = pd.DataFrame()

    # Calculate metrics for each symbol and preset
    logger.info("Calculating metrics...")
    watchlist_metrics = []

    for symbol_entry in watchlist:
        symbol = symbol_entry['Symbol']
        logger.info(f"Processing {symbol}...")

        metrics_by_preset = {}
        for preset_name in presets_with_dates.keys():
            symbol_df = all_data.get(symbol, {}).get(preset_name, pd.DataFrame())

            # Calculate metrics against SPY (primary benchmark)
            spy_df = benchmark_data['SPY'].get(preset_name, pd.DataFrame())
            if not symbol_df.empty:
                metrics = calculate_metrics(symbol_df, spy_df, symbol, 'SPY')
            else:
                metrics = {}

            # Add other benchmark returns (QQQ, IWM, VTI)
            for bench in ['QQQ', 'IWM', 'VTI']:
                bench_df = benchmark_data[bench].get(preset_name, pd.DataFrame())
                if not symbol_df.empty and not bench_df.empty:
                    bench_metrics = calculate_metrics(symbol_df, bench_df, symbol, bench)
                    if bench_metrics:
                        metrics.update(bench_metrics)

            metrics_by_preset[preset_name] = metrics

        watchlist_metrics.append({
            'symbol': symbol,
            'company': symbol_entry.get('Company', ''),
            'notes': symbol_entry.get('Notes', ''),
            'metrics': metrics_by_preset,
        })

    # Add outperformance flags (underperforming in 2+ of 3 periods)
    for symbol_data in watchlist_metrics:
        underperform_count = 0
        for period in ['1y', '2y', '5y']:
            metrics = symbol_data['metrics'][period]
            if metrics and metrics.get('return', 0) < metrics.get('benchmark_return', 0):
                underperform_count += 1
        symbol_data['underperforming'] = underperform_count >= 2

    # Add group assignments
    symbol_groups = {
        # Chip Design
        'NVDA': 'Chip Design',
        'AMD': 'Chip Design',
        'INTC': 'Chip Design',
        'ARM': 'Chip Design',
        'SNPS': 'Chip Design',
        # Manufacturing & Memory
        'TSM': 'Manufacturing & Memory',
        'MU': 'Manufacturing & Memory',
        '000660.KS': 'Manufacturing & Memory',
        'ASML': 'Manufacturing & Memory',
        # Cloud & Enterprise
        'MSFT': 'Cloud & Enterprise',
        'AMZN': 'Cloud & Enterprise',
        'GOOGL': 'Cloud & Enterprise',
        'META': 'Cloud & Enterprise',
        'ORCL': 'Cloud & Enterprise',
        'AVGO': 'Cloud & Enterprise',
        # Consumer Hardware
        'AAPL': 'Consumer Hardware',
        # Benchmarks
        'SMH': 'Benchmarks',
        'QQQM': 'Benchmarks',
    }

    for symbol_data in watchlist_metrics:
        symbol_data['group'] = symbol_groups.get(symbol_data['symbol'], 'Other')

    # Calculate correlation matrix (1Y returns)
    logger.info("Calculating correlation matrix...")
    correlation_matrix = calculate_correlation_matrix(all_data, watchlist_metrics)

    # Generate output
    output = {
        'generated_at': datetime.now().isoformat(),
        'watchlist': watchlist_metrics,
        'correlation_matrix': correlation_matrix,
    }

    # Write JSON
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    logger.info(f"Report written to {OUTPUT_PATH}")
    logger.info("Done")


def calculate_correlation_matrix(all_data: Dict, watchlist_metrics: List[Dict]) -> Dict:
    """
    Calculate correlation matrix between all symbols using 1Y daily returns.

    Returns: {symbol: {symbol: correlation}}
    """
    import numpy as np

    # Extract symbols and their 1Y data
    symbols = [entry['symbol'] for entry in watchlist_metrics]
    returns_dict = {}

    for symbol in symbols:
        symbol_df = all_data.get(symbol, {}).get('1y', pd.DataFrame())
        if symbol_df.empty or len(symbol_df) < 2:
            continue

        prices = symbol_df.values.flatten()
        daily_returns = pd.Series(prices).pct_change().dropna()
        returns_dict[symbol] = daily_returns.values

    if not returns_dict:
        return {}

    # Find common length for all series
    min_len = min(len(v) for v in returns_dict.values())

    # Build correlation matrix
    matrix = {}
    for sym1 in returns_dict.keys():
        matrix[sym1] = {}
        for sym2 in returns_dict.keys():
            if sym1 == sym2:
                matrix[sym1][sym2] = 1.0
            else:
                try:
                    corr = float(np.corrcoef(
                        returns_dict[sym1][-min_len:],
                        returns_dict[sym2][-min_len:]
                    )[0, 1])
                    matrix[sym1][sym2] = round(corr, 3)
                except:
                    matrix[sym1][sym2] = None

    return matrix


if __name__ == '__main__':
    main()
