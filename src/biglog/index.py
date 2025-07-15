"""Index data structures for BigLog."""

import struct
import mmap
import os
from pathlib import Path
import json
import array


class IndexMetadata:
    """Metadata for the index files."""

    def __init__(self, path: Path):
        self.path = path
        self.metadata_file = path / "metadata.json"

    def load(self) -> dict:
        """Load metadata from disk."""
        if self.metadata_file.exists():
            with open(self.metadata_file, "r") as f:
                return json.load(f)
        return {}

    def save(self, metadata: dict):
        """Save metadata to disk."""
        self.path.mkdir(parents=True, exist_ok=True)
        with open(self.metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

    def validate(self, file_stat: os.stat_result) -> bool:
        """Check if index is valid for given file stats."""
        metadata = self.load()
        if not metadata:
            return False

        # Check if creation time matches (indicates file rotation)
        if "ctime" in metadata and metadata["ctime"] != file_stat.st_ctime:
            return False

        # Check if file got smaller (indicates truncation)
        if "size" in metadata and metadata["size"] > file_stat.st_size:
            return False

        return True


class DisplayWidths:
    """Manages the display_widths.dat file."""

    def __init__(self, path: Path):
        self.path = path / "display_widths.dat"
        self._file = None
        self._mmap = None
        self._count = 0

    def open(self, create: bool = False):
        """Open the display widths file."""
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            mode = "r+b" if self.path.exists() else "w+b"
        else:
            mode = "r+b"

        self._file = open(self.path, mode)

        # Get current size
        self._file.seek(0, 2)  # Seek to end
        file_size = self._file.tell()
        self._count = file_size // 2  # Each width is uint16 (2 bytes)

        # Create mmap if file has content
        if file_size > 0:
            self._file.seek(0)
            self._mmap = mmap.mmap(self._file.fileno(), file_size)

    def close(self):
        """Close the file."""
        if self._mmap:
            self._mmap.close()
            self._mmap = None
        if self._file:
            self._file.close()
            self._file = None

    def append(self, width: int):
        """Append a display width."""
        if width > 65535:
            width = 65535  # Cap at uint16 max

        # Write to end of file
        self._file.seek(0, 2)
        self._file.write(struct.pack("<H", width))
        self._file.flush()

        # Recreate mmap with new size
        if self._mmap:
            self._mmap.close()

        file_size = self._file.tell()
        if file_size > 0:
            self._file.seek(0)
            self._mmap = mmap.mmap(self._file.fileno(), file_size)

        self._count += 1

    def get(self, line_no: int) -> int:
        """Get display width for a line."""
        if line_no < 0 or line_no >= self._count:
            raise IndexError(f"Line {line_no} out of range")

        offset = line_no * 2
        data = self._mmap[offset : offset + 2]
        return struct.unpack("<H", data)[0]

    def get_range(self, start: int, end: int) -> array.array:
        """Get display widths for a range of lines."""
        if start < 0 or end > self._count:
            raise IndexError(f"Range [{start}:{end}) out of bounds")

        offset = start * 2
        size = (end - start) * 2
        data = self._mmap[offset : offset + size]

        # Convert to array for efficient operations
        result = array.array("H")  # uint16
        result.frombytes(data)
        return result

    def __len__(self) -> int:
        """Get number of stored widths."""
        return self._count


# WrapTreeNode removed - using array-based storage in WrapTree instead
