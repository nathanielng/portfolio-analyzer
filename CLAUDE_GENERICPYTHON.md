# CLAUDE.md - Development Preferences and Coding Guidelines

## Project Context
This is a Python project following modern development practices with emphasis on clean code, maintainability, and production-ready implementations.

## Python Development Preferences

### Package Management
- **Primary tool**: UV for Python package management
- Prefer standard library modules over heavy dependencies when possible
- Only add external dependencies when they provide significant value
- Example: Use `csv` module instead of `pandas` for simple CSV operations

### Licensing Preferences
- **Strongly prefer permissive licenses**: MIT, Apache 2.0, BSD (2-Clause or 3-Clause)
- **Avoid restrictive licenses**: GPL, AGPL, LGPL (copyleft licenses)
- When choosing dependencies, prioritize packages with permissive licenses
- Check license compatibility before adding new dependencies
- Default to MIT License for new projects unless specific requirements dictate otherwise

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
from dotenv import load_dotenv

from src.module_name import SomeClass
from src.utils import helper_function
```

#### Environment Variables & Configuration
- **Always use** `python-dotenv` for environment variable management
- Load with `load_dotenv()` at the start of scripts
- Access with `os.getenv('VAR_NAME', 'default_value')`
- Provide `.env.example` files with clear documentation
- Never hardcode credentials or configuration values

Example:
```python
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv('API_KEY')
debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
```

#### Logging
- **Always use** `logging.info()`, `logging.error()`, `logging.warning()`
- Never use `print()` for informational messages in production code
- Configure logging with timestamps and log levels
- Use named loggers for different modules
- Make log levels configurable via environment variables

Example:
```python
import logging

logger = logging.getLogger(__name__)
logger.info("Processing started")
logger.error("An error occurred", exc_info=True)
```

### Error Handling & Resilience

#### Retry Logic & Rate Limiting
- Implement exponential backoff for external service calls
- Add configurable retry logic (default: 3 retries)
- Include explicit delays between requests when needed
- Log retry attempts and backoff durations
- Handle rate limiting gracefully

Example:
```python
def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """Calculate exponential backoff delay."""
    delay = min(base_delay * (2 ** attempt), max_delay)
    logging.info(f"Backing off for {delay:.2f} seconds (attempt {attempt + 1})")
    return delay

def retry_with_backoff(func, max_retries: int = 3, *args, **kwargs):
    """Retry a function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                delay = exponential_backoff(attempt)
                time.sleep(delay)
            else:
                raise
```

#### External Service Integration
- Prefer free APIs/services when available
- Make API keys optional with clear fallbacks
- Auto-detect configuration based on available credentials
- Support multiple backends/providers with graceful fallback
- Validate responses before processing
- Cache responses when appropriate

### Project Structure

#### Directory Organization
```
project-name/
├── README.md
├── LICENSE (MIT License recommended)
├── requirements.txt
├── .env.example
├── .gitignore
├── setup.py or pyproject.toml
├── .claude/
│   └── CLAUDE.md          # AI coding guidelines
├── data/                  # Input data files (optional)
├── output/                # Generated output (optional)
├── src/                   # Core library code
│   ├── __init__.py
│   ├── module1/
│   │   ├── __init__.py
│   │   └── core.py
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── config.py
├── scripts/               # Executable scripts
├── tests/                 # Unit and integration tests
│   ├── __init__.py
│   ├── test_module1.py
│   └── conftest.py
├── notebooks/             # Jupyter notebooks (if applicable)
├── docs/                  # Documentation
└── examples/              # Example usage files
```

#### Module Design Principles
- Separation of concerns: each module has a single, well-defined purpose
- Use abstract base classes for common interfaces
- Keep configuration separate from business logic
- Make modules independently testable
- Avoid circular dependencies
- Use dependency injection where appropriate

#### Scripts Directory Pattern
Add project root to Python path in standalone scripts:
```python
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.module_name import function_name
```

### Data Handling

#### File I/O Best Practices
- Use context managers (`with` statements) for file operations
- Specify encoding explicitly (usually `utf-8`)
- Validate file existence before reading
- Create output directories if they don't exist
- Use pathlib for cross-platform path handling

Example:
```python
from pathlib import Path

def read_file(filepath: str) -> str:
    """Read file content with proper error handling."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    with path.open('r', encoding='utf-8') as f:
        return f.read()
