# README.md
# Portfolio Analyzer

A Python-based portfolio analysis tool for tracking stock prices, calculating risk-return metrics, and optimizing asset allocation. Fetches real-time and historical stock data from multiple sources (Yahoo Finance and Polygon.io) with automatic fallback handling and rate limiting. Features include multi-currency support with automatic USD conversion, correlation analysis, portfolio rebalancing strategies, and comprehensive logging.

## Features

- 📈 **Multi-Source Data Fetching**: Yahoo Finance and Polygon.io support with automatic fallback
- 💱 **Currency Conversion**: Automatic USD conversion for international stocks
- 🔄 **Smart Rate Limiting**: Exponential backoff and intelligent request pacing
- 📊 **Portfolio Analysis**: Correlation matrices, risk metrics, and comprehensive risk reports
- 📉 **Risk Metrics**: Volatility, variance, maximum drawdown, VaR, and CVaR
- 📈 **Risk-Return Metrics**: Sharpe ratio, Sortino ratio, Beta, Alpha, and Information ratio
- ⚖️ **Rebalancing Tools**: (Coming soon) Target allocation and risk parity strategies
- 🪵 **Comprehensive Logging**: Detailed logging for debugging and monitoring
- 📝 **CSV-Based Configuration**: Simple CSV files for portfolio management

## Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/portfolio-analyzer.git
cd portfolio-analyzer

# Install dependencies
pip install -r requirements.txt.    # if using pip
uv pip install -r requirements.txt  # if using uv

# Copy environment example and configure
cp .env.example .env
# Edit .env with your API keys (optional for Polygon.io)
```

## Quick Start
```bash
# Fetch current stock prices
python scripts/fetch_prices.py

# Run comprehensive portfolio analysis
python scripts/analyze_portfolio.py
```

## Project Structure
```
portfolio-analyzer/
├── src/                    # Core library code
│   ├── fetchers/          # Stock price fetchers
│   ├── analyzers/         # Portfolio analysis tools
│   ├── rebalancers/       # Rebalancing algorithms
│   └── utils/             # Shared utilities
├── scripts/               # Executable scripts
├── data/                  # Input CSV files
├── output/                # Generated reports
└── tests/                 # Unit tests
```

## Configuration

Edit `data/stocks.csv` to add or remove stocks from your portfolio:
```csv
Symbol,Company
NVDA,Nvidia
MSFT,Microsoft
2330.TW,Taiwan Semiconductor Manufacturing Co Ltd
```

## Usage

### Fetching Stock Prices
```python
from scripts.fetch_prices import get_stock_prices

# Fetch recent prices
prices = get_stock_prices()

# Fetch historical prices
prices = get_stock_prices(date='2025-01-03')

# Use specific backend
prices = get_stock_prices(backend='polygon')
```

**Note**: Stock prices are now saved with dates in `yyyymmdd` format (e.g., `20250103`) in the output CSV file.

### Portfolio Analysis

The portfolio analyzer provides comprehensive analysis capabilities:

```python
from src.analyzers import PortfolioAnalyzer
from src.fetchers import YFinanceFetcher

# Initialize analyzer
analyzer = PortfolioAnalyzer(risk_free_rate=0.04)  # 4% risk-free rate
fetcher = YFinanceFetcher()

# Fetch historical data
prices = analyzer.fetch_historical_data(
    fetcher=fetcher,
    symbols=['AAPL', 'MSFT', 'GOOGL'],
    start_date='2024-01-01',
    end_date='2025-01-03'
)

# Calculate returns
returns = analyzer.calculate_returns(prices)

# Correlation analysis
correlation_matrix = analyzer.calculate_correlation_matrix(returns)
pairwise_corr = analyzer.calculate_pairwise_correlation(returns, 'AAPL', 'MSFT')

# Risk metrics
volatility = analyzer.calculate_volatility(returns)
variance = analyzer.calculate_variance(returns)
max_drawdown = analyzer.calculate_max_drawdown(prices)

# Risk-return metrics
sharpe_ratio = analyzer.calculate_sharpe_ratio(returns)
sortino_ratio = analyzer.calculate_sortino_ratio(returns)
var_95 = analyzer.calculate_value_at_risk(returns, confidence_level=0.95)
cvar_95 = analyzer.calculate_conditional_var(returns, confidence_level=0.95)

# Market-relative metrics (requires market benchmark)
beta = analyzer.calculate_beta(returns, market_returns)
alpha = analyzer.calculate_alpha(returns, market_returns)
info_ratio = analyzer.calculate_information_ratio(returns, benchmark_returns)

# Generate comprehensive report
risk_report = analyzer.generate_risk_report(returns, prices, market_returns)
```

### Available Risk Metrics

#### Basic Risk Metrics
- **Volatility (Standard Deviation)**: Measures price fluctuation intensity
- **Variance**: Squared standard deviation, used in portfolio optimization
- **Maximum Drawdown**: Worst peak-to-trough decline during the period

#### Risk-Adjusted Return Metrics
- **Sharpe Ratio**: Return per unit of total risk (>1.0 is good, >2.0 is excellent)
- **Sortino Ratio**: Return per unit of downside risk (better than Sharpe for evaluating downside)
- **Information Ratio**: Return per unit of tracking error vs benchmark

#### Downside Risk Metrics
- **Value at Risk (VaR)**: Maximum expected loss at a given confidence level
- **Conditional VaR (CVaR)**: Average loss in the worst-case scenarios

#### Market-Relative Metrics
- **Beta**: Volatility relative to market (1.0 = market volatility, >1.0 = more volatile)
- **Alpha**: Excess return vs expected return given Beta (>0 = outperforming)

### Output Files

Running `analyze_portfolio.py` generates the following CSV files in the `output/` directory:

1. **historical_prices.csv**: Historical price data for all stocks
2. **daily_returns.csv**: Calculated daily returns
3. **correlation_matrix.csv**: Correlation matrix showing relationships between stocks
4. **risk_report.csv**: Comprehensive risk metrics for all stocks

## Environment Variables

- `POLYGON_API_KEY`: Your Polygon.io API key (optional, enables Polygon backend)
- `STOCKS_CSV`: Path to stocks CSV file (default: `data/stocks.csv`)
- `OUTPUT_FILE`: Output CSV file path (default: `output/stock_prices.csv`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

## License

MIT License

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.