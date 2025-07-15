"""Array-based WrapTree implementation for efficient seeking."""

import array
import logging
import time
from pathlib import Path
from typing import Tuple
from .index import DisplayWidths

# Configure logger
logger = logging.getLogger(__name__)


# Header layout (8 x uint32)
MAGIC = 0  # 0x4249474c (BIGL)
VERSION = 1  # File format version
INODE = 2  # File identity
CTIME = 3  # File creation time
ROOT_INDEX = 4  # Root node position (= 8 initially)
REAL_LENGTH = 5  # Actual used length (excluding pre-alloc)
RESERVED_6 = 6  # Future use
RESERVED_7 = 7  # Future use

HEADER_SIZE = 8
ROOT_NODE_START = 8  # First node always at index 8

# Node layout offsets
NODE_START_LINE = 0  # Starting line number
NODE_END_LINE = 1  # Ending line number (exclusive)
NODE_BUCKET_COUNT = 2  # Number of buckets in this node
NODE_PARENT = 3  # Parent node index (0 = no parent)
NODE_LEFT = 4  # Left child index (0 = no child)
NODE_RIGHT = 5  # Right child index (0 = no child)
NODE_NEXT = 6  # Next sibling index (0 = no sibling)
NODE_RESERVED = 7  # Reserved for future use
NODE_BUCKETS_START = 8  # Start of bucket data

# File format constants
BIGL_MAGIC = 0x4249474C
CURRENT_VERSION = 1
PREALLOC_SIZE = 1024  # Pre-allocate in chunks of 1024 uint32s