```

#### CSV Handling
- Use `csv.DictReader` and `csv.DictWriter` for structured data
- Include headers in all CSV files
- Validate CSV structure after loading
- Handle missing/malformed data gracefully

#### Type Hints
- Use type hints for all function parameters and return values
- Import from `typing` module: `Dict`, `List`, `Optional`, `Tuple`, `Union`
- Be explicit about optional values with `Optional[type]`
- Use `Any` sparingly and only when truly necessary
- Consider using `TypedDict` for complex dictionaries

Example:
```python
from typing import Dict, List, Optional, Union

def process_data(
    items: List[Dict[str, Union[str, int]]],
    filter_key: Optional[str] = None
) -> Dict[str, List[str]]:
    """Process items with optional filtering."""
    pass
```

### Documentation Standards

#### Docstrings
- Use Google-style or NumPy-style docstrings consistently
- Include Args, Returns, Raises, and Examples sections
- Provide usage examples for complex functions
- Document all public APIs
- Keep docstrings up-to-date with code changes

Example:
```python
def calculate_metric(data: List[float], method: str = 'mean') -> float:
    """
    Calculate a statistical metric from data.
    
    Args:
        data: List of numeric values to process
        method: Calculation method ('mean', 'median', 'mode')
    
    Returns:
        Calculated metric value
    
    Raises:
        ValueError: If method is not recognized or data is empty
    
    Examples:
        >>> calculate_metric([1, 2, 3, 4, 5], method='mean')
        3.0
        >>> calculate_metric([1, 2, 3, 4, 5], method='median')
        3.0
    """
    pass
```

#### README Files
- Include clear project description and purpose
- List key features (use emojis for visual appeal)
- Provide installation instructions
- Show quick start/usage examples
- Document configuration options
- Include project structure overview
- Add badges for build status, coverage, etc.
- Link to detailed documentation

#### Code Comments
- Write self-documenting code with clear variable/function names
- Use comments to explain "why", not "what"
- Comment complex algorithms or non-obvious logic
- Keep comments up-to-date with code
- Avoid redundant comments

### Testing & Quality

#### Testing Strategy
- Write tests for all public APIs
- Aim for high test coverage (>80%)
- Use pytest as the testing framework
- Organize tests to mirror source structure
- Include unit tests, integration tests, and end-to-end tests
- Use fixtures for common test setup
- Mock external services in tests

Example test structure:
```python
import pytest
from src.module import function_to_test

def test_function_basic():
    """Test basic functionality."""
    result = function_to_test(input_data)
    assert result == expected_output

def test_function_edge_case():
    """Test edge case handling."""
    with pytest.raises(ValueError):
        function_to_test(invalid_input)

@pytest.fixture
def sample_data():
    """Provide sample data for tests."""
    return {"key": "value"}
```

#### Code Quality
- Use meaningful, descriptive variable names
- Keep functions focused and single-purpose (max 50 lines)
- Avoid deep nesting (max 3-4 levels)
- Handle edge cases explicitly
- Follow DRY (Don't Repeat Yourself) principle
- Use constants for magic numbers and strings
- Consider using a linter (ruff, pylint, flake8)
- Consider using a formatter (black, ruff format)

#### Error Handling
- Provide clear, actionable error messages
- Log errors with sufficient context
- Distinguish between warnings and errors
- Never fail silently (always log or raise)
- Use specific exception types
- Clean up resources in finally blocks or with context managers

Example:
```python
def process_file(filepath: str) -> Dict:
    """Process file with comprehensive error handling."""
    try:
        logger.info(f"Processing file: {filepath}")
        with open(filepath, 'r') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {str(e)}")
        raise ValueError(f"File {filepath} contains invalid JSON") from e
    except Exception as e:
        logger.error(f"Unexpected error processing {filepath}: {str(e)}", exc_info=True)
        raise
```

### Git & Version Control

#### .gitignore
Always exclude:
- `.env` (sensitive credentials)
- `venv/`, `env/`, `.venv/`, `__pycache__/`, `*.pyc`
- Build artifacts: `dist/`, `build/`, `*.egg-info/`
- Output files (but keep `.gitkeep` in output directories)
- IDE-specific files (`.vscode/`, `.idea/`, `*.swp`)
- OS files (`.DS_Store`, `Thumbs.db`)
- Coverage reports: `.coverage`, `htmlcov/`
- Jupyter checkpoints: `.ipynb_checkpoints/`

#### Commit Messages
- Use conventional commits format: `type(scope): description`
- Types: feat, fix, docs, style, refactor, test, chore
- Keep first line under 50 characters
- Provide detailed description in body when needed
- Reference issue numbers when applicable

Example:
```
feat(api): add retry logic with exponential backoff

Implemented configurable retry mechanism for API calls with
exponential backoff to handle transient failures gracefully.

Closes #123
```

#### Repository Naming
- Use lowercase with hyphens: `project-name`
- Choose descriptive names that indicate purpose
- Avoid abbreviations unless widely understood
- Keep names concise but meaningful

### Development Workflow

#### Feature Development
1. Create feature branch from main: `git checkout -b feature/feature-name`
2. Implement feature with tests
3. Ensure all tests pass
4. Update documentation
5. Create pull request with clear description
6. Address code review feedback
7. Merge when approved

#### Code Review Checklist
- [ ] Code follows style guidelines
- [ ] All tests pass
- [ ] New features have tests
- [ ] Documentation is updated
- [ ] No hardcoded credentials or sensitive data
- [ ] Error handling is comprehensive
- [ ] Logging is appropriate
- [ ] Performance considerations addressed

### Features & Functionality Preferences

#### Solution Design
- Provide comprehensive, production-ready solutions
- Combine multiple approaches into unified implementations
- Include proper error handling from the start
- Support configuration via environment variables
- Make solutions extensible and maintainable

#### User Experience
- Provide sensible defaults for all configuration
- Add clear error messages with actionable guidance
- Include progress indicators for long operations
- Support both CLI and programmatic usage where appropriate
- Consider adding `--verbose` and `--quiet` flags for scripts

#### Performance Considerations
- Profile code for bottlenecks before optimizing
- Use appropriate data structures (sets for membership, dicts for lookups)
- Cache expensive computations when appropriate
- Consider lazy evaluation for large datasets
- Use generators for memory-efficient iteration
- Document performance characteristics (time/space complexity)

### Security Best Practices

#### Credential Management
- Never commit credentials to version control
- Use environment variables for all secrets
- Provide `.env.example` with placeholder values
- Consider using secrets management tools for production
- Rotate credentials regularly

#### Input Validation
- Validate all external input (user input, API responses, file content)
- Sanitize data before processing
- Use parameterized queries for databases
- Avoid `eval()` and `exec()` with untrusted input
- Implement rate limiting for public APIs

#### Dependencies
- Keep dependencies up-to-date
- Review dependency licenses
- Use virtual environments to isolate dependencies
- Consider using `pip-audit` or similar tools to check for vulnerabilities
- Pin versions in `requirements.txt` for reproducibility

## Communication & Interaction Style

### Code Explanations
- Explain design decisions and trade-offs
- Highlight key features and improvements
- Point out potential issues or limitations
- Suggest alternatives when relevant
- Provide context for non-obvious implementations

### File Delivery
- Present complete, working code files
- Include all necessary configuration files
- Provide clear file structure
- Show example usage and data
- Include installation and setup instructions

### Iterative Development
- Welcome feedback and refinement requests
- Be open to aesthetic and UX improvements
- Consider edge cases and error scenarios
- Validate assumptions with user
- Provide progressive enhancement suggestions

## LLM Instruction Summary

When working on Python projects following these guidelines:

1. **Environment & Setup**
   - Use UV for package management
   - Use `python-dotenv` and `os.getenv()` for configuration
   - Prefer standard library over external dependencies
   - Choose dependencies with permissive licenses (MIT, Apache 2.0, BSD)

2. **Code Quality**
   - Organize imports according to PEP 8
   - Use type hints throughout
   - Always use `logging` instead of `print()` for informational output
   - Create comprehensive docstrings
   - Write meaningful variable and function names

3. **Error Handling**
   - Implement exponential backoff for external calls
   - Provide clear, actionable error messages
   - Handle edge cases explicitly
   - Never fail silently

4. **Project Structure**
   - Follow the recommended directory layout
   - Separate concerns into focused modules
   - Use abstract base classes for interfaces
   - Add project root to path in scripts:
```python
     import sys
     import os
     sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
