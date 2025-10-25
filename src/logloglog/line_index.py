"""Simple line indexing with periodic summaries for efficient wrapping calculations."""

import logging
from pathlib import Path
from typing import Tuple
from arrayfile import Array

logger = logging.getLogger(__name__)

# Configuration
MAX_WIDTH = 512  # Maximum terminal width we support
SUMMARY_INTERVAL = 1000  # Store summary every N lines


class LineIndex:
    """
    Indexes log lines with byte positions, widths, and periodic summaries.

    Stores:
    - line_positions: byte offset of each line in the log file
    - line_widths: display width of each line
    - summaries: every 1000 lines, cumulative display rows for each width 1-512
    """

    def __init__(self, index_path: Path):
        """Initialize line index with given path."""
        self.index_path = index_path
        self._line_positions = None
        self._line_widths = None
        self._summaries = None
        self._line_count = 0
        self._current_block_width_counts = {}  # Track widths in current 1000-line block
        self._pending_positions = []  # Batch positions for extend()
        self._pending_widths = []  # Batch widths for extend()

    def open(self, create: bool = False):
        """Open index files."""
        self.index_path.mkdir(parents=True, exist_ok=True)

        mode = "w+b" if create else "r+b"

        # Line positions (uint64 for file offsets)
        self._line_positions = Array("Q", str(self.index_path / "positions.dat"), mode)

        # Line widths (uint16, capped at 65535)
        self._line_widths = Array("H", str(self.index_path / "widths.dat"), mode)

        # Summaries (uint32 array, MAX_WIDTH entries per summary)
        self._summaries = Array("I", str(self.index_path / "summaries.dat"), mode)

        # Count existing lines
        self._line_count = len(self._line_positions)

    def close(self):
        """Close all index files."""
        # Flush any pending data before closing
        self._flush_pending()

        if self._line_positions:
            self._line_positions.close()
            self._line_positions = None
        if self._line_widths:
            self._line_widths.close()
            self._line_widths = None
        if self._summaries:
            self._summaries.close()
            self._summaries = None

    def append_line(self, position: int, width: int):
        """
        Append a new line to the index.

        Args:
            position: Byte offset of line start in log file
            width: Display width of the line
        """
        # Cap width at uint16 max
        width = min(width, 65535)

        # Batch in memory
        self._pending_positions.append(position)
        self._pending_widths.append(width)
        self._line_count += 1

        # Track width for current block
        self._current_block_width_counts[width] = self._current_block_width_counts.get(width, 0) + 1

        # Check if we need to flush and store a summary
        if self._line_count % SUMMARY_INTERVAL == 0:
            self._flush_pending()
            self._store_summary()
            self._current_block_width_counts.clear()

    def _flush_pending(self):
        """Flush pending positions and widths to disk."""
        if self._pending_positions:
            self._line_positions.extend(self._pending_positions)
            self._pending_positions.clear()
        if self._pending_widths:
            self._line_widths.extend(self._pending_widths)
            self._pending_widths.clear()

    def _store_summary(self):
        """Store summary using already-tracked width counts."""
        # Calculate totals for each terminal width
        width_totals = [0] * MAX_WIDTH
        for line_width, count in self._current_block_width_counts.items():
            if line_width == 0:
                # Empty lines always take 1 row regardless of terminal width
                for i in range(MAX_WIDTH):
                    width_totals[i] += count
            else:
                # Calculate rows for each terminal width
                # Ceiling division: (line_width + term_width - 1) // term_width
                # This is always >= 1 when both operands are positive
                for term_width in range(1, MAX_WIDTH + 1):
                    rows = (line_width + term_width - 1) // term_width
                    width_totals[term_width - 1] += rows * count

        # Store all width totals in summary array (batch append for performance)
        self._summaries.extend(width_totals)

    def get_line_position(self, line_no: int) -> int:
        """Get byte position of a line."""
        if line_no < 0 or line_no >= self._line_count:
            raise IndexError(f"Line {line_no} out of range")

        # Check if it's in the flushed data or pending batch
        flushed_count = len(self._line_positions)
        if line_no < flushed_count:
            return self._line_positions[line_no]
        else:
            # It's in the pending batch
            pending_idx = line_no - flushed_count
            return self._pending_positions[pending_idx]

    def get_line_width(self, line_no: int) -> int:
        """Get display width of a line."""
        if line_no < 0 or line_no >= self._line_count:
            raise IndexError(f"Line {line_no} out of range")

        # Check if it's in the flushed data or pending batch
        flushed_count = len(self._line_widths)
        if line_no < flushed_count:
            return self._line_widths[line_no]
        else:
            # It's in the pending batch
            pending_idx = line_no - flushed_count
            return self._pending_widths[pending_idx]

    def get_total_display_rows(self, width: int) -> int:
        """
        Get total display rows for all lines at given terminal width.

        Args:
            width: Terminal width

        Returns:
            Total number of display rows
        """
        if width <= 0:
            return 0  # No display possible with zero or negative width
        if width > MAX_WIDTH:
            width = MAX_WIDTH

        total_rows = 0

        # Add up complete summaries
        complete_summaries = self._line_count // SUMMARY_INTERVAL
        for i in range(complete_summaries):
            summary_offset = i * MAX_WIDTH + (width - 1)
            total_rows += self._summaries[summary_offset]

        # Add remaining lines not in a summary
        start_line = complete_summaries * SUMMARY_INTERVAL
        for line_idx in range(start_line, self._line_count):
            line_width = self.get_line_width(line_idx)
            # Ceiling division is always >= 1 for positive operands
            rows = (line_width + width - 1) // width if width > 0 and line_width > 0 else 1
            total_rows += rows

        return total_rows

    def get_display_row_for_line(self, line_no: int, width: int) -> int:
        """
        Get the display row number where a logical line starts.

        Args:
            line_no: Logical line number
            width: Terminal width

        Returns:
            Display row number where this line starts
        """
        if line_no < 0 or line_no >= self._line_count:
            raise IndexError(f"Line {line_no} out of range")

        if width <= 0:
            return 0  # No display possible
        if width > MAX_WIDTH:
            width = MAX_WIDTH

        display_row = 0

        # Add complete summaries before this line
        summary_idx = line_no // SUMMARY_INTERVAL
        for i in range(summary_idx):
            summary_offset = i * MAX_WIDTH + (width - 1)
            display_row += self._summaries[summary_offset]

        # Add individual lines from last summary to target line
        start_line = summary_idx * SUMMARY_INTERVAL
        for line_idx in range(start_line, line_no):
            line_width = self.get_line_width(line_idx)
            rows = (line_width + width - 1) // width if width > 0 and line_width > 0 else 1
            display_row += rows

        return display_row

    def get_line_for_display_row(self, display_row: int, width: int) -> Tuple[int, int]:
        """
        Find the logical line containing the given display row.

        Args:
            display_row: Display row to find
            width: Terminal width

        Returns:
            Tuple of (line_number, row_offset_within_line)
        """
        if width <= 0:
            raise IndexError(f"Display row {display_row} out of range")  # No display possible
        if width > MAX_WIDTH:
            width = MAX_WIDTH

        current_row = 0

        # Binary search through summaries to find the right range
        complete_summaries = self._line_count // SUMMARY_INTERVAL
        summary_idx = 0

        # Find which summary block contains our display row
        for i in range(complete_summaries):
            summary_offset = i * MAX_WIDTH + (width - 1)
            summary_rows = self._summaries[summary_offset]
            if current_row + summary_rows > display_row:
                summary_idx = i
                break
            current_row += summary_rows
        else:
            # It's in the incomplete last block
            summary_idx = complete_summaries

        # Linear search within the summary block
        start_line = summary_idx * SUMMARY_INTERVAL
        end_line = min(start_line + SUMMARY_INTERVAL, self._line_count)

        for line_idx in range(start_line, end_line):
            line_width = self.get_line_width(line_idx)
            rows = (line_width + width - 1) // width if width > 0 and line_width > 0 else 1

            if current_row + rows > display_row:
                # Found the line
                offset_within_line = display_row - current_row
                return (line_idx, offset_within_line)

            current_row += rows

        # Display row is beyond the end
        raise IndexError(f"Display row {display_row} out of range")

    def __len__(self) -> int:
        """Get total number of indexed lines."""
        return self._line_count
