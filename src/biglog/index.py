"""Index data structures for BigLog."""

import struct
import mmap
import os
from pathlib import Path
import json
import numpy as np


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

    def get_range(self, start: int, end: int) -> np.ndarray:
        """Get display widths for a range of lines."""
        if start < 0 or end > self._count:
            raise IndexError(f"Range [{start}:{end}) out of bounds")

        offset = start * 2
        size = (end - start) * 2
        data = self._mmap[offset : offset + size]

        # Convert to numpy array for efficient operations
        return np.frombuffer(data, dtype=np.uint16)

    def __len__(self) -> int:
        """Get number of stored widths."""
        return self._count


class WrapTreeNode:
    """A node in the WrapTree B-tree."""

    # Node size is 256 bytes
    NODE_SIZE = 256
    HISTOGRAM_BUCKETS = 16
    MAX_FANOUT = 20  # Max children for internal nodes

    # Histogram bucket boundaries (log-scale)
    BUCKET_BOUNDARIES = [0, 40, 60, 80, 100, 120, 160, 200, 250, 300, 400, 500, 750, 1000, 2000, 5000, 65536]

    def __init__(self):
        self.start_line = 0
        self.end_line = 0
        self.is_leaf = True
        self.fanout = 0
        self.histogram = np.zeros(self.HISTOGRAM_BUCKETS, dtype=np.uint16)
        self.child_offsets = []

    def find_bucket(self, width: int) -> int:
        """Find histogram bucket for a display width."""
        for i in range(len(self.BUCKET_BOUNDARIES) - 1):
            if width < self.BUCKET_BOUNDARIES[i + 1]:
                return i
        return self.HISTOGRAM_BUCKETS - 1

    def bucket_center(self, bucket: int) -> int:
        """Get representative width for a bucket."""
        low = self.BUCKET_BOUNDARIES[bucket]
        high = self.BUCKET_BOUNDARIES[bucket + 1]
        return (low + high) // 2

    def add_width(self, width: int):
        """Add a width to the histogram."""
        bucket = self.find_bucket(width)
        self.histogram[bucket] += 1

    def estimate_rows(self, terminal_width: int) -> int:
        """Estimate display rows for this node at given terminal width."""
        total = 0
        for bucket in range(self.HISTOGRAM_BUCKETS):
            count = self.histogram[bucket]
            if count > 0:
                center = self.bucket_center(bucket)
                rows_per_line = (center + terminal_width - 1) // terminal_width
                total += count * rows_per_line
        return total

    def to_bytes(self) -> bytes:
        """Serialize node to bytes."""
        data = bytearray(self.NODE_SIZE)

        # Header
        struct.pack_into("<QQBBxxxxxx", data, 0, self.start_line, self.end_line, self.is_leaf, self.fanout)

        # Histogram (16 * 2 bytes = 32 bytes)
        offset = 24
        for i in range(self.HISTOGRAM_BUCKETS):
            struct.pack_into("<H", data, offset + i * 2, self.histogram[i])

        # Child offsets (up to MAX_FANOUT * 8 bytes)
        offset = 56
        for i, child_offset in enumerate(self.child_offsets[: self.MAX_FANOUT]):
            struct.pack_into("<Q", data, offset + i * 8, child_offset)

        return bytes(data)

    @classmethod
    def from_bytes(cls, data: bytes) -> "WrapTreeNode":
        """Deserialize node from bytes."""
        node = cls()

        # Header
        (node.start_line, node.end_line, node.is_leaf, node.fanout) = struct.unpack_from("<QQBBxxxxxx", data, 0)

        # Histogram
        offset = 24
        for i in range(cls.HISTOGRAM_BUCKETS):
            node.histogram[i] = struct.unpack_from("<H", data, offset + i * 2)[0]

        # Child offsets
        offset = 56
        node.child_offsets = []
        for i in range(node.fanout):
            child_offset = struct.unpack_from("<Q", data, offset + i * 8)[0]
            node.child_offsets.append(child_offset)

        return node