class WrapTree:
    """Array-based tree for efficient display row seeking."""

    def __init__(self, path: Path, display_widths: DisplayWidths):
        self.path = path / "wraptree.dat"
        self.display_widths = display_widths
        self._data = None
        self._file = None

    def open(self, create: bool = False):
        """Open the wrap tree file."""
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)

        if self.path.exists() and not create:
            # Load existing file
            self._load_existing()
        else:
            # Create new file
            self._create_new()

    def _load_existing(self):
        """Load existing array data from file."""
        with open(self.path, "rb") as f:
            data = f.read()

        if len(data) == 0:
            self._create_new()
            return

        # Load as uint32 array
        self._data = array.array("I")
        self._data.frombytes(data)

        # Validate header
        if len(self._data) < HEADER_SIZE or self._data[MAGIC] != BIGL_MAGIC:
            # Invalid file, recreate
            self._create_new()
            return

        # Check if upgrade needed
        if self._data[VERSION] < CURRENT_VERSION:
            self.upgrade()

    def _create_new(self):
        """Create new array with header and empty root node."""
        self._data = array.array("I")

        # Initialize header
        header = [0] * HEADER_SIZE
        header[MAGIC] = BIGL_MAGIC
        header[VERSION] = CURRENT_VERSION
        header[ROOT_INDEX] = ROOT_NODE_START
        header[REAL_LENGTH] = HEADER_SIZE + NODE_BUCKETS_START  # Header + empty root

        self._data.extend(header)

        # Initialize empty root node at index 8
        root_node = [0] * NODE_BUCKETS_START
        self._data.extend(root_node)

        # Pre-allocate space
        self._ensure_capacity(PREALLOC_SIZE)

        # Save to disk
        self._save()

    def _ensure_capacity(self, min_size: int):
        """Ensure array has at least min_size capacity."""
        current_size = len(self._data)
        if current_size >= min_size:
            return

        # Round up to next PREALLOC_SIZE boundary
        new_size = ((min_size + PREALLOC_SIZE - 1) // PREALLOC_SIZE) * PREALLOC_SIZE
        extend_by = new_size - current_size

        if extend_by > 0:
            self._data.extend([0] * extend_by)

    def _save(self):
        """Save array data to file."""
        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "wb") as f:
            f.write(self._data.tobytes())

    def close(self):
        """Close the tree and save data."""
        if self._data is not None:
            self._save()
            self._data = None

    def get_node_size(self, node_index: int) -> int:
        """Get the size of a node (including bucket data)."""
        if node_index == 0:
            return 0

        bucket_count = self._data[node_index + NODE_BUCKET_COUNT]
        # Each bucket has length + size = 2 values
        return NODE_BUCKETS_START + (bucket_count * 2)

    def add_width_to_node(self, node_index: int, width: int):
        """Add a width to a node's histogram."""
        bucket_count = self._data[node_index + NODE_BUCKET_COUNT]
        buckets_start = node_index + NODE_BUCKETS_START

        # Look for existing bucket with this width
        for i in range(bucket_count):
            width_idx = buckets_start + i
            if self._data[width_idx] == width:
                # Found existing bucket, increment count
                count_idx = buckets_start + bucket_count + i
                self._data[count_idx] += 1
                return

        # Need to add new bucket - append at end of current buckets
        self._ensure_capacity(buckets_start + (bucket_count + 1) * 2 + 1)

        # Add new width and count
        new_width_idx = buckets_start + bucket_count
        new_count_idx = buckets_start + bucket_count + 1 + bucket_count  # After all widths

        self._data[new_width_idx] = width
        self._data[new_count_idx] = 1

        # Update bucket count
        self._data[node_index + NODE_BUCKET_COUNT] += 1

        # Update real length
        new_real_length = buckets_start + (bucket_count + 1) * 2
        self._data[REAL_LENGTH] = max(self._data[REAL_LENGTH], new_real_length)

    def update_tree(self, total_lines: int):
        """Update tree structure for total number of lines."""
        start_time = time.time()
        logger.debug(f"Updating tree for {total_lines:,} lines")

        # For now, just update the root node
        root_index = self._data[ROOT_INDEX]

        # Build histogram using dict approach
        hist_start = time.time()
        width_counts = {}
        progress_interval = max(1, total_lines // 20)  # Log progress every 5%

        for line_no in range(total_lines):
            width = self.display_widths.get(line_no)
            width_counts[width] = width_counts.get(width, 0) + 1

            if line_no % progress_interval == 0 and line_no > 0:
                elapsed = time.time() - hist_start
                rate = line_no / elapsed
                pct = (line_no / total_lines) * 100
                logger.debug(f"Histogram progress: {pct:.1f}% ({line_no:,}/{total_lines:,}) at {rate:.0f} lines/sec")

        hist_time = time.time() - hist_start
        logger.debug(f"Histogram build took {hist_time:.3f}s - {len(width_counts)} unique widths")

        # Convert to sorted lists
        sort_start = time.time()
        widths = sorted(width_counts.keys())
        counts = [width_counts[w] for w in widths]
        bucket_count = len(widths)
        logger.debug(f"Sort took {time.time() - sort_start:.3f}s")

        # Update node
        write_start = time.time()
        self._data[root_index + NODE_START_LINE] = 0
        self._data[root_index + NODE_END_LINE] = total_lines
        self._data[root_index + NODE_BUCKET_COUNT] = bucket_count

        # Write bucket data: [width1, width2, ...] [count1, count2, ...]
        buckets_start = root_index + NODE_BUCKETS_START
        self._ensure_capacity(buckets_start + bucket_count * 2)

        # Write widths
        for i, width in enumerate(widths):
            self._data[buckets_start + i] = width

        # Write counts
        for i, count in enumerate(counts):
            self._data[buckets_start + bucket_count + i] = count

        # Update real length
        self._data[REAL_LENGTH] = buckets_start + bucket_count * 2
        logger.debug(f"Array write took {time.time() - write_start:.3f}s")

        total_time = time.time() - start_time
        logger.debug(f"Tree update complete in {total_time:.3f}s (histogram: {hist_time:.3f}s)")

    def estimate_rows_for_node(self, node_index: int, terminal_width: int) -> int:
        """Estimate display rows for a node at given terminal width."""
        if node_index == 0:
            return 0

        bucket_count = self._data[node_index + NODE_BUCKET_COUNT]
        if bucket_count == 0:
            return 0

        buckets_start = node_index + NODE_BUCKETS_START
        total_rows = 0

        for i in range(bucket_count):
            bucket_width = self._data[buckets_start + i]
            bucket_count_val = self._data[buckets_start + bucket_count + i]

            rows_per_line = max(1, (bucket_width + terminal_width - 1) // terminal_width)
            total_rows += bucket_count_val * rows_per_line

        return total_rows

    def get_total_rows(self, terminal_width: int) -> int:
        """Get total number of display rows at given width."""
        root_index = self._data[ROOT_INDEX]
        return self.estimate_rows_for_node(root_index, terminal_width)

    def seek_display_row(self, row: int, terminal_width: int) -> Tuple[int, int]:
        """Find the logical line containing the given display row."""
        root_index = self._data[ROOT_INDEX]
        return self._seek_in_node(root_index, row, terminal_width, 0)

    def _seek_in_node(self, node_index: int, target_row: int, terminal_width: int, rows_before: int) -> Tuple[int, int]:
        """Recursively seek in a node."""
        if node_index == 0:
            raise ValueError(f"Display row {target_row} not found")

        start_line = self._data[node_index + NODE_START_LINE]
        end_line = self._data[node_index + NODE_END_LINE]
        left_child = self._data[node_index + NODE_LEFT]
        right_child = self._data[node_index + NODE_RIGHT]

        # If this is a leaf node (no children), scan actual widths
        if left_child == 0 and right_child == 0:
            current_row = rows_before

            for line_no in range(start_line, end_line):
                width = self.display_widths.get(line_no)
                line_rows = max(1, (width + terminal_width - 1) // terminal_width)

                if current_row + line_rows > target_row:
                    # Found the line
                    offset_in_line = target_row - current_row
                    return (line_no, offset_in_line)

                current_row += line_rows

            raise ValueError(f"Display row {target_row} not found in leaf")

        # Internal node - check children
        if left_child != 0:
            left_rows = self.estimate_rows_for_node(left_child, terminal_width)
            if rows_before + left_rows > target_row:
                return self._seek_in_node(left_child, target_row, terminal_width, rows_before)
            rows_before += left_rows

        if right_child != 0:
            return self._seek_in_node(right_child, target_row, terminal_width, rows_before)

        raise ValueError(f"Display row {target_row} not found")

    def upgrade(self):
        """Upgrade file format and compact data."""
        # TODO: Implement compaction
        # For now, just update version
        self._data[VERSION] = CURRENT_VERSION
        self._save()
