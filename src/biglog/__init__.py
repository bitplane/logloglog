"""BigLog - Efficient scrollback indexing for large log files."""

from .biglog import BigLog
from .logview import LogView

__version__ = "0.1.0"
__all__ = ["BigLog", "LogView"]
