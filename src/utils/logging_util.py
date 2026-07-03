"""Logging Configuration Utility for GridSense AI.

This module registers console and rotating file-based handlers with standard formatters.
"""

import sys
import logging
from logging.handlers import RotatingFileHandler
from config.config import config


def setup_logger(name: str = "gridsense") -> logging.Logger:
    """Configures and returns a multi-handler rotating logger.

    Args:
        name: Name of the logger instance.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(config.log_level)

    # Prevent handler duplication if function is called multiple times
    if logger.hasHandlers():
        return logger

    # Log format pattern: Timestamp | Level | Module.Function | Message
    log_format = "%(asctime)s | %(levelname)-8s | %(module)s.%(funcName)s | %(message)s"
    formatter = logging.Formatter(log_format)

    # 1. Console Handler (Standard Output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(config.log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. Rotating File Handler (Logs directory)
    log_file_path = config.get_log_file_path()
    file_handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(config.log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info(
        f"Logging initialized at level: {config.log_level_str}. Target log file: {log_file_path}"
    )
    return logger


# Global application-wide logger
logger = setup_logger()
