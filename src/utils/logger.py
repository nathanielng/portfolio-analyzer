# src/utils/logger.py
"""Logging configuration for portfolio analyzer."""

import logging
import os


def setup_logger(name: str = 'portfolio_analyzer', level: str = None) -> logging.Logger:
    """
    Setup and configure logger.
    
    Args:
        name: Logger name
        level: Logging level (default from env or INFO)
    
    Returns:
        Configured logger instance
    """
    log_level = level or os.getenv('LOG_LEVEL', 'INFO')
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger