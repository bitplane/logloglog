"""WrapTree B-tree implementation for efficient seeking."""

import mmap
from pathlib import Path
from typing import Tuple
from .index import WrapTreeNode, DisplayWidths


class WrapTree:
    """B-tree for efficient display row seeking."""

    def __init__(self, path: Path, display_widths: DisplayWidths):
        self.path = path / "wraptree.dat"
        self.display_widths = display_widths
        self._file = None
        self._mmap = None
        self._root_offset = 0
        self._next_offset = 0

        # Configuration
        self.max_leaf_lines = 1000  # Lines per leaf node

    def open(self, create: bool = False):
        """Open the wrap tree file."""
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            mode = "r+b" if self.path.exists() else "w+b"
        else:
            mode = "r+b"

        self._file = open(self.path, mode)

        # Get current size
        self._file.seek(0, 2)
        file_size = self._file.tell()

        if file_size == 0 and create:
            # Create initial root node
            root = WrapTreeNode()
            root.is_leaf = True
            self._write_node(0, root)
            self._root_offset = 0
            self._next_offset = WrapTreeNode.NODE_SIZE
        else:
            # Existing file
            self._next_offset = file_size

        # Create mmap if file has content
        if self._file.tell() > 0:
            self._file.seek(0)
            self._mmap = mmap.mmap(self._file.fileno(), self._file.tell())

    def close(self):
        """Close the tree file."""
        if self._mmap:
            self._mmap.close()
            self._mmap = None
        if self._file:
            self._file.close()
            self._file = None

    def _write_node(self, offset: int, node: WrapTreeNode):
        """Write a node to disk."""
        self._file.seek(offset)
        self._file.write(node.to_bytes())
        self._file.flush()

        # Update mmap
        if self._mmap:
            self._mmap.close()
        self._file.seek(0, 2)
        file_size = self._file.tell()
        if file_size > 0:
            self._file.seek(0)
            self._mmap = mmap.mmap(self._file.fileno(), file_size)

    def _read_node(self, offset: int) -> WrapTreeNode:
        """Read a node from disk."""
        if offset + WrapTreeNode.NODE_SIZE > len(self._mmap):
            raise ValueError(f"Invalid node offset: {offset}")

        data = self._mmap[offset : offset + WrapTreeNode.NODE_SIZE]
        return WrapTreeNode.from_bytes(data)

    def _allocate_node(self) -> int:
        """Allocate space for a new node."""
        offset = self._next_offset
        self._next_offset += WrapTreeNode.NODE_SIZE

        # Extend file
        self._file.seek(self._next_offset - 1)
        self._file.write(b"\0")
        self._file.flush()

        # Update mmap
        if self._mmap:
            self._mmap.close()
        self._file.seek(0)
        self._mmap = mmap.mmap(self._file.fileno(), self._next_offset)

        return offset

    def update_leaf(self, start_line: int, end_line: int):
        """Update tree with new lines."""
        # For now, simple implementation - just update the root if it's a leaf
        root = self._read_node(self._root_offset)

        if root.is_leaf and root.end_line == start_line:
            # Can append to root
            for line_no in range(start_line, end_line):
                width = self.display_widths.get(line_no)
                root.add_width(width)

            root.end_line = end_line
            self._write_node(self._root_offset, root)
        else:
            # TODO: Implement proper B-tree insertion
            pass

    def seek_display_row(self, row: int, terminal_width: int) -> Tuple[int, int]:
        """
        Find the logical line containing the given display row.

        Args:
            row: Display row number
            terminal_width: Terminal width for wrapping

        Returns:
            Tuple of (logical_line_number, offset_within_line)
        """
        return self._seek_in_node(self._root_offset, row, terminal_width, 0)

    def _seek_in_node(
        self, node_offset: int, target_row: int, terminal_width: int, rows_before: int
    ) -> Tuple[int, int]:
        """Recursively seek in a node."""
        node = self._read_node(node_offset)

        if node.is_leaf:
            # Scan actual widths
            current_row = rows_before

            for line_no in range(node.start_line, node.end_line):
                width = self.display_widths.get(line_no)
                line_rows = (width + terminal_width - 1) // terminal_width

                if current_row + line_rows > target_row:
                    # Found the line
                    offset_in_line = target_row - current_row
                    return (line_no, offset_in_line)

                current_row += line_rows

            # Row not in this leaf
            raise ValueError(f"Display row {target_row} not found")

        else:
            # Internal node - descend into appropriate child
            current_row = rows_before

            for i, child_offset in enumerate(node.child_offsets):
                child = self._read_node(child_offset)
                child_rows = child.estimate_rows(terminal_width)

                if current_row + child_rows > target_row:
                    # Descend into this child
                    return self._seek_in_node(child_offset, target_row, terminal_width, current_row)

                current_row += child_rows

            raise ValueError(f"Display row {target_row} not found")

    def get_total_rows(self, terminal_width: int) -> int:
        """Get total number of display rows at given width."""
        return self._calculate_total_rows(self._root_offset, terminal_width)

    def _calculate_total_rows(self, node_offset: int, terminal_width: int) -> int:
        """Recursively calculate total rows."""
        node = self._read_node(node_offset)

        if node.is_leaf:
            # Calculate exact rows from widths
            total = 0
            for line_no in range(node.start_line, node.end_line):
                width = self.display_widths.get(line_no)
                total += (width + terminal_width - 1) // terminal_width
            return total
        else:
            # Sum estimates from children
            return node.estimate_rows(terminal_width)
