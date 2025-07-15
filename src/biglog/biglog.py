"""Main BigLog implementation."""

import os
from pathlib import Path
from typing import Callable, List, Iterator, Tuple
from wcwidth import wcswidth
import platformdirs

from .logview import LogView
from .index import IndexMetadata, DisplayWidths
from .wraptree import WrapTree


def default_get_width(line: str) -> int:
    """Default width calculation using wcwidth."""
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

        # File tracking
        self._file = None
        self._file_stat = None
        self._last_position = 0
        self._line_offsets = []  # Cached line start positions

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
        # Get file stats
        self._file_stat = os.stat(self.path)

        # Check if index is valid
        if self._metadata.validate(self._file_stat):
            # Load existing index
            metadata = self._metadata.load()
            self._last_position = metadata.get("last_position", 0)
            self._line_offsets = metadata.get("line_offsets", [])

            self._display_widths.open(create=False)
            self._wraptree.open(create=False)
        else:
            # Create new index
            self._clear_index()
            self._display_widths.open(create=True)
            self._wraptree.open(create=True)

        # Open log file
        self._file = open(self.path, "r+b")

        # Update index with any new content
        self.update()

    def _clear_index(self):
        """Clear the index directory."""
        import shutil

        if self._index_path.exists():
            shutil.rmtree(self._index_path)
        self._last_position = 0
        self._line_offsets = []

    def close(self):
        """Close all resources."""
        if self._file:
            self._file.close()
            self._file = None
        self._display_widths.close()
        self._wraptree.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def update(self):
        """Update index with new lines from the file."""
        # Check if file has grown
        self._file.seek(0, 2)  # Seek to end
        current_size = self._file.tell()

        if current_size < self._last_position:
            # File was truncated or rotated
            self._clear_index()
            self._display_widths.close()
            self._wraptree.close()
            self._display_widths.open(create=True)
            self._wraptree.open(create=True)

        # Read new content
        self._file.seek(self._last_position)
        new_content = self._file.read()

        if new_content:
            # Process new lines
            text = new_content.decode("utf-8", errors="replace")
            lines = text.split("\n")

            # Remove last empty element if text ends with newline
            if text.endswith("\n") and lines and lines[-1] == "":
                lines.pop()

            # Index new lines
            start_line = len(self._line_offsets)

            for line in lines:
                # Record line offset
                self._line_offsets.append(self._last_position)

                # Calculate and store width
                width = self.get_width(line)
                self._display_widths.append(width)

                # Update position (line + newline)
                line_bytes = len(line.encode("utf-8")) + 1
                self._last_position += line_bytes

            # Update tree
            if lines:
                end_line = len(self._line_offsets)
                self._wraptree.update_leaf(start_line, end_line)

            # Save metadata
            self._save_metadata()

    def _save_metadata(self):
        """Save index metadata."""
        metadata = {
            "version": 1,
            "last_position": self._last_position,
            "line_offsets": self._line_offsets,
            "line_count": len(self._line_offsets),
            "ctime": self._file_stat.st_ctime,
            "size": self._file_stat.st_size,
        }
        self._metadata.save(metadata)

    def append(self, line: str):
        """
        Append a line to the log file and update index.

        Args:
            line: Line to append (newline will be added)
        """
        # Write to file
        self._file.seek(0, 2)  # Seek to end
        data = (line + "\n").encode("utf-8")
        self._file.write(data)
        self._file.flush()

        # Update our position tracking
        self._line_offsets.append(self._last_position)
        self._last_position += len(data)

        # Update index
        width = self.get_width(line)
        self._display_widths.append(width)

        # Update tree
        line_no = len(self._line_offsets) - 1
        self._wraptree.update_leaf(line_no, line_no + 1)

        # Update file stats
        self._file_stat = os.stat(self.path)
        self._save_metadata()

    def __getitem__(self, line_no: int) -> str:
        """Get a logical line by line number."""
        if line_no < 0:
            line_no = len(self) + line_no

        if line_no < 0 or line_no >= len(self._line_offsets):
            raise IndexError(f"Line {line_no} out of range")

        # Read the line from file
        start_offset = self._line_offsets[line_no]

        # Find end offset
        if line_no + 1 < len(self._line_offsets):
            end_offset = self._line_offsets[line_no + 1] - 1  # -1 for newline
        else:
            # Last line - read to current position or EOF
            end_offset = self._last_position

        # Read line
        self._file.seek(start_offset)
        data = self._file.read(end_offset - start_offset)

        # Decode and strip newline
        line = data.decode("utf-8", errors="replace")
        return line.rstrip("\n\r")

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
