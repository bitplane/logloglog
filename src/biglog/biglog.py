"""Main BigLog implementation."""

import os
import time
import logging
import array
from functools import lru_cache
from pathlib import Path
from typing import Callable, List, Iterator, Tuple
from wcwidth import wcswidth
import platformdirs

from .logview import LogView
from .index import IndexMetadata, DisplayWidths
from .wraptree import WrapTree

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


class BigLog(LogView):
    """
    Efficient scrollback indexing for large log files.

    BigLog provides O(log n) seeking through large logs at any terminal width.
    """

    def __init__(
        self,
        path: Path | str,
        get_width: Callable[[str], int] = None,
        split_lines: Callable[[str], List[str]] = None,
        cache_dir: Path = None,
    ):
        """
        Initialize BigLog for a file.

        Args:
            path: Log file path
            get_width: Function to calculate display width (defaults to wcwidth)
            split_lines: Function to split text into lines (defaults to newline split)
            cache_dir: Cache directory (auto-detected if None)
        """
        self.path = Path(path).resolve()  # Resolve symlinks
        self.get_width = get_width or default_get_width
        self.split_lines = split_lines or default_split_lines

        # Set up cache directory
        if cache_dir is None:
            cache_dir = Path(platformdirs.user_cache_dir("biglog"))
        self.cache_dir = cache_dir

        # Initialize index components
        self._index_path = self._get_index_path()
        self._metadata = IndexMetadata(self._index_path)
        self._display_widths = DisplayWidths(self._index_path)
        self._wraptree = WrapTree(self._index_path, self._display_widths)

        # Line offset array for O(1) access
        self._line_offsets = array.array("Q")  # uint64 offsets
        self._line_offsets_path = self._index_path / "line_offsets.dat"

        # File tracking
        self._file = None
        self._file_stat = None
        self._last_position = 0

        # Open and validate index
        self._open()

        # Initialize as a LogView of the entire log
        super().__init__(self, float("inf"), 0)

    def _get_index_path(self) -> Path:
        """Get the index directory path based on file identity."""
        stat = os.stat(self.path)

        if os.name == "posix":
            # Unix: use device and inode
            index_name = f"{stat.st_dev}_{stat.st_ino}"
        else:
            # Windows: use file index
            import ctypes
            import ctypes.wintypes

            # Get file handle
            handle = ctypes.windll.kernel32.CreateFileW(str(self.path), 0x80000000, 0, None, 3, 0x80, None)

            # Get file index
            file_info = ctypes.wintypes.BY_HANDLE_FILE_INFORMATION()
            ctypes.windll.kernel32.GetFileInformationByHandle(handle, ctypes.byref(file_info))
            ctypes.windll.kernel32.CloseHandle(handle)

            index_name = f"{file_info.dwVolumeSerialNumber}_{file_info.nFileIndexHigh}_{file_info.nFileIndexLow}"

        return self.cache_dir / index_name

    def _open(self):
        """Open the log file and index."""
        start_time = time.time()
        logger.info(f"Opening BigLog for {self.path}")

        # Get file stats
        stat_start = time.time()
        self._file_stat = os.stat(self.path)
        logger.debug(f"File stat took {time.time() - stat_start:.3f}s - size: {self._file_stat.st_size:,} bytes")

        # Check if index is valid
        validate_start = time.time()
        is_valid = self._metadata.validate(self._file_stat)
        logger.debug(f"Index validation took {time.time() - validate_start:.3f}s - valid: {is_valid}")

        if is_valid:
            # Load existing index
            load_start = time.time()
            metadata = self._metadata.load()
            self._last_position = metadata.get("last_position", 0)
            logger.debug(f"Metadata load took {time.time() - load_start:.3f}s - last_pos: {self._last_position:,}")

            widths_start = time.time()
            self._display_widths.open(create=False)
            logger.debug(f"DisplayWidths open took {time.time() - widths_start:.3f}s")

            tree_start = time.time()
            self._wraptree.open(create=False)
            logger.debug(f"WrapTree open took {time.time() - tree_start:.3f}s")

            # Load line offsets
            self._load_line_offsets()
        else:
            # Create new index
            logger.info("Creating new index (invalid/missing)")
            clear_start = time.time()
            self._clear_index()
            logger.debug(f"Clear index took {time.time() - clear_start:.3f}s")

            self._display_widths.open(create=True)
            self._wraptree.open(create=True)

        # Open log file in text mode for easier handling
        file_start = time.time()
        self._file = open(self.path, "r+", encoding="utf-8", errors="replace")
        logger.debug(f"File open took {time.time() - file_start:.3f}s")

        # Update index with any new content
        update_start = time.time()
        self.update()
        logger.info(f"Update took {time.time() - update_start:.3f}s")

        logger.info(f"Total open time: {time.time() - start_time:.3f}s")

    def _clear_index(self):
        """Clear the index directory."""
        import shutil

        if self._index_path.exists():
            shutil.rmtree(self._index_path)
        self._last_position = 0
        self._line_offsets = array.array("Q")  # Reset line offsets

    def close(self):
        """Close all resources."""
        if self._file:
            self._file.close()
            self._file = None
        self._display_widths.close()
        self._wraptree.close()
        self._save_line_offsets()

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
            self._display_widths.close()
            self._wraptree.close()
            self._display_widths.open(create=True)
            self._wraptree.open(create=True)
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
            raw_pos = os.lseek(self._file.fileno(), 0, os.SEEK_CUR)
            line_data = self._file.readline()

            if not line_data:
                break  # EOF

            # Record line offset for O(1) access
            self._line_offsets.append(raw_pos)

            # Strip newline (CPython already decoded UTF-8)
            line = line_data.rstrip("\n\r")

            # Calculate and store width
            width = self.get_width(line)
            self._display_widths.append(width)
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

            # Update tree structure
            tree_start = time.time()
            total_lines = len(self._display_widths)
            logger.debug(f"Updating tree for {total_lines:,} total lines")
            self._wraptree.update_tree(total_lines)
            logger.debug(f"Tree update took {time.time() - tree_start:.3f}s")

            # Save metadata and line offsets
            save_start = time.time()
            self._save_metadata()
            self._save_line_offsets()
            logger.debug(f"Metadata save took {time.time() - save_start:.3f}s")

        logger.info(f"Total update time: {time.time() - start_time:.3f}s")

    def _save_metadata(self):
        """Save index metadata."""
        metadata = {
            "version": 1,
            "last_position": self._last_position,
            "line_count": len(self._display_widths),
            "ctime": self._file_stat.st_ctime,
            "size": self._file_stat.st_size,
        }
        self._metadata.save(metadata)

    def _load_line_offsets(self):
        """Load line offsets from disk."""
        if self._line_offsets_path.exists():
            with open(self._line_offsets_path, "rb") as f:
                data = f.read()
                if data:
                    self._line_offsets = array.array("Q")
                    self._line_offsets.frombytes(data)

    def _save_line_offsets(self):
        """Save line offsets to disk."""
        if self._line_offsets:
            self._line_offsets_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._line_offsets_path, "wb") as f:
                f.write(self._line_offsets.tobytes())

    def append(self, line: str):
        """
        Append a line to the log file and update index.

        Args:
            line: Line to append (newline will be added)
        """
        # Write to file (text mode)
        self._file.seek(0, 2)  # Seek to end
        raw_pos = os.lseek(self._file.fileno(), 0, os.SEEK_CUR)
        self._file.write(line + "\n")
        self._file.flush()

        # Update our position tracking
        self._last_position = self._file.tell()

        # Update index
        self._line_offsets.append(raw_pos)
        width = self.get_width(line)
        self._display_widths.append(width)

        # Update tree
        total_lines = len(self._display_widths)
        self._wraptree.update_tree(total_lines)

        # Update file stats
        self._file_stat = os.stat(self.path)
        self._save_metadata()

    def __getitem__(self, line_no: int) -> str:
        """Get a logical line by line number."""
        total_lines = len(self._line_offsets)

        # Handle negative indexing
        if line_no < 0:
            line_no = total_lines + line_no

        if line_no < 0 or line_no >= total_lines:
            raise IndexError(f"Line {line_no} out of range")

        # O(1) access using line offset index
        offset = self._line_offsets[line_no]
        self._file.seek(offset)
        line_data = self._file.readline()

        if not line_data:
            raise IndexError(f"Line {line_no} out of range")

        return line_data.rstrip("\n\r")

    def __len__(self) -> int:
        """Get total number of logical lines."""
        return len(self._line_offsets)

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
        return self._wraptree.seek_display_row(row, width)

    def _get_total_display_rows(self, width: int) -> int:
        """Get total display rows at given width."""
        return self._wraptree.get_total_rows(width)
