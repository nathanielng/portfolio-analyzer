# src/analyzers/portfolio_analyzer.py
"""Portfolio analysis and risk metrics calculation."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger('portfolio_analyzer.analyzer')


class PortfolioAnalyzer:
    """
    Analyze portfolio performance, risk metrics, and correlations.

    This class provides comprehensive portfolio analysis including:
    - Correlation analysis between stocks
    - Risk metrics (volatility, variance, standard deviation)
    - Risk-return metrics (Sharpe ratio, Sortino ratio, etc.)
    - Downside risk metrics (Maximum Drawdown, VaR, CVaR)
    """

    def __init__(self, risk_free_rate: float = 0.04):
        """
        Initialize the portfolio analyzer.

        Args:
            risk_free_rate: Annual risk-free rate (default: 4% = 0.04)
        """
        self.risk_free_rate = risk_free_rate

    def fetch_historical_data(
        self,
        fetcher,
        symbols: List[str],
        start_date: str,
        end_date: Optional[str] = None,
        interval: str = 'daily'
    ) -> pd.DataFrame:
        """
        Fetch historical price data for multiple symbols.

        Args:
            fetcher: Price fetcher instance (YFinanceFetcher or PolygonFetcher)
            symbols: List of stock symbols
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format (default: today)
            interval: Data interval - 'daily', 'weekly', or 'monthly'

        Returns:
            DataFrame with dates as index and symbols as columns
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        logger.info(f"Fetching historical data for {len(symbols)} symbols from {start_date} to {end_date}")

        # Generate date range
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        # Determine date interval
        if interval == 'daily':
            delta = timedelta(days=1)
        elif interval == 'weekly':
            delta = timedelta(weeks=1)
        elif interval == 'monthly':
            delta = timedelta(days=30)
        else:
            raise ValueError(f"Invalid interval: {interval}")

        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime('%Y-%m-%d'))
            current += delta

        # Fetch data for each symbol
        price_data = {}

        for symbol in symbols:
            logger.info(f"Fetching historical data for {symbol}")
            symbol_prices = []

            for date in dates:
                try:
                    result = fetcher.fetch_price(symbol, date)
                    price = result.get('price')
                    symbol_prices.append(price)
                except Exception as e:
                    logger.warning(f"Failed to fetch {symbol} for {date}: {e}")
                    symbol_prices.append(None)

            price_data[symbol] = symbol_prices

        # Create DataFrame
        df = pd.DataFrame(price_data, index=pd.to_datetime(dates))

        # Forward fill missing values (use last known price)
        df = df.ffill()

        # Backward fill any remaining NaN at the start
        df = df.bfill()

        logger.info(f"Successfully fetched historical data: {df.shape[0]} dates, {df.shape[1]} symbols")

        return df

    def calculate_returns(
        self,
        prices: pd.DataFrame,
        return_type: str = 'simple'
    ) -> pd.DataFrame:
        """
        Calculate returns from price data.

        Args:
            prices: DataFrame with prices (dates as index, symbols as columns)
            return_type: 'simple' for arithmetic returns or 'log' for logarithmic returns

        Returns:
            DataFrame with returns
        """
        if return_type == 'simple':
            returns = prices.pct_change()
        elif return_type == 'log':
            returns = np.log(prices / prices.shift(1))
        else:
            raise ValueError(f"Invalid return_type: {return_type}")

        # Drop first row (NaN from pct_change)
        returns = returns.dropna()

        return returns

    def calculate_correlation_matrix(
        self,
        returns: pd.DataFrame,
        method: str = 'pearson'
    ) -> pd.DataFrame:
        """
        Calculate correlation matrix between all stocks.

        Args:
            returns: DataFrame with returns (dates as index, symbols as columns)
            method: Correlation method - 'pearson', 'kendall', or 'spearman'

        Returns:
            Correlation matrix as DataFrame

        Explanation:
            The correlation matrix shows how stock returns move together.
            Values range from -1 to 1:
            - 1.0: Perfect positive correlation (stocks move together)
            - 0.0: No correlation (stocks move independently)
            - -1.0: Perfect negative correlation (stocks move opposite)
        """
        correlation = returns.corr(method=method)

        logger.info(f"Calculated {method} correlation matrix for {len(returns.columns)} symbols")

        return correlation

    def calculate_pairwise_correlation(
        self,
        returns: pd.DataFrame,
        symbol1: str,
        symbol2: str,
        method: str = 'pearson'
    ) -> float:
        """
        Calculate correlation between two specific stocks.

        Args:
            returns: DataFrame with returns
            symbol1: First stock symbol
            symbol2: Second stock symbol
            method: Correlation method - 'pearson', 'kendall', or 'spearman'

        Returns:
            Correlation coefficient
        """
        if symbol1 not in returns.columns or symbol2 not in returns.columns:
            raise ValueError(f"Symbols not found in returns data")

        correlation = returns[symbol1].corr(returns[symbol2], method=method)

        logger.info(f"Correlation between {symbol1} and {symbol2}: {correlation:.4f}")

        return correlation

    def calculate_volatility(
        self,
        returns: pd.DataFrame,
        annualize: bool = True,
        trading_days: int = 252
    ) -> pd.Series:
        """
        Calculate volatility (standard deviation of returns).

        Args:
            returns: DataFrame with returns
            annualize: Whether to annualize the volatility
            trading_days: Number of trading days per year (default: 252)

        Returns:
            Series with volatility for each symbol

        Explanation:
            Volatility measures the dispersion of returns around the mean.
            Higher volatility indicates higher risk and price fluctuations.
            Annualized volatility allows comparison across different time periods.
        """
        volatility = returns.std()

        if annualize:
            volatility = volatility * np.sqrt(trading_days)

        logger.info(f"Calculated volatility for {len(returns.columns)} symbols")

        return volatility

    def calculate_variance(
        self,
        returns: pd.DataFrame,
        annualize: bool = True,
        trading_days: int = 252
    ) -> pd.Series:
        """
        Calculate variance of returns.

        Args:
            returns: DataFrame with returns
            annualize: Whether to annualize the variance
            trading_days: Number of trading days per year (default: 252)

        Returns:
            Series with variance for each symbol

        Explanation:
            Variance is the squared standard deviation, measuring the average
            squared deviation from the mean return. It's used in portfolio
            optimization and risk calculations.
        """
        variance = returns.var()

        if annualize:
            variance = variance * trading_days

        logger.info(f"Calculated variance for {len(returns.columns)} symbols")

        return variance

    def calculate_sharpe_ratio(
        self,
        returns: pd.DataFrame,
        risk_free_rate: Optional[float] = None,
        trading_days: int = 252
    ) -> pd.Series:
        """
        Calculate Sharpe ratio for each stock.

        Args:
            returns: DataFrame with returns
            risk_free_rate: Annual risk-free rate (default: uses instance rate)
            trading_days: Number of trading days per year (default: 252)

        Returns:
            Series with Sharpe ratio for each symbol

        Explanation:
            The Sharpe ratio measures risk-adjusted return, calculated as:
            (Return - Risk-Free Rate) / Standard Deviation

            Higher Sharpe ratio indicates better risk-adjusted performance.
            - Sharpe > 1.0: Good risk-adjusted return
            - Sharpe > 2.0: Very good risk-adjusted return
            - Sharpe > 3.0: Excellent risk-adjusted return

            It answers: "How much extra return do I get per unit of risk?"
        """
        if risk_free_rate is None:
            risk_free_rate = self.risk_free_rate

        # Calculate annualized return
        mean_return = returns.mean() * trading_days

        # Calculate annualized volatility
        volatility = returns.std() * np.sqrt(trading_days)

        # Calculate Sharpe ratio
        sharpe = (mean_return - risk_free_rate) / volatility

        logger.info(f"Calculated Sharpe ratio for {len(returns.columns)} symbols")

        return sharpe

    def calculate_sortino_ratio(
        self,
        returns: pd.DataFrame,
        risk_free_rate: Optional[float] = None,
        trading_days: int = 252
    ) -> pd.Series:
        """
        Calculate Sortino ratio for each stock.

        Args:
            returns: DataFrame with returns
            risk_free_rate: Annual risk-free rate (default: uses instance rate)
            trading_days: Number of trading days per year (default: 252)

        Returns:
            Series with Sortino ratio for each symbol

        Explanation:
            The Sortino ratio is similar to the Sharpe ratio but only considers
            downside volatility (negative returns), calculated as:
            (Return - Risk-Free Rate) / Downside Deviation

            This is more appropriate than Sharpe ratio because investors only
            care about downside risk, not upside volatility.

            Higher Sortino ratio indicates better downside risk-adjusted returns.
            - Sortino > 1.0: Good downside risk-adjusted return
            - Sortino > 2.0: Very good downside risk-adjusted return
        """
        if risk_free_rate is None:
            risk_free_rate = self.risk_free_rate

        # Calculate annualized return
        mean_return = returns.mean() * trading_days

        # Calculate downside deviation (only negative returns)
        downside_returns = returns.copy()
        downside_returns[downside_returns > 0] = 0
        downside_deviation = downside_returns.std() * np.sqrt(trading_days)

        # Calculate Sortino ratio
        sortino = (mean_return - risk_free_rate) / downside_deviation

        logger.info(f"Calculated Sortino ratio for {len(returns.columns)} symbols")

        return sortino

    def calculate_max_drawdown(
        self,
        prices: pd.DataFrame
    ) -> pd.Series:
        """
        Calculate maximum drawdown for each stock.

        Args:
            prices: DataFrame with prices (dates as index, symbols as columns)

        Returns:
            Series with maximum drawdown for each symbol

        Explanation:
            Maximum Drawdown (MDD) measures the largest peak-to-trough decline
            in the stock price. It shows the worst-case loss an investor would
            have experienced during the period.

            MDD is expressed as a negative percentage:
            - MDD of -20% means the stock fell 20% from its peak
            - MDD of -50% means the stock fell 50% from its peak

            Lower (more negative) values indicate higher risk. This metric is
            crucial for understanding the worst-case scenario and potential
            recovery time needed.
        """
        # Calculate cumulative maximum
        cumulative_max = prices.cummax()

        # Calculate drawdown
        drawdown = (prices - cumulative_max) / cumulative_max

        # Get maximum drawdown (most negative value)
        max_drawdown = drawdown.min()

        logger.info(f"Calculated maximum drawdown for {len(prices.columns)} symbols")

        return max_drawdown

    def calculate_value_at_risk(
        self,
        returns: pd.DataFrame,
        confidence_level: float = 0.95,
        method: str = 'historical'
    ) -> pd.Series:
        """
        Calculate Value at Risk (VaR) for each stock.

        Args:
            returns: DataFrame with returns
            confidence_level: Confidence level (default: 0.95 for 95% VaR)
            method: 'historical' or 'parametric' (assumes normal distribution)

        Returns:
            Series with VaR for each symbol

        Explanation:
            Value at Risk (VaR) estimates the maximum loss expected over a given
            time period at a specific confidence level.

            For example, a 95% VaR of -2% means:
            "There is a 95% probability that the daily loss will not exceed 2%"
            Or equivalently: "There is a 5% chance of losing more than 2% in a day"

            Methods:
            - Historical VaR: Uses actual historical return distribution
            - Parametric VaR: Assumes returns follow a normal distribution

            VaR is widely used in risk management and regulatory reporting.
        """
        if method == 'historical':
            # Use historical percentile
            var = returns.quantile(1 - confidence_level)
        elif method == 'parametric':
            # Assume normal distribution
            from scipy import stats
            z_score = stats.norm.ppf(1 - confidence_level)
            var = returns.mean() + z_score * returns.std()
        else:
            raise ValueError(f"Invalid method: {method}")

        logger.info(f"Calculated {confidence_level*100}% VaR using {method} method")

        return var

    def calculate_conditional_var(
        self,
        returns: pd.DataFrame,
        confidence_level: float = 0.95
    ) -> pd.Series:
        """
        Calculate Conditional Value at Risk (CVaR) for each stock.

        Args:
            returns: DataFrame with returns
            confidence_level: Confidence level (default: 0.95 for 95% CVaR)

        Returns:
            Series with CVaR for each symbol

        Explanation:
            Conditional Value at Risk (CVaR), also known as Expected Shortfall,
            measures the average loss in the worst (1 - confidence_level) cases.

            For example, a 95% CVaR of -3% means:
            "In the worst 5% of cases, the average loss is 3%"

            CVaR is superior to VaR because:
            1. It considers the severity of losses beyond VaR
            2. It provides information about tail risk
            3. It's more conservative and better for risk management

            CVaR is always worse (more negative) than VaR at the same confidence level.
        """
        # Calculate VaR threshold
        var_threshold = returns.quantile(1 - confidence_level)

        # Calculate CVaR (mean of returns below VaR threshold)
        cvar = pd.Series(index=returns.columns, dtype=float)

        for symbol in returns.columns:
            symbol_returns = returns[symbol]
            tail_returns = symbol_returns[symbol_returns <= var_threshold[symbol]]
            cvar[symbol] = tail_returns.mean() if len(tail_returns) > 0 else var_threshold[symbol]

        logger.info(f"Calculated {confidence_level*100}% CVaR for {len(returns.columns)} symbols")

        return cvar

    def calculate_beta(
        self,
        returns: pd.DataFrame,
        market_returns: pd.Series,
        symbol: Optional[str] = None
    ) -> pd.Series:
        """
        Calculate Beta relative to a market index.

        Args:
            returns: DataFrame with stock returns
            market_returns: Series with market/benchmark returns
            symbol: Specific symbol to calculate (default: all symbols)

        Returns:
            Series with Beta for each symbol (or single value if symbol specified)

        Explanation:
            Beta measures a stock's volatility relative to the overall market.
            It's calculated as: Covariance(Stock, Market) / Variance(Market)

            Interpretation:
            - Beta = 1.0: Stock moves in line with the market
            - Beta > 1.0: Stock is more volatile than the market (amplified moves)
            - Beta < 1.0: Stock is less volatile than the market (dampened moves)
            - Beta = 0.0: Stock is uncorrelated with the market
            - Beta < 0.0: Stock moves opposite to the market (rare)

            Examples:
            - Beta = 1.5: If market goes up 10%, stock typically goes up 15%
            - Beta = 0.5: If market goes up 10%, stock typically goes up 5%
        """
        symbols_to_calc = [symbol] if symbol else returns.columns

        beta = pd.Series(index=symbols_to_calc, dtype=float)

        for sym in symbols_to_calc:
            if sym not in returns.columns:
                raise ValueError(f"Symbol {sym} not found in returns")

            # Calculate covariance and variance
            covariance = returns[sym].cov(market_returns)
            market_variance = market_returns.var()

            beta[sym] = covariance / market_variance

        logger.info(f"Calculated Beta for {len(symbols_to_calc)} symbols")

        return beta

    def calculate_alpha(
        self,
        returns: pd.DataFrame,
        market_returns: pd.Series,
        risk_free_rate: Optional[float] = None,
        trading_days: int = 252,
        symbol: Optional[str] = None
    ) -> pd.Series:
        """
        Calculate Alpha (Jensen's Alpha) relative to a market index.

        Args:
            returns: DataFrame with stock returns
            market_returns: Series with market/benchmark returns
            risk_free_rate: Annual risk-free rate (default: uses instance rate)
            trading_days: Number of trading days per year (default: 252)
            symbol: Specific symbol to calculate (default: all symbols)

        Returns:
            Series with annualized Alpha for each symbol

        Explanation:
            Alpha measures a stock's excess return relative to what would be
            expected given its Beta (market risk). It's calculated as:
            Alpha = Actual Return - [Risk-Free Rate + Beta × (Market Return - Risk-Free Rate)]

            Interpretation:
            - Alpha > 0: Stock outperformed expectations (good stock picking)
            - Alpha = 0: Stock performed as expected given its risk
            - Alpha < 0: Stock underperformed expectations (poor performance)

            Alpha represents the value added by active management or stock selection.
            - Alpha of +2% means the stock beat the market by 2% annually
            - Alpha of -1% means the stock underperformed by 1% annually

            This is a key metric for evaluating fund managers and investment strategies.
        """
        if risk_free_rate is None:
            risk_free_rate = self.risk_free_rate

        symbols_to_calc = [symbol] if symbol else returns.columns

        # Calculate Beta first
        beta = self.calculate_beta(returns, market_returns)

        # Calculate annualized returns
        stock_returns = returns[symbols_to_calc].mean() * trading_days
        market_return = market_returns.mean() * trading_days

        # Calculate Alpha using CAPM
        expected_return = risk_free_rate + beta * (market_return - risk_free_rate)
        alpha = stock_returns - expected_return

        logger.info(f"Calculated Alpha for {len(symbols_to_calc)} symbols")

        return alpha

    def calculate_information_ratio(
        self,
        returns: pd.DataFrame,
        benchmark_returns: pd.Series,
        trading_days: int = 252
    ) -> pd.Series:
        """
        Calculate Information Ratio for each stock.

        Args:
            returns: DataFrame with stock returns
            benchmark_returns: Series with benchmark returns
            trading_days: Number of trading days per year (default: 252)

        Returns:
            Series with Information Ratio for each symbol

        Explanation:
            The Information Ratio (IR) measures risk-adjusted returns relative
            to a benchmark, calculated as:
            IR = (Portfolio Return - Benchmark Return) / Tracking Error

            Where Tracking Error is the standard deviation of the difference
            between portfolio and benchmark returns.

            Interpretation:
            - IR > 0.5: Good active management
            - IR > 1.0: Excellent active management
            - IR < 0: Underperforming the benchmark

            Unlike Sharpe ratio (which uses risk-free rate), IR measures
            performance relative to a specific benchmark, making it ideal
            for evaluating active fund managers.

            Higher IR means more consistent outperformance of the benchmark.
        """
        # Calculate excess returns
        excess_returns = returns.subtract(benchmark_returns, axis=0)

        # Calculate annualized excess return
        mean_excess = excess_returns.mean() * trading_days

        # Calculate tracking error (annualized)
        tracking_error = excess_returns.std() * np.sqrt(trading_days)

        # Calculate Information Ratio
        information_ratio = mean_excess / tracking_error

        logger.info(f"Calculated Information Ratio for {len(returns.columns)} symbols")

        return information_ratio

    def generate_risk_report(
        self,
        returns: pd.DataFrame,
        prices: pd.DataFrame,
        market_returns: Optional[pd.Series] = None
    ) -> pd.DataFrame:
        """
        Generate a comprehensive risk analysis report.

        Args:
            returns: DataFrame with returns
            prices: DataFrame with prices
            market_returns: Optional market/benchmark returns for Beta/Alpha

        Returns:
            DataFrame with all risk metrics for each symbol
        """
        logger.info("Generating comprehensive risk report")

        report = pd.DataFrame(index=returns.columns)

        # Basic statistics
        report['Mean Return (Annual)'] = returns.mean() * 252
        report['Volatility (Annual)'] = self.calculate_volatility(returns)
        report['Variance (Annual)'] = self.calculate_variance(returns)

        # Risk-adjusted metrics
        report['Sharpe Ratio'] = self.calculate_sharpe_ratio(returns)
        report['Sortino Ratio'] = self.calculate_sortino_ratio(returns)

        # Downside risk metrics
        report['Max Drawdown'] = self.calculate_max_drawdown(prices)
        report['VaR (95%)'] = self.calculate_value_at_risk(returns, 0.95)
        report['CVaR (95%)'] = self.calculate_conditional_var(returns, 0.95)

        # Market-relative metrics (if market returns provided)
        if market_returns is not None:
            report['Beta'] = self.calculate_beta(returns, market_returns)
            report['Alpha (Annual)'] = self.calculate_alpha(returns, market_returns)
            report['Information Ratio'] = self.calculate_information_ratio(returns, market_returns)

        logger.info(f"Generated risk report for {len(report)} symbols")

        return report
