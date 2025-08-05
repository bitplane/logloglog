"""Main LogLogLog implementation."""

import os
import shutil
import time
import logging
import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Callable, List, Iterator, Tuple, Union
from wcwidth import wcswidth

from .widthview import WidthView
from .line_index import LineIndex
from .cache import Cache
from .log_file import LogFile

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


class LogLogLog:
    """
    Efficient scrollback indexing for large log files.

    LogLogLog provides O(log n) seeking through large logs at any terminal width.
    """

    def __init__(
        self,
        path: Union[Path, str, LogFile],
        get_width: Callable[[str], int] = None,
        split_lines: Callable[[str], List[str]] = None,
        cache: Cache = None,
        defer_indexing: bool = False,
    ):
        """
        Initialize LogLogLog for a file.

        Args:
            path: Log file path or LogFile instance
            get_width: Function to calculate display width (defaults to wcwidth)
            split_lines: Function to split text into lines (defaults to newline split)
            cache: Cache instance (auto-created if None)
            defer_indexing: If True, skip initial indexing (useful for UI responsiveness)
        """
        # Handle path/LogFile parameter
        if isinstance(path, LogFile):
            self.log_file = path
            self.path = path.path.resolve()
        else:
            self.path = Path(path).resolve()  # Resolve symlinks
            # Use append mode to allow both reading existing content and writing new content
            self.log_file = LogFile(self.path, mode="a")

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
        self._file_stat = None

        # Open and validate index (unless deferred)
        if not defer_indexing:
            self._open()

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

        # No need to open file explicitly - LogFile handles that
        logger.debug(f"Using LogFile for {self.path}")

        if index_exists:
            try:
                # Try to open existing index
                load_start = time.time()
                self._line_index.open(create=False)

                # Calculate last_position from last line offset
                if len(self._line_index) > 0:
                    last_offset = self._line_index.get_line_position(len(self._line_index) - 1)
                    self.log_file.seek_to(last_offset)
                    self.log_file.read_line()  # Read to end of last line
                    last_position = self.log_file.get_position()
                    logger.debug(f"Calculated last_position: {last_position:,} from offset {last_offset:,}")
                else:
                    last_position = 0
                    logger.debug("Empty line index, setting last_position to 0")

                # Update LogFile position
                self.log_file.seek_to(last_position)

                logger.debug(f"Index load took {time.time() - load_start:.3f}s - last_pos: {last_position:,}")
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
            self.log_file.seek_to(0)

        # Update index with any new content
        update_start = time.time()
        self.update()
        logger.info(f"Update took {time.time() - update_start:.3f}s")

        logger.info(f"Total open time: {time.time() - start_time:.3f}s")

    async def aopen(self):
        """Async version of _open() method for non-blocking file initialization."""
        start_time = time.time()
        logger.info(f"Opening LogLogLog for {self.path} (async)")

        # Get file stats (run in thread for I/O)
        stat_start = time.time()
        self._file_stat = await asyncio.to_thread(os.stat, self.path)
        logger.debug(f"File stat took {time.time() - stat_start:.3f}s - size: {self._file_stat.st_size:,} bytes")

        # Choose offset dtype based on file size
        self._offset_dtype = "I" if self._file_stat.st_size < (1 << 32) else "Q"
        logger.debug(f"Using {self._offset_dtype} for line offsets ({'4' if self._offset_dtype == 'I' else '8'} bytes)")

        # Check if index exists and is valid (run file checks in thread)
        validate_start = time.time()

        async def check_file_exists(path):
            return await asyncio.to_thread(path.exists)

        positions_exists, widths_exists, summaries_exists, file_size_exists = await asyncio.gather(
            check_file_exists(self._index_path / "positions.dat"),
            check_file_exists(self._index_path / "widths.dat"),
            check_file_exists(self._index_path / "summaries.dat"),
            check_file_exists(self._file_size_path),
        )

        index_exists = positions_exists and widths_exists and summaries_exists and file_size_exists

        logger.debug(
            f"Index file check - positions: {positions_exists}, widths: {widths_exists}, summaries: {summaries_exists}, file_size: {file_size_exists}"
        )

        # No need to open file explicitly - LogFile handles that
        logger.debug(f"Using LogFile for {self.path}")

        if index_exists:
            try:
                # Try to open existing index (run in thread for I/O)
                load_start = time.time()
                await asyncio.to_thread(self._line_index.open, create=False)

                # Calculate last_position from last line offset
                if len(self._line_index) > 0:
                    last_offset = self._line_index.get_line_position(len(self._line_index) - 1)
                    self.log_file.seek_to(last_offset)
                    await self.log_file.aread_line()  # Read to end of last line (async)
                    last_position = self.log_file.get_position()
                    logger.debug(f"Calculated last_position: {last_position:,} from offset {last_offset:,}")
                else:
                    last_position = 0
                    logger.debug("Empty line index, setting last_position to 0")

                # Update LogFile position
                self.log_file.seek_to(last_position)

                logger.debug(f"Index load took {time.time() - load_start:.3f}s - last_pos: {last_position:,}")
                logger.debug(f"Loaded {len(self._line_index):,} lines")

                # Check if file size has changed (shrunk = truncated)
                cached_file_size = await asyncio.to_thread(self._load_file_size)
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
            await asyncio.to_thread(self._clear_index)
            logger.debug(f"Clear index took {time.time() - clear_start:.3f}s")

            await asyncio.to_thread(self._line_index.open, create=True)
            self.log_file.seek_to(0)

        # Update index with any new content (use async version)
        update_start = time.time()
        await self.aupdate()
        logger.info(f"Async update took {time.time() - update_start:.3f}s")

        logger.info(f"Total async open time: {time.time() - start_time:.3f}s")

    async def _initialize_deferred(self):
        """Initialize a deferred LogLogLog instance for first use."""
        logger.info(f"Initializing deferred LogLogLog for {self.path}")

        # Get file stats
        self._file_stat = await asyncio.to_thread(os.stat, self.path)
        logger.debug(f"File size: {self._file_stat.st_size:,} bytes")

        # Choose offset dtype based on file size
        self._offset_dtype = "I" if self._file_stat.st_size < (1 << 32) else "Q"

        # Check if index exists and is valid
        async def check_file_exists(path):
            return await asyncio.to_thread(path.exists)

        positions_exists, widths_exists, summaries_exists, file_size_exists = await asyncio.gather(
            check_file_exists(self._index_path / "positions.dat"),
            check_file_exists(self._index_path / "widths.dat"),
            check_file_exists(self._index_path / "summaries.dat"),
            check_file_exists(self._file_size_path),
        )

        index_exists = positions_exists and widths_exists and summaries_exists and file_size_exists

        if index_exists:
            try:
                # Try to open existing index
                await asyncio.to_thread(self._line_index.open, create=False)

                # Calculate last_position from last line offset
                if len(self._line_index) > 0:
                    last_offset = self._line_index.get_line_position(len(self._line_index) - 1)
                    self.log_file.seek_to(last_offset)
                    await self.log_file.aread_line()
                    last_position = self.log_file.get_position()
                else:
                    last_position = 0

                self.log_file.seek_to(last_position)

                # Check if file size has changed (shrunk = truncated)
                cached_file_size = await asyncio.to_thread(self._load_file_size)
                current_file_size = self._file_stat.st_size
                if cached_file_size is not None and current_file_size < cached_file_size:
                    logger.info("File truncated - invalidating cache")
                    raise Exception("File truncated")

            except Exception as e:
                logger.info(f"Failed to load existing index: {e}, rebuilding")
                index_exists = False

        if not index_exists:
            # Create new index
            await asyncio.to_thread(self._clear_index)
            await asyncio.to_thread(self._line_index.open, create=True)
            self.log_file.seek_to(0)

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
        self.log_file.seek_to(0)

    def close(self):
        """Close all resources."""
        # LogFile handles its own file management
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
        current_size = self.log_file.get_size()
        current_position = self.log_file.get_position()
        logger.debug(f"File size: {current_size:,}, position: {current_position:,}")

        if current_size < current_position:
            # File was truncated or rotated
            logger.info(
                f"File truncated/rotated - rebuilding index (size: {current_size:,}, pos: {current_position:,})"
            )
            self._clear_index()
            self._line_index.close()
            self._line_index.open(create=True)
            # Reset position to start over
            self.log_file.seek_to(0)

        # Stream process new content instead of reading entire file into RAM
        stream_start = time.time()

        # Process line by line to avoid loading huge files into memory
        width_count = 0
        process_start = time.time()

        while self.log_file.has_more_data():
            # Get raw byte position before reading line
            raw_pos = self.log_file.get_position()
            line = self.log_file.read_line()

            if line is None:
                break  # EOF

            # Calculate width and add to index
            width = self.get_width(line)
            self._line_index.append_line(raw_pos, width)
            width_count += 1

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
        current_file_size = self.log_file.get_size()
        self._save_file_size(current_file_size)

        logger.info(f"Total update time: {time.time() - start_time:.3f}s")

    async def aupdate(self):
        """Async version of update() method for non-blocking file processing."""
        start_time = time.time()

        # Initialize if this is a deferred instance
        if self._file_stat is None:
            await self._initialize_deferred()

        # Check if file has grown (use async methods)
        current_size = await self.log_file.aget_size()
        current_position = self.log_file.get_position()
        logger.debug(f"File size: {current_size:,}, position: {current_position:,}")

        if current_size < current_position:
            # File was truncated or rotated
            logger.info(
                f"File truncated/rotated - rebuilding index (size: {current_size:,}, pos: {current_position:,})"
            )
            await asyncio.to_thread(self._clear_index)
            self._line_index.close()
            self._line_index.open(create=True)
            # Reset position to start over
            self.log_file.seek_to(0)

        # Stream process new content instead of reading entire file into RAM
        stream_start = time.time()

        # Process line by line to avoid loading huge files into memory
        width_count = 0
        process_start = time.time()

        while await self.log_file.ahas_more_data():
            # Get raw byte position before reading line
            raw_pos = self.log_file.get_position()
            line = await self.log_file.aread_line()

            if line is None:
                break  # EOF

            # Calculate width and add to index (run width calculation in thread for CPU-bound work)
            width = await asyncio.to_thread(self.get_width, line)
            self._line_index.append_line(raw_pos, width)
            width_count += 1

            # Progress logging for large files
            if width_count % 100000 == 0:
                elapsed = time.time() - process_start
                rate = width_count / elapsed if elapsed > 0 else 0
                logger.info(f"Processed {width_count:,} lines in {elapsed:.1f}s ({rate:.0f} lines/sec)")
                # Yield control to allow other tasks to run
                await asyncio.sleep(0)

            # Yield control periodically for responsiveness
            if width_count % 1000 == 0:
                await asyncio.sleep(0)

        if width_count > 0:
            logger.debug(f"Stream processing took {time.time() - stream_start:.3f}s for {width_count:,} lines")

            # No tree update needed - summaries are created automatically during append
            # LineIndex handles flushing internally

        # Save current file size to cache metadata (run in thread for I/O)
        current_file_size = await self.log_file.aget_size()
        await asyncio.to_thread(self._save_file_size, current_file_size)

        logger.info(f"Total async update time: {time.time() - start_time:.3f}s")

    def append(self, line: str):
        """
        Append a line to the log file and update index.

        Args:
            line: Line to append (newline will be added)

        Raises:
            IOError: If LogFile was opened in read-only mode
        """
        # Get position before append
        raw_pos = self.log_file.get_size()

        # Write to file using LogFile
        self.log_file.append_line(line)

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

        # Save current position, seek to line, read it, restore position
        saved_position = self.log_file.get_position()
        self.log_file.seek_to(offset)
        line = self.log_file.read_line()
        self.log_file.seek_to(saved_position)

        return line if line is not None else ""

    def __len__(self) -> int:
        """Get total number of logical lines."""
        return len(self._line_index)

    def __iter__(self) -> Iterator[str]:
        """Iterate over all logical lines."""
        for i in range(len(self)):
            yield self[i]

    def width(self, width: int) -> WidthView:
        """
        Create a width-specific view of this log.

        Args:
            width: Terminal width for line wrapping

        Returns:
            WidthView instance for this width
        """
        return WidthView(self, width)

    # Public API methods for testing and monitoring

    def get_file_info(self) -> dict:
        """
        Get information about the log file.

        Returns:
            Dict with file size, current position, and other metadata.
        """
        return {
            "file_size": self.log_file.get_size(),
            "current_position": self.log_file.get_position(),
            "path": str(self.path),
            "total_lines": len(self._line_index),
        }

    def get_cache_info(self) -> dict:
        """
        Get information about the cache state.

        Returns:
            Dict with cache directory and status information.
        """
        return {
            "cache_dir": str(self._index_path),
            "has_index": (self._index_path / "positions.dat").exists(),
            "has_file_size_cache": self._file_size_path.exists(),
        }

    def line_at_row(self, row: int, width: int) -> Tuple[int, int]:
        """
        Find which logical line contains the given display row.

        Args:
            row: Display row number
            width: Terminal width

        Returns:
            Tuple of (line_number, offset_within_line)
        """
        return self._line_index.get_line_for_display_row(row, width)

    def row_for_line(self, line_no: int, width: int) -> int:
        """
        Get the display row where a logical line starts.

        Args:
            line_no: Logical line number
            width: Terminal width

        Returns:
            Display row number
        """
        return self._line_index.get_display_row_for_line(line_no, width)

    def total_rows(self, width: int) -> int:
        """
        Get total number of display rows at given width.

        Args:
            width: Terminal width

        Returns:
            Total display rows
        """
        return self._line_index.get_total_display_rows(width)
