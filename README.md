# BigLog

A Python library for efficient scrollback indexing of large log files with terminal word wrapping support.

## Overview

BigLog provides O(log n) seeking and scrolling through arbitrarily large logs at any terminal width, using an on-disk B-tree index with histogram-based summaries.

## Features

- **Efficient random access** by display row at any terminal width
- **Incremental indexing** - only new lines are indexed on updates
- **Memory-efficient** - uses mmap for large files
- **Cross-platform** - works on Linux, macOS, and Windows
- **Pluggable width calculation** - customize how line widths are computed
- **Log rotation aware** - handles file rotation and truncation

## Installation

```bash
pip install biglog
```

## Quick Start

```python
from biglog import BigLog

# Open a log file
log = BigLog("/var/log/app.log")

# Access by logical line number
print(f"Line 1000: {log[1000]}")
print(f"Total lines: {len(log)}")

# Create a view at specific terminal width
view = log.at(width=80, start=5000)
for row in view:
    print(row)  # Prints wrapped lines starting from display row 5000
```

## API Reference

### BigLog

```python
class BigLog:
    def __init__(self, path: Path | str,
                 get_width: Callable[[str], int] = None,
                 split_lines: Callable[[str], List[str]] = None,
                 cache_dir: Path = None):
        """
        Initialize BigLog index for a file.

        Args:
            path: Log file to index
            get_width: Function to calculate display width of a line (defaults to wcwidth)
            split_lines: Function to split input into lines (defaults to splitting on \n)
            cache_dir: Where to store index files (auto-detect if None)
        """

    def __getitem__(self, line_no: int) -> str:
        """Get logical line by line number"""

    def __len__(self) -> int:
        """Total number of logical lines in file"""

    def __iter__(self) -> Iterator[str]:
        """Iterate over all logical lines"""

    def append(self, line: str):
        """Append line to the log file and update index"""

    def update(self):
        """Re-scan file for new lines and update index"""

    def at(self, width: int, start: int = 0, end: int = None) -> LogView:
        """Create a view at given terminal width, starting from display row"""
```

### LogView

```python
class LogView:
    def __getitem__(self, row_no: int) -> str:
        """Get text at display row (may be partial line if wrapped)"""

    def __len__(self) -> int:
        """Total number of display rows in this view"""

    def __iter__(self) -> Iterator[str]:
        """Iterate over display rows"""
```

## Examples

### Custom Width Function

```python
def my_width_func(line: str) -> int:
    # Custom logic for calculating display width
    # Handle tabs, ANSI sequences, emoji, etc.
    return len(line)  # Simple example

log = BigLog("/var/log/app.log", get_width=my_width_func)
```

### Appending and Updating

```python
log = BigLog("/var/log/app.log")

# Append new lines
log.append("New log entry")

# Update index for externally added lines
log.update()
```

### Viewing Specific Ranges

```python
# View rows 1000-2000 at 80 character width
view = log.at(width=80, start=1000, end=2000)

for i, row in enumerate(view):
    print(f"Row {1000 + i}: {row}")
```

## Implementation Details

### Data Structures

1. **display_widths.dat** - Array of uint16 values storing the display width of each logical line
2. **wraptree.dat** - B-tree index with histogram nodes for efficient seeking
3. **metadata.json** - Index metadata including file stats and indexing position

### Cache Location

- Linux/macOS: `~/.cache/biglog/`
- Windows: `%LOCALAPPDATA%\biglog\`

Index files are named by device ID and inode (or equivalent on Windows) to handle file moves and symlinks correctly.

### Index Management

- **File tracking**: Uses inode (Unix) or file ID (Windows) so moving/renaming files doesn't require reindexing
- **Symlink resolution**: Soft links are resolved to their targets before indexing
- **Rotation detection**: Stores file creation time and length - if creation time changes (e.g., log rotation), the index is rebuilt
- **Incremental updates**: Only new lines are indexed when file grows
- **Works with /var/log**: Handles log rotation scenarios common in system logs

## Development

```bash
# Clone the repo
git clone https://github.com/yourusername/biglog
cd biglog

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run example
python examples/basic_usage.py
```

## License

MIT

## Performance

BigLog is designed to handle extremely large log files (terabytes) efficiently:

- **O(log n) seeking** to any display row
- **O(1) append** operations
- **Minimal memory usage** via mmap
- **Scales to trillions of lines**

The B-tree index with histogram summaries allows for fast estimation of display rows at any terminal width without storing separate indices for each width.