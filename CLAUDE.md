# CLAUDE.md - Development Preferences and Coding Guidelines

## Project Context
This project is a Python-based portfolio analysis tool for tracking stock prices, calculating risk-return metrics, and optimizing asset allocation. The tool fetches data from multiple sources (Yahoo Finance, Polygon.io) with smart fallbacks, rate limiting, and multi-currency support.

## Python Development Preferences

### Package Management
- **Primary tool**: UV for Python package management
- Prefer standard library modules over heavy dependencies when possible
- Example: Use `csv` module instead of `pandas` for simple CSV operations

### Licensing Preferences
- **Strongly prefer permissive licenses**: MIT, Apache 2.0, BSD (2-Clause or 3-Clause)
- **Avoid restrictive licenses**: GPL, AGPL, LGPL (copyleft licenses)
- When choosing dependencies, prioritize packages with permissive licenses
- Check license compatibility before adding new dependencies
- This project uses MIT License for maximum flexibility

**Acceptable licenses (in order of preference):**
1. MIT License (most preferred)
2. Apache License 2.0
3. BSD 2-Clause or 3-Clause License
4. ISC License
5. Python Software Foundation License

**Avoid:**
- GPL (GNU General Public License)
- AGPL (GNU Affero General Public License)
- LGPL (GNU Lesser General Public License)
- Any licenses with copyleft provisions or strong reciprocal requirements

### Code Style & Structure

#### Imports
Follow PEP 8 import organization:
1. Standard library imports (alphabetically sorted)
2. Third-party imports (alphabetically sorted)
3. Local application imports
4. Each group separated by a blank line

Example:
```python
import csv
import logging
import os
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

import requests
import yfinance as yf
from dotenv import load_dotenv

from src.fetchers import PolygonFetcher, YFinanceFetcher
from src.utils import CSVHandler, CurrencyConverter, setup_logger
```

#### Environment Variables & Configuration
- **Always use** `python-dotenv` for environment variable management
- Load with `load_dotenv()` at the start of scripts
- Access with `os.getenv('VAR_NAME', 'default_value')`
- Provide `.env.example` files with clear documentation

Example:
```python
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv('POLYGON_API_KEY')
```

#### Logging
- **Always use** `logging.info()`, `logging.error()`, `logging.warning()`
- Never use `print()` for informational messages in production code
- Configure logging with timestamps and log levels
- Use named loggers for different modules

Example:
```python
import logging

logger = logging.getLogger('portfolio_analyzer.module_name')
logger.info("Processing started")
```

### Error Handling & Resilience

#### Rate Limiting
- Implement exponential backoff for API calls
- Add configurable retry logic (default: 3 retries)
- Include explicit sleep delays between API calls when needed
- Log retry attempts and backoff durations

Example:
```python
def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    delay = min(base_delay * (2 ** attempt), max_delay)
    logging.info(f"Backing off for {delay:.2f} seconds (attempt {attempt + 1})")
    return delay
```

#### API Integration
- Prefer free APIs that don't require API keys
- When API keys are needed, make them optional with clear fallbacks
- Auto-detect which backend to use based on available credentials
- Support multiple backends with graceful fallback mechanisms

### Project Structure

#### Directory Organization
```
portfolio-analyzer/
├── README.md
├── LICENSE (MIT License)
├── requirements.txt
├── .env.example
├── .gitignore
├── setup.py
├── .claude/
│   └── CLAUDE.md      # AI coding guidelines
├── data/              # Input CSV files
├── output/            # Generated reports
├── src/               # Core library code
│   ├── fetchers/      # Data fetching modules
│   ├── analyzers/     # Analysis algorithms
│   ├── rebalancers/   # Portfolio rebalancing
│   └── utils/         # Shared utilities
├── scripts/           # Executable scripts
├── tests/             # Unit tests
├── notebooks/         # Jupyter notebooks
├── docs/              # Documentation
└── examples/          # Sample files
```

#### Module Design
- Separate concerns into focused modules
- Use abstract base classes for common interfaces
- Keep configuration separate from logic
- Store data in CSV files rather than hardcoded dictionaries

### Data Handling

#### CSV Files
- Use CSV files for configuration and data storage
- Include headers in all CSV files
- Use `csv.DictReader` and `csv.DictWriter` for structured access
- Validate CSV data after loading

Example CSV structure:
```csv
Symbol,Company
NVDA,Nvidia
MSFT,Microsoft
```

#### Type Hints
- Use type hints for all function parameters and return values
- Import from `typing` module: `Dict`, `List`, `Optional`, `Tuple`
- Be explicit about optional values with `Optional[type]`

Example:
```python
def fetch_price(self, symbol: str, date: Optional[str] = None) -> Dict:
    """Fetch stock price with optional date parameter."""
    pass
```

### API & External Services

#### Preferred Characteristics
1. Free tier available
2. No API key required (or optional)
3. Reasonable rate limits
4. Well-documented
5. Stable and reliable
6. **Permissive license (MIT, Apache 2.0, BSD)**

#### Current Integrations
- **Yahoo Finance (yfinance)**: Default backend, no API key needed, Apache 2.0 License
- **Polygon.io**: Optional backend with API key, 5 calls/minute free tier
- **exchangerate-api.com**: Currency conversion, free, no API key

