# README.md
# Portfolio Analyzer

A Python-based portfolio analysis tool for tracking stock prices, calculating risk-return metrics, and optimizing asset allocation. Fetches real-time and historical stock data from multiple sources (Yahoo Finance and Polygon.io) with automatic fallback handling and rate limiting. Features include multi-currency support with automatic USD conversion, correlation analysis, portfolio rebalancing strategies, and comprehensive logging.

## Features

- 📈 **Multi-Source Data Fetching**: Yahoo Finance, Polygon.io, and Stooq with automatic fallback
- 💱 **SGD-Base Currency**: All portfolio values computed in SGD (or configurable base currency)
- 📊 **Daily Report**: P&L, YTD, drawdown, macro dashboard, per-ticker news → Markdown + Telegram
- 🔄 **Smart Rate Limiting**: Exponential backoff and intelligent request pacing
- 📉 **Risk Metrics**: Volatility, max drawdown, VaR, CVaR, Sharpe, Sortino, Beta, Alpha
- ⚖️ **Rebalancing**: Band-based rebalancing suggestions (contributions-first)
- 📝 **CSV-Based Configuration**: `universe.csv` (candidates), `holdings.csv` (positions), `targets.csv` (weights)

## Scope

This repo is a **portfolio analysis and daily monitoring** tool. It is intentionally scoped to:
- Portfolio valuation, risk metrics, and allocation math
- Daily report generation and Telegram delivery
- Rebalancing suggestions

**Out of scope (kept separate):** AI/tech research aggregation (Hacker News, arXiv, GitHub Trending
summarization via LLM). That belongs in a dedicated `research_scan.py` script — the concerns are
entirely different and mixing them would bloat this tool's dependency surface.

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
├── INVESTMENT_PLAN.md      # Decision framework driving the roadmap
├── src/                    # Core library code
│   ├── config.py          # Base currency (SGD), exposure caps, rebalance bands
│   ├── fetchers/          # Data fetchers
│   │   ├── base / yfinance / polygon   # price quotes (implemented)
│   │   ├── history.py     # bulk historical OHLC            [stub]
│   │   ├── fx.py          # historical FX → SGD base (§6.5) [stub]
│   │   └── macro.py       # FRED rates/oil/CPI + VIX (§6.5) [stub]
│   ├── analyzers/         # Analysis
│   │   ├── risk_metrics.py # per-asset metrics (implemented)
│   │   ├── portfolio.py   # weighted portfolio math (§6.2)  [stub]
│   │   └── allocation.py  # weighting engines (§6.3)        [stub]
│   ├── rebalancers/       # Band-based rebalancing → trades (§7) [stub]
│   └── utils/             # Shared utilities
├── scripts/               # Executable scripts
├── data/                  # Working CSVs: universe / holdings / targets (gitignored)
├── examples/              # Tracked CSV templates
├── output/                # Generated reports
└── tests/                 # Unit tests
```

> **Data model:** `universe.csv` (candidate metadata: currency, exchange, asset class, broker),
> `holdings.csv` (your positions), `targets.csv` (target weights). Templates live in `examples/`.

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
from src.analyzers import RiskMetrics  # formerly PortfolioAnalyzer (alias kept for compatibility)
from src.fetchers import YFinanceFetcher

# Initialize analyzer
analyzer = RiskMetrics(risk_free_rate=0.04)  # 4% risk-free rate
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

| Variable | Default | Description |
|---|---|---|
| `BASE_CURRENCY` | `SGD` | Base currency for all portfolio values |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token (enables push notifications) |
| `TELEGRAM_CHAT_ID` | — | Telegram chat/channel ID |
| `POLYGON_API_KEY` | — | Polygon.io key (optional, enables Polygon backend) |
| `FRED_API_KEY` | — | FRED key (optional, higher rate limits for macro data) |
| `OUTPUT_DIR` | `output` | Directory for generated reports |
| `LOG_LEVEL` | `INFO` | Logging level |

See `.env.example` for setup instructions including how to find your Telegram chat ID.

## Daily Report & Cron Setup

Run once manually to verify:
```bash
python scripts/daily_report.py
```

To run automatically every day at 8:00 AM:
```bash
crontab -e
```
Add these lines (adjust path to match where you cloned the repo):
```
# Portfolio daily report — 8:00 AM
0 8 * * * cd /path/to/portfolio-analyzer && ~/.venv/bin/python scripts/daily_report.py >> ~/portfolio-reports/daily.log 2>&1
```

Create the log directory first:
```bash
mkdir -p ~/portfolio-reports
```

**Telegram setup** (to get push notifications):
1. Message `@BotFather` on Telegram → `/newbot` → copy the token
2. Start a chat with your new bot
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the `chat.id` value
4. Add both to your `.env` file

## License

MIT License

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.
