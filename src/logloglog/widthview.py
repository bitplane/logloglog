"""WidthView class for viewing logs at a specific terminal width."""

from typing import Iterator, Tuple, TYPE_CHECKING

from wcwidth import wcwidth

from .line_index import MAX_WIDTH

if TYPE_CHECKING:
    from .logloglog import LogLogLog


class WidthView:
    """A width-specific view of a LogLogLog using Python container protocols."""

    def __init__(self, logloglog: "LogLogLog", width: int):
        """
        Initialize a WidthView.

        Args:
            logloglog: The LogLogLog instance to view
            width: Terminal width for wrapping
        """
        self._logloglog = logloglog
        self._width = min(width, MAX_WIDTH)
        self._cached_length = None

    def _wrap_line(self, line: str) -> list[str]:
        """Split a line into rows measured in terminal cells."""
        if not line:
            return [""]

        rows = [""]
        cell_offset = 0

        for character in line:
            character_width = max(0, wcwidth(character))
            row = cell_offset // self._width if character_width else len(rows) - 1
            while len(rows) <= row:
                rows.append("")
            rows[row] += character
            cell_offset += character_width

        expected_rows = max(1, (cell_offset + self._width - 1) // self._width)
        rows.extend([""] * (expected_rows - len(rows)))
        return rows

    def line_at(self, row: int) -> Tuple[int, int]:
        """
        Find which logical line contains the given display row.

        Args:
            row: Display row number

        Returns:
            Tuple of (line_number, offset_within_line)

        Raises:
            IndexError: If row is out of bounds
        """
        if row < 0:
            row = len(self) + row  # Handle negative indexing

        if row < 0 or row >= len(self):
            raise IndexError(f"Display row {row} out of range")

        return self._logloglog.line_at_row(row, self._width)

    def row_for(self, line_no: int) -> int:
        """
        Get the display row where a logical line starts.

        Args:
            line_no: Logical line number

        Returns:
            Display row number
        """
        return self._logloglog.row_for_line(line_no, self._width)

    def __getitem__(self, row_no: int) -> str:
        """
        Get text at display row.

        Args:
            row_no: Display row number (negative indexing supported)

        Returns:
            Text at the display row (may be partial line if wrapped)

        Raises:
            IndexError: If row_no is out of bounds
        """
        # Handle negative indexing
        if row_no < 0:
            row_no = len(self) + row_no

        if row_no < 0 or row_no >= len(self):
            raise IndexError(f"Display row {row_no} out of range")

        # Find the logical line and position within it
        line_no, line_offset = self.line_at(row_no)

        # Get the line and calculate the wrapped portion
        line = self._logloglog[line_no]

        return self._wrap_line(line)[line_offset]

    def __len__(self) -> int:
        """Get total number of display rows."""
        if self._cached_length is None:
            self._cached_length = self._logloglog.total_rows(self._width)
        return self._cached_length

    def __iter__(self) -> Iterator[str]:
        """Iterate over display rows."""
        for i in range(len(self)):
            yield self[i]
