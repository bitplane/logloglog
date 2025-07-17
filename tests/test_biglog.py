"""Tests for BigLog functionality."""

import tempfile
import os
import pytest
from pathlib import Path
from biglog import BigLog


@pytest.fixture
def temp_log_file():
    """Create a temporary log file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def log_with_content(temp_cache_dir):
    """Create a log file with test content."""
    content = "Line 1\nLine 2\nLine 3\n"
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)
        yield log
        log.close()
    finally:
        os.unlink(log_path)


def test_empty_log(temp_log_file, temp_cache_dir):
    """Test with empty log file."""
    log = BigLog(temp_log_file, cache_dir=temp_cache_dir)
    assert len(log) == 0

    # Test empty view
    view = log.at(width=80)
    assert len(view) == 0
    log.close()


def test_simple_lines(temp_cache_dir):
    """Test with simple text lines."""
    content = "Hello world\nThis is line 2\nShort\nA very long line that should wrap at 80 characters and continue beyond that point"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)

        # Test basic access
        assert len(log) == 4
        assert log[0] == "Hello world"
        assert log[1] == "This is line 2"
        assert log[2] == "Short"
        assert log[3].startswith("A very long line")

        # Test iteration
        lines = list(log)
        assert len(lines) == 4

        log.close()
    finally:
        os.unlink(log_path)


def test_iteration(log_with_content):
    """Test line iteration."""
    lines = list(log_with_content)
    assert lines == ["Line 1", "Line 2", "Line 3"]


def test_append(temp_cache_dir):
    """Test appending lines."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Initial line\n")
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)

        assert len(log) == 1
        assert log[0] == "Initial line"

        # Append new lines
        log.append("Second line")
        log.append("Third line")

        assert len(log) == 3
        assert log[1] == "Second line"
        assert log[2] == "Third line"

        log.close()
    finally:
        os.unlink(log_path)


