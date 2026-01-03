# scripts/analyze_portfolio.py
"""Script to perform portfolio analysis including correlations and risk metrics."""

import logging
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

# Add parent directory to path so we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

from src.analyzers import PortfolioAnalyzer
from src.fetchers import PolygonFetcher, YFinanceFetcher
from src.utils import CSVHandler, setup_logger

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


def get_fetcher(backend: str = None):
    """Get appropriate fetcher based on backend."""
    if backend is None:
        backend = determine_backend()

    if backend == 'yfinance':
        return YFinanceFetcher()
    elif backend == 'polygon':
        return PolygonFetcher()
    else:
        raise ValueError(f"Unknown backend: {backend}")


def format_dataframe(df: pd.DataFrame, float_format: str = '.4f') -> str:
    """Format DataFrame for nice console output."""
    return df.to_string(float_format=lambda x: f'{x:{float_format}}')


def main():
    """Main function to perform portfolio analysis."""
    logger.info("=" * 80)
    logger.info("Portfolio Analysis Tool")
    logger.info("=" * 80)

    # Configuration
    stocks_csv = os.getenv('STOCKS_CSV', 'data/stocks.csv')
    output_dir = os.getenv('OUTPUT_DIR', 'output')
    risk_free_rate = float(os.getenv('RISK_FREE_RATE', '0.04'))  # 4% default

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Load stock symbols
    stock_data = CSVHandler.load_stocks(stocks_csv)
    symbols = list(stock_data.keys())

    logger.info(f"\nAnalyzing {len(symbols)} stocks: {', '.join(symbols)}")

    # Initialize analyzer and fetcher
    analyzer = PortfolioAnalyzer(risk_free_rate=risk_free_rate)
    fetcher = get_fetcher()

    # Define analysis period (last 6 months)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')

    logger.info(f"\nAnalysis period: {start_date} to {end_date}")

    # Fetch historical data
    logger.info("\n" + "=" * 80)
    logger.info("Step 1: Fetching Historical Price Data")
    logger.info("=" * 80)

    try:
        prices = analyzer.fetch_historical_data(
            fetcher=fetcher,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            interval='daily'
        )

        logger.info(f"\nSuccessfully fetched {len(prices)} days of price data")
        logger.info(f"Date range: {prices.index[0].strftime('%Y-%m-%d')} to {prices.index[-1].strftime('%Y-%m-%d')}")

        # Save prices to CSV
        prices_file = os.path.join(output_dir, 'historical_prices.csv')
        prices.to_csv(prices_file)
        logger.info(f"Saved historical prices to {prices_file}")

    except Exception as e:
        logger.error(f"Error fetching historical data: {e}")
        logger.info("Continuing with limited analysis based on available data")
        return

    # Calculate returns
    logger.info("\n" + "=" * 80)
    logger.info("Step 2: Calculating Returns")
    logger.info("=" * 80)

    returns = analyzer.calculate_returns(prices, return_type='simple')
    logger.info(f"Calculated returns for {len(returns)} periods")

    # Save returns to CSV
    returns_file = os.path.join(output_dir, 'daily_returns.csv')
    returns.to_csv(returns_file)
    logger.info(f"Saved daily returns to {returns_file}")

    # Calculate correlation matrix
    logger.info("\n" + "=" * 80)
    logger.info("Step 3: Correlation Analysis")
    logger.info("=" * 80)

    correlation = analyzer.calculate_correlation_matrix(returns)

    print("\nCorrelation Matrix (Pearson):")
    print(format_dataframe(correlation))

    # Save correlation matrix to CSV
    correlation_file = os.path.join(output_dir, 'correlation_matrix.csv')
    correlation.to_csv(correlation_file)
    logger.info(f"\nSaved correlation matrix to {correlation_file}")

    # Pairwise correlations (if we have at least 2 stocks)
    if len(symbols) >= 2:
        print("\nPairwise Correlations:")
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                corr = analyzer.calculate_pairwise_correlation(returns, symbols[i], symbols[j])
                print(f"  {symbols[i]} vs {symbols[j]}: {corr:.4f}")

    # Calculate risk metrics
    logger.info("\n" + "=" * 80)
    logger.info("Step 4: Risk Metrics Analysis")
    logger.info("=" * 80)

    # Volatility
    volatility = analyzer.calculate_volatility(returns)
    print("\nAnnualized Volatility (Standard Deviation):")
    for symbol in volatility.index:
        print(f"  {symbol}: {volatility[symbol]:.2%}")

    # Variance
    variance = analyzer.calculate_variance(returns)
    print("\nAnnualized Variance:")
    for symbol in variance.index:
        print(f"  {symbol}: {variance[symbol]:.6f}")

    # Maximum Drawdown
    max_drawdown = analyzer.calculate_max_drawdown(prices)
    print("\nMaximum Drawdown:")
    for symbol in max_drawdown.index:
        print(f"  {symbol}: {max_drawdown[symbol]:.2%}")

    # Calculate risk-return metrics
    logger.info("\n" + "=" * 80)
    logger.info("Step 5: Risk-Return Metrics")
    logger.info("=" * 80)

    # Sharpe Ratio
    sharpe = analyzer.calculate_sharpe_ratio(returns)
    print("\nSharpe Ratio (higher is better):")
    for symbol in sharpe.index:
        print(f"  {symbol}: {sharpe[symbol]:.4f}")

    # Sortino Ratio
    sortino = analyzer.calculate_sortino_ratio(returns)
    print("\nSortino Ratio (higher is better):")
    for symbol in sortino.index:
        print(f"  {symbol}: {sortino[symbol]:.4f}")

    # Value at Risk
    var_95 = analyzer.calculate_value_at_risk(returns, confidence_level=0.95)
    print("\nValue at Risk (95% confidence):")
    for symbol in var_95.index:
        print(f"  {symbol}: {var_95[symbol]:.2%} (5% chance of worse daily loss)")

    # Conditional VaR
    cvar_95 = analyzer.calculate_conditional_var(returns, confidence_level=0.95)
    print("\nConditional VaR / Expected Shortfall (95% confidence):")
    for symbol in cvar_95.index:
        print(f"  {symbol}: {cvar_95[symbol]:.2%} (average loss in worst 5% of days)")

    # Generate comprehensive risk report
    logger.info("\n" + "=" * 80)
    logger.info("Step 6: Comprehensive Risk Report")
    logger.info("=" * 80)

    # For Beta and Alpha, we need a market benchmark
    # Try to fetch SPY (S&P 500) as a market proxy
    try:
        logger.info("\nFetching market benchmark (SPY) for Beta/Alpha calculation...")
        market_prices = analyzer.fetch_historical_data(
            fetcher=fetcher,
            symbols=['SPY'],
            start_date=start_date,
            end_date=end_date,
            interval='daily'
        )
        market_returns = analyzer.calculate_returns(market_prices)['SPY']

        logger.info("Successfully fetched market data")

        # Generate full report with market metrics
        risk_report = analyzer.generate_risk_report(returns, prices, market_returns)

    except Exception as e:
        logger.warning(f"Could not fetch market data: {e}")
        logger.info("Generating report without market-relative metrics (Beta/Alpha)")

        # Generate report without market metrics
        risk_report = analyzer.generate_risk_report(returns, prices, market_returns=None)

    print("\nComprehensive Risk Report:")
    print(format_dataframe(risk_report))

    # Save risk report to CSV
    risk_report_file = os.path.join(output_dir, 'risk_report.csv')
    risk_report.to_csv(risk_report_file)
    logger.info(f"\nSaved comprehensive risk report to {risk_report_file}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Analysis Complete!")
    logger.info("=" * 80)

    print("\nOutput files generated:")
    print(f"  1. {prices_file} - Historical prices")
    print(f"  2. {returns_file} - Daily returns")
    print(f"  3. {correlation_file} - Correlation matrix")
    print(f"  4. {risk_report_file} - Comprehensive risk report")

    print("\nKey Metrics Explanations:")
    print("  • Sharpe Ratio: Risk-adjusted return (>1.0 is good, >2.0 is very good)")
    print("  • Sortino Ratio: Like Sharpe but only considers downside risk")
    print("  • Max Drawdown: Worst peak-to-trough decline (more negative = riskier)")
    print("  • VaR (95%): Maximum expected loss with 95% confidence")
    print("  • CVaR (95%): Average loss in worst 5% of cases")
    print("  • Beta: Volatility vs market (1.0 = same as market, >1.0 = more volatile)")
    print("  • Alpha: Excess return vs expected (>0 = outperforming)")


if __name__ == "__main__":
    main()
