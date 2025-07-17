"""Tail functionality for displaying the last N lines of a log."""

from typing import Iterator, List


class Tail:
    """Displays the last N lines of a log file with a given height."""

    def __init__(self, height: int):
        """
        Initialize a Tail view.

        Args:
            height: Number of lines to display (window height)
        """
        if height <= 0:
            raise ValueError("Height must be positive")
        self.height = height

    def get_lines(self, log_list: "LogList") -> List[str]:
        """
        Get the last N lines from the log.

        Args:
            log_list: LogList instance to read from

        Returns:
            List of the last N lines (or fewer if log is shorter)
        """
        total_lines = len(log_list)
        if total_lines == 0:
            return []

        # Calculate start position
        start_line = max(0, total_lines - self.height)

        # Get the lines
        lines = []
        for i in range(start_line, total_lines):
            lines.append(log_list[i])

        return lines

    def get_display_rows(self, log_list: "LogList", width: int) -> List[str]:
        """
        Get the last N display rows (accounting for line wrapping).

        Args:
            log_list: LogList instance to read from
            width: Terminal width for wrapping

        Returns:
            List of display rows (wrapped lines)
        """
        if width <= 0:
            return []

        # Get a view of the entire log to calculate display rows
        view = log_list.get_view(width)
        total_display_rows = len(view)

        if total_display_rows == 0:
            return []

        # Calculate start position for display rows
        start_row = max(0, total_display_rows - self.height)

        # Get the display rows
        rows = []
        for i in range(start_row, total_display_rows):
            rows.append(view[i])

        return rows

    def __iter__(self) -> Iterator[str]:
        """Iterator interface - requires a log_list to be bound."""
        raise NotImplementedError("Use get_lines() or get_display_rows() instead")
