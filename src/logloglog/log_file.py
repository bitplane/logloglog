"""Simple file abstraction for log file operations."""

import asyncio
from pathlib import Path
from typing import Optional, Union


class LogFile:
    """
    Simple file abstraction for reading and writing log files.

    Keeps file handle open during batch operations for performance.
    Call open() to start a batch read session, close() when done.
    Individual operations (append, get_size) open/close as needed.
    """

    def __init__(self, path: Union[Path, str], mode: str = "r"):
        """
        Initialize LogFile.

        Args:
            path: Path to the log file
            mode: File mode - "r" for read-only, "a" for append, "w" for write
        """
        self.path = Path(path)
        self.mode = mode
        self._read_position = 0
        self._file_handle = None

        # Validate mode
        if mode not in ("r", "a", "w"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'r', 'a', or 'w'")

        # Create file if it doesn't exist and we're in write/append mode
        if mode in ("a", "w") and not self.path.exists():
            self.path.touch()

    def open(self):
        """Open the file for reading. Call this before batch read operations."""
        if self._file_handle is None:
            self._file_handle = open(self.path, "rb")
            self._file_handle.seek(self._read_position)

    def close(self):
        """Close the file handle. Call this after batch operations complete."""
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None

    def read_line(self) -> Optional[str]:
        """
        Read the next line from the current position.

        Returns:
            The next line without trailing newline, or None if no more data.
        """
        try:
            # Use open file handle if available, otherwise open temporarily
            if self._file_handle is not None:
                line_bytes = self._file_handle.readline()
                if line_bytes:
                    self._read_position = self._file_handle.tell()
                    return line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
            else:
                # Fallback for when no batch session is open
                with open(self.path, "rb") as f:
                    f.seek(self._read_position)
                    line_bytes = f.readline()
                    if line_bytes:
                        self._read_position = f.tell()
                        return line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
        except (IOError, OSError):
            pass
        return None

    def read_all_lines(self) -> list[str]:
        """
        Read all remaining lines from current position.

        Returns:
            List of lines without trailing newlines.
        """
        lines = []
        while line := self.read_line():
            lines.append(line)
        return lines

    def append_line(self, line: str) -> None:
        """
        Append a line to the file.

        Args:
            line: Line to append (newline will be added automatically)

        Raises:
            IOError: If file is opened in read-only mode
        """
        if self.mode == "r":
            raise IOError("Cannot write to file opened in read-only mode")

        with open(self.path, "ab") as f:
            # Ensure line ends with newline
            if not line.endswith("\n"):
                line += "\n"
            f.write(line.encode("utf-8"))

    def append_lines(self, lines: list[str]) -> None:
        """
        Append multiple lines to the file.

        Args:
            lines: Lines to append (newlines will be added as needed)
        """
        if self.mode == "r":
            raise IOError("Cannot write to file opened in read-only mode")

        with open(self.path, "ab") as f:
            for line in lines:
                if not line.endswith("\n"):
                    line += "\n"
                f.write(line.encode("utf-8"))

    def has_more_data(self) -> bool:
        """
        Check if there's more data available to read.

        Returns:
            True if file has grown beyond current read position.
        """
        try:
            return self.path.stat().st_size > self._read_position
        except (IOError, OSError):
            return False

    def get_size(self) -> int:
        """
        Get current file size in bytes.

        Returns:
            File size in bytes, or 0 if file doesn't exist.
        """
        try:
            return self.path.stat().st_size
        except (IOError, OSError):
            return 0

    def seek_to(self, position: int) -> None:
        """
        Set the read position.

        Args:
            position: Byte position to seek to
        """
        self._read_position = max(0, position)

    def get_position(self) -> int:
        """
        Get current read position.

        Returns:
            Current byte position for reads.
        """
        return self._read_position

    def reset(self) -> None:
        """Reset read position to beginning of file."""
        self._read_position = 0

    # Async versions for Textual/asyncio compatibility

    async def aread_line(self) -> Optional[str]:
        """Async version of read_line()."""
        return await asyncio.to_thread(self.read_line)

    async def aread_all_lines(self) -> list[str]:
        """Async version of read_all_lines()."""
        return await asyncio.to_thread(self.read_all_lines)

    async def aappend_line(self, line: str) -> None:
        """Async version of append_line()."""
        await asyncio.to_thread(self.append_line, line)

    async def aappend_lines(self, lines: list[str]) -> None:
        """Async version of append_lines()."""
        await asyncio.to_thread(self.append_lines, lines)

    async def ahas_more_data(self) -> bool:
        """Async version of has_more_data()."""
        return await asyncio.to_thread(self.has_more_data)

    async def aget_size(self) -> int:
        """Async version of get_size()."""
        return await asyncio.to_thread(self.get_size)
