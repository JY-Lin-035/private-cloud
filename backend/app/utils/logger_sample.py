import logging
import traceback as tb
from typing import Optional
from logging.handlers import RotatingFileHandler
import os

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(logs_dir, exist_ok=True)

# Configure logging with file handler
log_file = os.path.join(logs_dir, "app.log")

# Create file handler with rotation (10MB max, keep 5 backups)
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)

# Configure Redis logger
redis_logger = logging.getLogger('redis')
redis_logger.setLevel(logging.INFO)
redis_logger.addHandler(file_handler)
redis_logger.addHandler(console_handler)


def log_error(title: str, error: Exception, level: str = "error"):
    """Log error with details similar to Laravel's LogHelper."""
    log_func = getattr(logger, level, logger.error)
    error_msg = f"{title} - Error: {str(error)}"
    if error.__traceback__:
        error_msg += f" - File: {error.__traceback__.tb_frame.f_code.co_filename}:{error.__traceback__.tb_lineno}"
    error_msg += f"\nTraceback:\n{tb.format_exc()}"
    log_func(error_msg)


def log_info(title: str, data: dict = None):
    """Log info message."""
    if data:
        logger.info(f"{title} - Data: {data}")
    else:
        logger.info(title)


def log_debug(title: str, data: dict = None):
    """Log debug message."""
    if data:
        logger.debug(f"{title} - Data: {data}")
    else:
        logger.debug(title)
