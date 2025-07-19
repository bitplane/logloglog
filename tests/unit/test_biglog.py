"""Tests for LogLogLog functionality."""

import tempfile
import os
import pytest
from pathlib import Path
from logloglog import LogLogLog
from logloglog.cache import Cache


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
        log = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        yield log
        log.close()
    finally:
        os.unlink(log_path)


def test_empty_log(temp_log_file, temp_cache_dir):
    """Test with empty log file."""
    log = LogLogLog(temp_log_file, cache=Cache(temp_cache_dir))
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
        log = LogLogLog(log_path, cache=Cache(temp_cache_dir))

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
        log = LogLogLog(log_path, cache=Cache(temp_cache_dir))

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
        log = LogLogLog(log_path, cache=Cache(temp_cache_dir))
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
        log = LogLogLog(log_path, cache=Cache(temp_cache_dir))

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
        log = LogLogLog(log_path, get_width=custom_width, cache=Cache(temp_cache_dir))

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
        log1 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log1) == 3
        log1.close()

        # Second open - should reuse index
        log2 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log2) == 3
        assert log2[0] == "Line 1"
        log2.close()
    finally:
        os.unlink(log_path)


def test_context_manager(temp_cache_dir):
    """Test LogLogLog as context manager."""
    content = "Test line\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        with LogLogLog(log_path, cache=Cache(temp_cache_dir)) as log:
            assert len(log) == 1
            assert log[0] == "Test line"
    finally:
        os.unlink(log_path)


def test_negative_indexing_logloglog(log_with_content):
    """Test that negative indexing works in LogLogLog."""
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
        log = LogLogLog(log_path, cache=Cache(temp_cache_dir))

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


def test_file_modification_detection(temp_cache_dir):
    """Test that file modifications are detected properly."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Line 1\nLine 2\n")
        log_path = f.name

    try:
        # Create initial cache
        log1 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log1) == 2
        original_last_pos = log1._last_position

        log1.close()

        # Modify file externally
        import time

        time.sleep(0.1)  # Ensure different timestamp
        with open(log_path, "a") as f:
            f.write("Line 3\nLine 4\n")

        # Reopen - should detect changes and update
        log2 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
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
        log1 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log1) == 4

        log1.close()

        # Truncate file
        with open(log_path, "w") as f:
            f.write("New line 1\nNew line 2\n")

        # Reopen - should detect truncation and rebuild
        log2 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log2) == 2
        assert log2[0] == "New line 1"
        assert log2[1] == "New line 2"
        log2.close()

    finally:
        os.unlink(log_path)


def test_ascii_fast_path(temp_cache_dir):
    """Test that ASCII fast path works correctly."""
    from logloglog.logloglog import default_get_width

    # ASCII lines should be fast and correct
    assert default_get_width("hello world") == 11
    assert default_get_width("") == 0
    assert default_get_width("timestamp: 2023-01-01 12:00:00") == 30

    # Unicode should still work
    assert default_get_width("café") == 4
    assert default_get_width("日本語") == 6


def test_default_split_lines_edge_cases():
    """Test default_split_lines function with different line endings."""
    from logloglog.logloglog import default_split_lines

    # Test Windows line endings (\r\n)
    text_windows = "line1\r\nline2\r\nline3\r\n"
    lines = default_split_lines(text_windows)
    assert lines == ["line1", "line2", "line3"]

    # Test Mac line endings (\r) - note: \r doesn't add final newline check
    text_mac = "line1\rline2\rline3"
    lines = default_split_lines(text_mac)
    assert lines == ["line1", "line2", "line3"]

    # Test mixed line endings
    text_mixed = "line1\r\nline2\nline3"
    lines = default_split_lines(text_mixed)
    assert lines == ["line1", "line2", "line3"]

    # Test text not ending with newline
    text_no_newline = "line1\nline2\nline3"
    lines = default_split_lines(text_no_newline)
    assert lines == ["line1", "line2", "line3"]


def test_logloglog_indexerror_out_of_bounds(log_with_content):
    """Test IndexError when accessing out of bounds line in empty read."""
    log = log_with_content

    # Mock a scenario where file.readline() returns empty (EOF)
    # This is hard to reproduce naturally, but we can test the boundary
    total_lines = len(log)

    # Test normal access works
    assert log[total_lines - 1] is not None

    # Test out of bounds access
    with pytest.raises(IndexError, match="Line .* out of range"):
        _ = log[total_lines + 100]


def test_corrupted_index_recovery(temp_cache_dir):
    """Test recovery when index files are corrupted."""
    content = "Line 1\nLine 2\nLine 3\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        # First, create a valid index
        log1 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log1) == 3
        index_path = log1._index_path
        log1.close()

        # Corrupt the line_offsets file
        corrupted_offsets_path = index_path / "line_offsets.dat"
        with open(corrupted_offsets_path, "wb") as f:
            f.write(b"corrupted data that will cause errors")

        # Should detect corruption and rebuild
        log2 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log2) == 3  # Should still work after rebuild
        assert log2[0] == "Line 1"
        log2.close()

    finally:
        os.unlink(log_path)


def test_custom_split_lines_function(temp_cache_dir):
    """Test LogLogLog with custom split_lines function."""

    # Test that custom split_lines function is stored and accessible
    def custom_split(text: str):
        # Split on semicolons instead of newlines
        lines = text.split(";")
        # Remove empty trailing element if text ends with separator
        if text.endswith(";"):
            lines.pop()
        return lines

    content = "line1\nline2\nline3\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = LogLogLog(log_path, split_lines=custom_split, cache=Cache(temp_cache_dir))

        # Verify the custom split function was assigned
        assert log.split_lines == custom_split

        # Test the function directly
        test_text = "a;b;c;"
        result = log.split_lines(test_text)
        assert result == ["a", "b", "c"]

        log.close()

    finally:
        os.unlink(log_path)


@pytest.fixture
def temp_log_with_content(temp_cache_dir):
    """Create a temporary log file with test content."""
    content = "Line 1\nLine 2\nLine 3\n"
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    yield log_path, temp_cache_dir
    os.unlink(log_path)


def test_index_loading_with_existing_offsets(temp_log_with_content):
    """Test loading index with existing line data."""
    log_path, cache_dir = temp_log_with_content

    # First, create a valid index
    log1 = LogLogLog(log_path, cache=Cache(cache_dir))
    assert len(log1) == 3
    # Verify we can access lines (confirms index exists)
    assert log1[0] == "Line 1"
    assert log1[1] == "Line 2"
    assert log1[2] == "Line 3"
    log1.close()

    # Now reopen - should load existing index
    log2 = LogLogLog(log_path, cache=Cache(cache_dir))
    assert len(log2) == 3
    # Verify lines are still accessible
    assert log2[0] == "Line 1"
    assert log2[1] == "Line 2"
    assert log2[2] == "Line 3"
    log2.close()


def test_file_truncation_scenario(temp_cache_dir):
    """Test file truncation detection to cover lines 220-232."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Line 1\nLine 2\nLine 3\nLine 4\n")
        log_path = f.name

    try:
        # Create cache with full file
        log1 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log1) == 4
        original_last_pos = log1._last_position
        log1.close()

        # Truncate file to be smaller
        with open(log_path, "w") as f:
            f.write("New content\n")

        # Reopen - should detect truncation and rebuild
        log2 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log2) == 1
        assert log2[0] == "New content"
        assert log2._last_position < original_last_pos
        log2.close()

    finally:
        os.unlink(log_path)