#### Backend Selection Logic
```python
# Auto-detect: Polygon if API key exists, otherwise YFinance
if os.getenv('POLYGON_API_KEY'):
    backend = 'polygon'
else:
    backend = 'yfinance'
```

### Documentation Standards

#### Docstrings
- Use Google-style docstrings
- Include Args, Returns, and Raises sections
- Provide usage examples for complex functions

Example:
```python
def get_exchange_rate(from_currency: str, to_currency: str = 'USD', max_retries: int = 3) -> Optional[float]:
    """
    Get exchange rate from one currency to another.
    
    Args:
        from_currency: Source currency code (e.g., 'TWD')
        to_currency: Target currency code (default: 'USD')
        max_retries: Maximum retry attempts
    
    Returns:
        Exchange rate or None if unavailable
    """
    pass
```

#### README Files
- Include clear project description
- List features with emojis for visual appeal
- Provide installation instructions
- Show quick start examples
- Document configuration options
- Include project structure overview

### Features & Functionality Preferences

#### Comprehensive Solutions
- Combine multiple approaches into unified implementations
- Provide feature-rich solutions rather than minimal examples
- Include export/import capabilities
- Support multiple output formats when relevant

#### User Experience
- Create polished, production-ready code
- Add proper error messages with actionable guidance
- Include progress indicators for long operations
- Provide sensible defaults for all configuration

#### Iterative Development
- Expect multiple rounds of refinement
- Be open to aesthetic and UX improvements
- Focus on visual design details
- Support theme switching and customization options

### Testing & Quality

#### Code Quality
- Use meaningful variable names
- Keep functions focused and single-purpose
- Avoid deep nesting
- Handle edge cases explicitly

#### Error Messages
- Provide clear, actionable error messages
- Log errors with context (file paths, API endpoints, etc.)
- Distinguish between warnings and errors
- Never fail silently

### Git & Version Control

#### .gitignore
Always exclude:
- `.env` (sensitive credentials)
- `venv/`, `env/`, `__pycache__/`
- Output files (but keep `.gitkeep` in output directories)
- IDE-specific files (`.vscode/`, `.idea/`)
- OS files (`.DS_Store`, `Thumbs.db`)

#### Repository Naming
- Use lowercase with hyphens: `portfolio-analyzer`
- Choose descriptive names that indicate purpose
- Avoid abbreviations unless widely understood

## Communication & Interaction Style

### Code Explanations
- Explain design decisions and trade-offs
- Highlight key features and improvements
- Point out potential issues or limitations
- Suggest alternatives when relevant

### File Delivery
- Present complete, working code files
- Include all necessary configuration files
- Provide clear file structure
- Show example data and usage

### Verification & Units
- Double-check data units (e.g., currency, exchange rates)
- Verify API response formats
- Confirm assumptions about data sources
- Test edge cases

## Current Project Specifics

### Stock Data Sources
- Primary: Yahoo Finance (yfinance library)
- Fallback: Polygon.io with API key
- Special cases: TSMC (2330.TW) returns prices in TWD, not USD

### Currency Handling
- Always track original currency
- Provide automatic USD conversion option
- Use free exchange rate APIs (exchangerate-api.com)
- Cache exchange rates to minimize API calls

### Expected Workflows
1. Fetch current/historical stock prices
2. Analyze portfolio metrics (correlation, risk-return)
3. Generate rebalancing recommendations
4. Export results to CSV/reports

## LLM Instruction Summary

When working on this project:
1. Use UV-compatible Python packages
2. Prefer standard library over dependencies
3. **Choose dependencies with permissive licenses (MIT, Apache 2.0, BSD)**
4. Always use `logging.info()` instead of `print()`
5. Use `load_dotenv()` and `os.getenv()` for configuration
6. Organize imports according to PEP 8
7. Implement exponential backoff for API calls
8. Provide comprehensive, production-ready solutions
9. Store configuration in CSV files
10. Use type hints throughout
11. Create detailed docstrings
12. Auto-detect backends based on available credentials
13. Handle errors gracefully with informative messages
14. Support both free and paid API tiers
15. Add the project root to Python path in scripts:
```python
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
```

## Example Code Pattern
```python
import logging
import os
from typing import Dict, Optional

from dotenv import load_dotenv

# Add project root to path for imports
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment
load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

def fetch_data(symbol: str, api_key: Optional[str] = None, max_retries: int = 3) -> Dict:
    """
    Fetch data with retry logic and error handling.
    
    Args:
        symbol: Stock symbol to fetch
        api_key: Optional API key (reads from env if not provided)
        max_retries: Maximum retry attempts
    
    Returns:
        Dictionary containing fetched data
    """
    api_key = api_key or os.getenv('API_KEY')
    
    for attempt in range(max_retries):
        try:
            # Fetch logic here
            logger.info(f"Fetching data for {symbol}")
            result = {}
            return result
        except Exception as e:
            logger.error(f"Error fetching {symbol} (attempt {attempt + 1}): {str(e)}")
            if attempt < max_retries - 1:
                # Exponential backoff
                time.sleep(2 ** attempt)
            else:
                raise
```