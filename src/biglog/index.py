"""Index data structures for BigLog."""

import os
from pathlib import Path
import json
from .array import Array


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
        self._array = None

    def open(self, create: bool = False):
        """Open the display widths file."""
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            mode = "w+b" if not self.path.exists() else "r+b"
        else:
            mode = "r+b"

        self._array = Array("H", str(self.path), mode)  # uint16

    def close(self):
        """Close the file."""
        if self._array:
            self._array.close()
            self._array = None

    def append(self, width: int):
        """Append a display width."""
        if width > 65535:
            width = 65535  # Cap at uint16 max
        self._array.append(width)

    def get(self, line_no: int) -> int:
        """Get display width for a line."""
        return self._array[line_no]

    def get_range(self, start: int, end: int) -> list:
        """Get display widths for a range of lines."""
        # Return a list of widths for compatibility
        return [self._array[i] for i in range(start, end)]

    def __len__(self) -> int:
        """Get number of stored widths."""
        return len(self._array)


# WrapTreeNode removed - using array-based storage in WrapTree instead