def test_index_cleanup_exception_handling(temp_log_with_content):
    """Test exception handling during index cleanup."""
    log_path, cache_dir = temp_log_with_content

    # Create a LogLogLog instance
    log = LogLogLog(log_path, cache=Cache(cache_dir))
    log.close()

    # Now corrupt an index file to trigger cleanup
    corrupted_file = log._index_path / "positions.dat"
    with open(corrupted_file, "wb") as f:
        f.write(b"corrupted")

    # This should trigger the exception handling during cleanup and rebuild
    log2 = LogLogLog(log_path, cache=Cache(cache_dir))
    assert len(log2) == 3  # Should still work after cleanup (fixture has 3 lines)
    log2.close()

    log.close()  # Original log close


def test_empty_index_loading(temp_cache_dir):
    """Test loading LogLogLog with completely empty index to cover lines 134-135."""
    # Create a log file with content first, then simulate empty index on reload
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Line 1\n")
        log_path = f.name

    try:
        # Create LogLogLog first to create index files
        log1 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log1) == 1
        index_path = log1._index_path
        log1.close()

        # Now create empty index files to simulate empty index scenario
        positions_file = index_path / "positions.dat"
        widths_file = index_path / "widths.dat"
        summaries_file = index_path / "summaries.dat"

        # Truncate index files to simulate empty index
        with open(positions_file, "wb") as f:
            pass  # Empty file
        with open(widths_file, "wb") as f:
            pass  # Empty file
        with open(summaries_file, "wb") as f:
            pass  # Empty file

        # Reopen - should handle empty index and rebuild
        log2 = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        assert len(log2) == 1  # Should rebuild from log file
        log2.close()
    finally:
        os.unlink(log_path)


def test_index_line_access_error(temp_cache_dir):
    """Test IndexError when accessing non-existent lines to cover line 322."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Line 1\nLine 2\n")
        log_path = f.name

    try:
        log = LogLogLog(log_path, cache=Cache(temp_cache_dir))

        # Test accessing beyond available lines
        with pytest.raises(IndexError, match="Line 2 out of range"):
            _ = log[2]

        # Test negative indexing beyond bounds
        with pytest.raises(IndexError, match="Line -1 out of range"):
            _ = log[-3]  # -3 + 2 lines = -1, which is out of range

        log.close()
    finally:
        os.unlink(log_path)
