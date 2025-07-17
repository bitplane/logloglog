"""Index data structures for LogLogLog."""

from pathlib import Path
from .core.array import Array


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
