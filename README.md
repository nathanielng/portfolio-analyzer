# README.md
# Portfolio Analyzer

A Python-based portfolio analysis tool for tracking stock prices, calculating risk-return metrics, and optimizing asset allocation. Fetches real-time and historical stock data from multiple sources (Yahoo Finance and Polygon.io) with automatic fallback handling and rate limiting. Features include multi-currency support with automatic USD conversion, correlation analysis, portfolio rebalancing strategies, and comprehensive logging.

## Features

- 📈 **Multi-Source Data Fetching**: Yahoo Finance and Polygon.io support with automatic fallback
- 💱 **Currency Conversion**: Automatic USD conversion for international stocks
- 🔄 **Smart Rate Limiting**: Exponential backoff and intelligent request pacing
- 📊 **Portfolio Analysis**: (Coming soon) Correlation, risk-return metrics
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
```python
from scripts.fetch_prices import get_stock_prices

# Fetch recent prices
prices = get_stock_prices()

# Fetch historical prices
prices = get_stock_prices(date='2025-01-03')

# Use specific backend
prices = get_stock_prices(backend='polygon')
```

## Environment Variables

- `POLYGON_API_KEY`: Your Polygon.io API key (optional, enables Polygon backend)
- `STOCKS_CSV`: Path to stocks CSV file (default: `data/stocks.csv`)
- `OUTPUT_FILE`: Output CSV file path (default: `output/stock_prices.csv`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

## License

MIT License

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.