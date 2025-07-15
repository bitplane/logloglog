"""BigLog - Efficient scrollback indexing for large log files."""

import logging
import sys


from .biglog import BigLog
from .logview import LogView

__version__ = "0.1.0"
__all__ = ["BigLog", "LogView", "configure_logging"]


# Configure logging for BigLog
def configure_logging(level=logging.INFO):
    """Configure logging for BigLog."""
    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Create console handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    # Configure biglog loggers
    for logger_name in ["biglog.biglog", "biglog.wraptree", "biglog.index"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()
        logger.addHandler(handler)


# Auto-configure with DEBUG level for performance monitoring
configure_logging(logging.DEBUG)
