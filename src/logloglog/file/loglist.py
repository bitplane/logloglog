"""LogList provides line-level access with caching and position tracking."""

import logging
from typing import Any, Optional

from ..logview import LogView

logger = logging.getLogger(__name__)


class LogList:
    """
    Provides line-level access to a log file with caching and position tracking.

    This class handles:
    - Line offset caching for O(1) line access
    - Current position tracking
    - Cache updates when file changes
    - View creation at different widths
    """

    def __init__(self, file_handler: "FileHandler"):
        """
        Initialize LogList with a FileHandler.

        Args:
            file_handler: FileHandler instance that manages the underlying file
        """
        self.file_handler = file_handler
        self._pos = 0  # Current position in the log

    @property
    def pos(self) -> int:
        """Get current position in the log."""
        return self._pos

    @pos.setter
    def pos(self, value: int) -> None:
        """Set current position in the log."""
        if value < 0:
            value = 0
        elif value >= len(self):
            value = len(self) - 1
        self._pos = value

    def __len__(self) -> int:
        """Get total number of lines in the log."""
        return self.file_handler.get_line_count()

    def __getitem__(self, line_no: int) -> str:
        """
        Get a line by line number.

        Args:
            line_no: Line number (0-based, negative indexing supported)

        Returns:
            The line content as a string

        Raises:
            IndexError: If line_no is out of bounds
        """
        total_lines = len(self)

        # Handle negative indexing
        if line_no < 0:
            line_no = total_lines + line_no

        if line_no < 0 or line_no >= total_lines:
            raise IndexError(f"Line {line_no} out of range [0, {total_lines})")

        return self.file_handler.get_line(line_no)

    def __getattr__(self, name: str) -> Any:
        """
        Delegate unknown attributes to the file_handler.

        This allows LogList to act as a proxy for FileHandler methods
        while adding its own line-level functionality.
        """
        if hasattr(self.file_handler, name):
            return getattr(self.file_handler, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def update(self) -> None:
        """Update the line offset cache if the file has changed."""
        logger.debug("LogList.update() - checking for file changes")
        self.file_handler.update()

        # Adjust position if it's now out of bounds
        max_pos = len(self) - 1
        if self._pos > max_pos:
            self._pos = max(0, max_pos)
            logger.debug(f"Adjusted position to {self._pos} due to file changes")

    def get_view(self, width: int, start: int = 0, end: Optional[int] = None) -> LogView:
        """
        Create a view of the log at a specific width.

        Args:
            width: Terminal width for line wrapping
            start: Starting display row
            end: Ending display row (None for end of log)

        Returns:
            LogView instance for the specified parameters
        """
        return self.file_handler.get_view(width, start, end)

    def get_line_range(self, start: int, count: int) -> list[str]:
        """
        Get a range of lines efficiently.

        Args:
            start: Starting line number
            count: Number of lines to get

        Returns:
            List of lines
        """
        lines = []
        end = min(start + count, len(self))

        for i in range(start, end):
            lines.append(self[i])

        return lines

    def append(self, line: str) -> None:
        """
        Append a line to the log file.

        Args:
            line: Line to append (newline will be added)
        """
        self.file_handler.append_line(line)

    def seek_to_end(self) -> None:
        """Set position to the last line."""
        self.pos = len(self) - 1

    def seek_to_start(self) -> None:
        """Set position to the first line."""
        self.pos = 0

    def next_line(self) -> Optional[str]:
        """
        Move to next line and return it.

        Returns:
            The next line, or None if at end
        """
        if self._pos < len(self) - 1:
            self._pos += 1
            return self[self._pos]
        return None

    def prev_line(self) -> Optional[str]:
        """
        Move to previous line and return it.

        Returns:
            The previous line, or None if at start
        """
        if self._pos > 0:
            self._pos -= 1
            return self[self._pos]
        return None