def test_update(temp_cache_dir):
    """Test updating with externally added lines."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Line 1\n")
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log) == 1

        # Externally append to file
        with open(log_path, "a") as f:
            f.write("Line 2\nLine 3\n")

        # Update should pick up new lines
        log.update()
        assert len(log) == 3
        assert log[1] == "Line 2"
        assert log[2] == "Line 3"

        log.close()
    finally:
        os.unlink(log_path)


def test_wrapped_view(temp_cache_dir):
    """Test LogView with wrapping."""
    # Create lines of known width
    content = "x" * 40 + "\n" + "y" * 120 + "\n" + "z" * 200

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)

        # View at width 80
        view = log.at(width=80)

        # Line 0: 40 chars -> 1 display row
        # Line 1: 120 chars -> 2 display rows (ceil(120/80) = 2)
        # Line 2: 200 chars -> 3 display rows (ceil(200/80) = 3)
        # Total: 6 display rows
        assert len(view) == 6

        # Test accessing wrapped portions
        assert view[0] == "x" * 40  # First line, full
        assert view[1] == "y" * 80  # Second line, first part
        assert view[2] == "y" * 40  # Second line, second part
        assert view[3] == "z" * 80  # Third line, first part
        assert view[4] == "z" * 80  # Third line, second part
        assert view[5] == "z" * 40  # Third line, third part

        log.close()
    finally:
        os.unlink(log_path)


def test_custom_width_function(temp_cache_dir):
    """Test with custom width calculation."""

    def custom_width(line: str) -> int:
        # Simple: each char is 1 unit
        return len(line)

    content = "abc\ndefgh\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, get_width=custom_width, cache_dir=temp_cache_dir)

        view = log.at(width=3)

        # Line 0: "abc" = 3 chars -> 1 row
        # Line 1: "defgh" = 5 chars -> 2 rows (ceil(5/3) = 2)
        assert len(view) == 3
        assert view[0] == "abc"
        assert view[1] == "def"
        assert view[2] == "gh"

        log.close()
    finally:
        os.unlink(log_path)


def test_index_persistence(temp_cache_dir):
    """Test that index persists across reopening."""
    content = "Line 1\nLine 2\nLine 3\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        # First open
        log1 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log1) == 3
        log1.close()

        # Second open - should reuse index
        log2 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log2) == 3
        assert log2[0] == "Line 1"
        log2.close()
    finally:
        os.unlink(log_path)


def test_context_manager(temp_cache_dir):
    """Test BigLog as context manager."""
    content = "Test line\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        with BigLog(log_path, cache_dir=temp_cache_dir) as log:
            assert len(log) == 1
            assert log[0] == "Test line"
    finally:
        os.unlink(log_path)


def test_cache_reuse(temp_cache_dir):
    """Test that cache is properly reused between sessions."""
    content = "Line 1\nLine 2\nLine 3\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        # First session - should build cache
        log1 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log1) == 3

        # Check that cache files were created
        index_files = list(temp_cache_dir.rglob("*"))
        assert len(index_files) > 0
        log1.close()

        # Second session - should reuse cache
        log2 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log2) == 3
        assert log2[0] == "Line 1"
        assert log2[1] == "Line 2"
        assert log2[2] == "Line 3"
        log2.close()
    finally:
        os.unlink(log_path)


def test_negative_indexing_biglog(log_with_content):
    """Test that negative indexing works in BigLog."""
    log = log_with_content

    # Should have 3 lines: "Line 1", "Line 2", "Line 3"
    assert len(log) == 3

    # Test negative indexing
    assert log[-1] == "Line 3"  # Last line
    assert log[-2] == "Line 2"  # Second to last
    assert log[-3] == "Line 1"  # First line

    # Should be same as positive indexing
    assert log[-1] == log[2]
    assert log[-2] == log[1]
    assert log[-3] == log[0]

    # Test out of bounds
    with pytest.raises(IndexError):
        _ = log[-4]  # Too negative

    with pytest.raises(IndexError):
        _ = log[3]  # Too positive


def test_view_with_real_file(temp_cache_dir):
    """Test view creation works with actual content."""
    content = "Short line\n" + "x" * 100 + "\nAnother line\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)

        # Should have 3 lines
        assert len(log) == 3

        # Create view at width 80
        view = log.at(80, 0)

        # View should have some rows (not 0)
        view_length = len(view)
        assert view_length > 0, f"View should have rows, got {view_length}"

        # Should be able to access first row
        first_row = view[0]
        assert first_row == "Short line"

        log.close()
    finally:
        os.unlink(log_path)


def test_tree_node_growth_issue(temp_cache_dir):
    """Test that demonstrates the tree node growth issue - should fail."""
    content = "Line 1\nLine 2\nLine 3\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)

        # First update - creates root node
        assert len(log) == 3
        original_root_offset = log._wraptree._data[4]  # ROOT_INDEX = 4

        # Add more content externally
        with open(log_path, "a") as f:
            f.write("Line 4\nLine 5\n")

        # Update should handle growing tree
        log.update()
        assert len(log) == 5

        # Root offset shouldn't change (proper in-place update)
        # This will FAIL because we're appending new nodes instead of updating in place
        assert (
            log._wraptree._data[4] == original_root_offset
        ), "Root offset changed - tree nodes not being updated in place"

        log.close()
    finally:
        os.unlink(log_path)


def test_cache_validation_scenarios(temp_cache_dir):
    """Test various cache validation scenarios."""
    content = "Line 1\nLine 2\nLine 3\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        # First open - should create cache
        log1 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log1) == 3

        # Check that index files were created
        assert log1._line_offsets_path.exists()
        assert (log1._index_path / "display_widths.dat").exists()
        assert (log1._index_path / "wraptree.dat").exists()
        assert len(log1._line_offsets) == 3

        log1.close()

        # Second open - should validate and reuse cache
        log2 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log2) == 3

        # Should have loaded the existing index (same number of lines)
        assert len(log2._line_offsets) == 3

        log2.close()

    finally:
        os.unlink(log_path)


def test_file_modification_detection(temp_cache_dir):
    """Test that file modifications are detected properly."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Line 1\nLine 2\n")
        log_path = f.name

    try:
        # Create initial cache
        log1 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log1) == 2
        original_last_pos = log1._last_position

        log1.close()

        # Modify file externally
        import time

        time.sleep(0.1)  # Ensure different timestamp
        with open(log_path, "a") as f:
            f.write("Line 3\nLine 4\n")

        # Reopen - should detect changes and update
        log2 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log2) == 4
        assert log2._last_position > original_last_pos
        log2.close()

    finally:
        os.unlink(log_path)


def test_file_truncation_detection(temp_cache_dir):
    """Test that file truncation is detected properly."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Line 1\nLine 2\nLine 3\nLine 4\n")
        log_path = f.name

    try:
        # Create cache with full file
        log1 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log1) == 4

        log1.close()

        # Truncate file
        with open(log_path, "w") as f:
            f.write("New line 1\nNew line 2\n")

        # Reopen - should detect truncation and rebuild
        log2 = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log2) == 2
        assert log2[0] == "New line 1"
        assert log2[1] == "New line 2"
        log2.close()

    finally:
        os.unlink(log_path)


def test_ascii_fast_path(temp_cache_dir):
    """Test that ASCII fast path works correctly."""
    from biglog.biglog import default_get_width

    # ASCII lines should be fast and correct
    assert default_get_width("hello world") == 11
    assert default_get_width("") == 0
    assert default_get_width("timestamp: 2023-01-01 12:00:00") == 30

    # Unicode should still work
    assert default_get_width("café") == 4
    assert default_get_width("日本語") == 6


def test_cache_directory_creation(temp_cache_dir):
    """Test that cache directories are created as needed."""
    content = "test line\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        # Use a nested cache directory that doesn't exist
        nested_cache = temp_cache_dir / "deep" / "nested" / "cache"

        # Should create the directory structure automatically
        log = BigLog(log_path, cache_dir=nested_cache)
        assert len(log) == 1

        # Verify cache files were created
        cache_dirs = list(nested_cache.glob("*"))
        assert len(cache_dirs) > 0, "Cache directory should have been created"

        log.close()

    finally:
        os.unlink(log_path)
