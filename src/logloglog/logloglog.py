"""Main LogLogLog implementation."""

import os
import shutil
import time
import logging
from functools import lru_cache
from pathlib import Path
from typing import Callable, List, Iterator, Tuple
from wcwidth import wcswidth

from .logview import LogView
from .line_index import LineIndex
from .cache import Cache

# Configure logger
logger = logging.getLogger(__name__)


@lru_cache(maxsize=100000)
def default_get_width(line: str) -> int:
    """Fast line width calculation with ASCII fast path and caching."""
    # Fast path for ASCII (99% of log lines)
    if line.isascii():
        return len(line)
    # Slow path for Unicode
    width = wcswidth(line)
    return max(0, width if width is not None else len(line))


def default_split_lines(text: str) -> List[str]:
    """Default line splitting on newlines."""
    # Handle different line endings
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Don't lose empty lines
    if text.endswith("\n"):
        lines.pop()  # Remove last empty element from split
    return lines


class LogLogLog(LogView):
    """
    Efficient scrollback indexing for large log files.

    LogLogLog provides O(log n) seeking through large logs at any terminal width.
    """

    def __init__(
        self,
        path: Path | str,
        get_width: Callable[[str], int] = None,
        split_lines: Callable[[str], List[str]] = None,
        cache: Cache = None,
    ):
        """
        Initialize LogLogLog for a file.

        Args:
            path: Log file path
            get_width: Function to calculate display width (defaults to wcwidth)
            split_lines: Function to split text into lines (defaults to newline split)
            cache: Cache instance (auto-created if None)
        """
        self.path = Path(path).resolve()  # Resolve symlinks
        self.get_width = get_width or default_get_width
        self.split_lines = split_lines or default_split_lines

        # Set up cache
        self.cache = cache or Cache()

        # Initialize index components
        self._index_path = self.cache.get_dir(self.path)
        self._line_index = LineIndex(self._index_path)

        # File size tracking
        self._file_size_path = self._index_path / "file_size.dat"

        # File tracking
        self._file = None
        self._file_stat = None
        self._last_position = 0

        # Open and validate index
        self._open()

        # Initialize as a LogView of the entire log
        super().__init__(self, float("inf"), 0)

    def _open(self):
        """Open the log file and index."""
        start_time = time.time()
        logger.info(f"Opening LogLogLog for {self.path}")

        # Get file stats
        stat_start = time.time()
        self._file_stat = os.stat(self.path)
        logger.debug(f"File stat took {time.time() - stat_start:.3f}s - size: {self._file_stat.st_size:,} bytes")

        # Choose offset dtype based on file size
        self._offset_dtype = "I" if self._file_stat.st_size < (1 << 32) else "Q"
        logger.debug(f"Using {self._offset_dtype} for line offsets ({'4' if self._offset_dtype == 'I' else '8'} bytes)")

        # Check if index exists and is valid
        validate_start = time.time()
        positions_exists = (self._index_path / "positions.dat").exists()
        widths_exists = (self._index_path / "widths.dat").exists()
        summaries_exists = (self._index_path / "summaries.dat").exists()
        file_size_exists = self._file_size_path.exists()

        index_exists = positions_exists and widths_exists and summaries_exists and file_size_exists

        logger.debug(
            f"Index file check - positions: {positions_exists}, widths: {widths_exists}, summaries: {summaries_exists}, file_size: {file_size_exists}"
        )

        # Open log file early so we can use it for validation
        file_start = time.time()
        self._file = open(self.path, "r+b")
        logger.debug(f"File open took {time.time() - file_start:.3f}s")

        if index_exists:
            try:
                # Try to open existing index
                load_start = time.time()
                self._line_index.open(create=False)

                # Calculate last_position from last line offset
                if len(self._line_index) > 0:
                    last_offset = self._line_index.get_line_position(len(self._line_index) - 1)
                    self._file.seek(last_offset)
                    self._file.readline()  # Read to end of last line
                    self._last_position = self._file.tell()
                    logger.debug(f"Calculated last_position: {self._last_position:,} from offset {last_offset:,}")
                else:
                    self._last_position = 0
                    logger.debug("Empty line index, setting last_position to 0")

                logger.debug(f"Index load took {time.time() - load_start:.3f}s - last_pos: {self._last_position:,}")
                logger.debug(f"Loaded {len(self._line_index):,} lines")

                # Check if file size has changed (shrunk = truncated)
                cached_file_size = self._load_file_size()
                current_file_size = self._file_stat.st_size
                if cached_file_size is not None and current_file_size < cached_file_size:
                    logger.info(
                        f"File shrunk from {cached_file_size:,} to {current_file_size:,} bytes - invalidating cache"
                    )
                    raise Exception("File truncated")

            except Exception as e:
                logger.exception(f"Failed to load existing index: {e}, rebuilding")
                index_exists = False
                # Close any partially opened components
                self._line_index.close()

        logger.debug(f"Index validation took {time.time() - validate_start:.3f}s - valid: {index_exists}")

        if not index_exists:
            # Create new index
            logger.info("Creating new index (invalid/missing)")
            clear_start = time.time()
            self._clear_index()
            logger.debug(f"Clear index took {time.time() - clear_start:.3f}s")

            self._line_index.open(create=True)
            self._last_position = 0

        # Update index with any new content
        update_start = time.time()
        self.update()
        logger.info(f"Update took {time.time() - update_start:.3f}s")

        logger.info(f"Total open time: {time.time() - start_time:.3f}s")

    def _save_file_size(self, file_size):
        """Save the file size to cache metadata."""
        with open(self._file_size_path, "w") as f:
            f.write(str(file_size))

    def _load_file_size(self):
        """Load the cached file size, returns None if not found."""
        try:
            with open(self._file_size_path, "r") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return None

    def _clear_index(self):
        """Clear the index directory."""
        # Clear the cache directory for this file
        if self._index_path.exists():
            shutil.rmtree(self._index_path)
        # Get a fresh cache directory
        self._index_path = self.cache.get_dir(self.path)
        self._last_position = 0

    def close(self):
        """Close all resources."""
        if self._file:
            self._file.close()
            self._file = None
        self._line_index.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def update(self):
        """Update index with new lines from the file."""
        start_time = time.time()

        # Check if file has grown
        seek_start = time.time()
        self._file.seek(0, 2)  # Seek to end
        current_size = self._file.tell()
        logger.debug(f"File seek took {time.time() - seek_start:.3f}s - current size: {current_size:,}")

        if current_size < self._last_position:
            # File was truncated or rotated
            logger.info(
                f"File truncated/rotated - rebuilding index (size: {current_size:,}, last_pos: {self._last_position:,})"
            )
            self._clear_index()
            self._line_index.close()
            self._line_index.open(create=True)
            # Reset position to start over
            self._last_position = 0

        # Stream process new content instead of reading entire file into RAM
        stream_start = time.time()
        self._file.seek(self._last_position)

        # Process line by line to avoid loading huge files into memory
        width_count = 0
        process_start = time.time()

        while True:
            # Get raw byte position before reading line
            raw_pos = self._file.tell()
            line_data = self._file.readline()

            if not line_data:
                break  # EOF

            # Decode and strip newline
            line = line_data.decode("utf-8", errors="replace").rstrip("\n\r")

            # Calculate width and add to index
            width = self.get_width(line)
            self._line_index.append_line(raw_pos, width)
            width_count += 1

            # Update position to end of this line
            self._last_position = self._file.tell()

            # Progress logging for large files
            if width_count % 100000 == 0:
                elapsed = time.time() - process_start
                rate = width_count / elapsed if elapsed > 0 else 0
                logger.info(f"Processed {width_count:,} lines in {elapsed:.1f}s ({rate:.0f} lines/sec)")

        if width_count > 0:
            logger.debug(f"Stream processing took {time.time() - stream_start:.3f}s for {width_count:,} lines")

            # No tree update needed - summaries are created automatically during append
            # LineIndex handles flushing internally

        # Save current file size to cache metadata
        current_file_size = self._file.tell()
        self._save_file_size(current_file_size)

        logger.info(f"Total update time: {time.time() - start_time:.3f}s")

    def append(self, line: str):
        """
        Append a line to the log file and update index.

        Args:
            line: Line to append (newline will be added)
        """
        # Write to file (binary mode)
        self._file.seek(0, 2)  # Seek to end
        raw_pos = self._file.tell()
        self._file.write((line + "\n").encode("utf-8"))
        self._file.flush()

        # Update our position tracking
        self._last_position = self._file.tell()

        # Update index
        width = self.get_width(line)
        self._line_index.append_line(raw_pos, width)

        # Update file stats
        self._file_stat = os.stat(self.path)

    def __getitem__(self, line_no: int) -> str:
        """Get a logical line by line number."""
        total_lines = len(self._line_index)

        # Handle negative indexing
        if line_no < 0:
            line_no = total_lines + line_no

        if line_no < 0 or line_no >= total_lines:
            raise IndexError(f"Line {line_no} out of range")

        # O(1) access using line offset index
        offset = self._line_index.get_line_position(line_no)
        self._file.seek(offset)
        line_data = self._file.readline()

        return line_data.decode("utf-8", errors="replace").rstrip("\n\r")

    def __len__(self) -> int:
        """Get total number of logical lines."""
        return len(self._line_index)

    def __iter__(self) -> Iterator[str]:
        """Iterate over all logical lines."""
        for i in range(len(self)):
            yield self[i]

    def at(self, width: int, start: int = 0, end: int = None) -> LogView:
        """
        Create a view at specific terminal width.

        Args:
            width: Terminal width for wrapping
            start: Starting display row
            end: Ending display row (None for end of log)

        Returns:
            LogView instance
        """
        return LogView(self, width, start, end)

    def _find_line_at_display_row(self, row: int, width: int) -> Tuple[int, int]:
        """Find logical line containing display row."""
        return self._line_index.get_line_for_display_row(row, width)

    def _get_total_display_rows(self, width: int) -> int:
        """Get total display rows at given width."""
        return self._line_index.get_total_display_rows(width)

    def _get_display_row_for_line(self, line_no: int, width: int) -> int:
        """Get display row where logical line starts (for resize fix)."""
        return self._line_index.get_display_row_for_line(line_no, width)