```

5. **Testing & Documentation**
   - Write tests for all public APIs
   - Keep documentation up-to-date
   - Provide usage examples
   - Include clear README files

6. **Security & Best Practices**
   - Never hardcode credentials
   - Validate all external input
   - Use context managers for resources
   - Handle cleanup in finally blocks

## Example Code Pattern
```python
"""
Module for doing something useful.

This module provides functionality to...
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)


class ResourceHandler:
    """Handle external resource operations with retry logic."""
    
    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3):
        """
        Initialize handler.
        
        Args:
            api_key: Optional API key (reads from env if not provided)
            max_retries: Maximum retry attempts for failed operations
        """
        self.api_key = api_key or os.getenv('API_KEY')
        self.max_retries = max_retries
        
        if not self.api_key:
            logger.warning("No API key provided, some features may be limited")
    
    def fetch_data(self, resource_id: str) -> Dict:
        """
        Fetch data for a resource with retry logic.
        
        Args:
            resource_id: Unique identifier for the resource
        
        Returns:
            Dictionary containing resource data
        
        Raises:
            ValueError: If resource_id is invalid
            RuntimeError: If fetching fails after all retries
        
        Examples:
            >>> handler = ResourceHandler(api_key="abc123")
            >>> data = handler.fetch_data("resource-1")
            >>> print(data['status'])
            'success'
        """
        if not resource_id:
            raise ValueError("resource_id cannot be empty")
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Fetching data for {resource_id} (attempt {attempt + 1})")
                # Actual fetch logic here
                result = self._api_call(resource_id)
                logger.info(f"Successfully fetched data for {resource_id}")
                return result
            except Exception as e:
                logger.error(f"Error fetching {resource_id} (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    delay = min(2 ** attempt, 60)  # Exponential backoff, max 60s
                    logger.info(f"Retrying after {delay}s delay")
                    time.sleep(delay)
                else:
                    logger.error(f"Failed to fetch {resource_id} after {self.max_retries} attempts")
                    raise RuntimeError(f"Failed to fetch resource {resource_id}") from e
    
    def _api_call(self, resource_id: str) -> Dict:
        """Make actual API call (implementation detail)."""
        # Implementation here
        pass


def main():
    """Main entry point for the script."""
    # Configure logging from environment
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize handler
    handler = ResourceHandler()
    
    # Process resources
    try:
        data = handler.fetch_data("example-resource")
        logger.info(f"Processed {len(data)} items")
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
```

---

**Note**: This file represents general coding preferences and guidelines. Specific projects may have additional requirements or constraints that take precedence. Always adapt these guidelines to your project's specific needs.