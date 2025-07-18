"""LogView class for viewing logs at a specific terminal width."""

from typing import Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    from .logloglog import LogLogLog


class LogView:
    """A view of a LogLogLog at a specific terminal width."""

    def __init__(self, logloglog: "LogLogLog", width: int, start: int = 0, end: int = None):
        """
        Initialize a LogView.

        Args:
            logloglog: The LogLogLog instance to view
            width: Terminal width for wrapping
            start: Starting display row (inclusive)
            end: Ending display row (exclusive), None for end of log
        """
        self._logloglog = logloglog
        self._width = width
        self._start = start
        self._end = end
        self._cached_length = None

    def __getitem__(self, row_no: int) -> str:
        """
        Get text at display row.

        Args:
            row_no: Display row number (0-based within this view, negative indexing supported)

        Returns:
            Text at the display row (may be partial line if wrapped)

        Raises:
            IndexError: If row_no is out of bounds
        """
        view_length = len(self)

        # Handle negative indexing
        if row_no < 0:
            row_no = view_length + row_no

        if row_no < 0 or row_no >= view_length:
            raise IndexError(f"Display row {row_no} out of range")

        # Convert view-relative row to absolute display row
        absolute_row = self._start + row_no

        # Find the logical line and position within it
        line_no, line_offset = self._logloglog._find_line_at_display_row(absolute_row, self._width)

        # Get the line and calculate the wrapped portion
        line = self._logloglog[line_no]

        # Calculate start and end positions for this display row
        start_pos = line_offset * self._width
        end_pos = min(start_pos + self._width, len(line))

        return line[start_pos:end_pos]

    def __len__(self) -> int:
        """Get total number of display rows in this view."""
        if self._cached_length is None:
            if self._end is None:
                # Calculate total rows from start to end of log
                total_rows = self._logloglog._get_total_display_rows(self._width)
                self._cached_length = total_rows - self._start
            else:
                self._cached_length = self._end - self._start

        return max(0, self._cached_length)

    def __iter__(self) -> Iterator[str]:
        """Iterate over display rows."""
        for i in range(len(self)):
            yield self[i]
