"""Tests for WidthView functionality."""

import tempfile
import os
import pytest
from pathlib import Path

from logloglog import LogLogLog
from logloglog.cache import Cache


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def simple_log(temp_cache_dir):
    """Create a simple log file with a few lines."""
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


@pytest.fixture
def log_with_custom_content(temp_cache_dir):
    """Factory fixture to create log files with custom content."""
    created_files = []

    def _create_log(content):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(content)
            log_path = f.name
        created_files.append(log_path)
        return LogLogLog(log_path, cache=Cache(temp_cache_dir))

    yield _create_log

    # Cleanup
    for path in created_files:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


@pytest.fixture
def log_with_incremental_lines(temp_cache_dir):
    """Create a log file with incremental line lengths for testing."""
    lines = []

    # Lines from 0 to 80 chars: "0", "01", "012", ...
    for i in range(81):
        line = "".join(str(j % 10) for j in range(i))
        lines.append(line)

    # Add a 1024 char line
    line_1024 = "".join(str(j % 10) for j in range(1024))
    lines.append(line_1024)

    content = "\n".join(lines) + "\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = LogLogLog(log_path, cache=Cache(temp_cache_dir))
        yield log
        log.close()
    finally:
        os.unlink(log_path)


def test_view_width_consistency(log_with_custom_content):
    """Test that view lengths are consistent across widths."""
    # Create content with known line lengths
    content = "short\n" + "x" * 50 + "\n" + "y" * 100 + "\n"
    log = log_with_custom_content(content)

    assert len(log) == 3

    # Test different widths
    view_20 = log.width(20)
    view_50 = log.width(50)
    view_200 = log.width(200)

    len_20 = len(view_20)
    len_50 = len(view_50)
    len_200 = len(view_200)

    # Basic consistency: larger widths should have fewer or equal rows
    assert len_200 <= len_50 <= len_20, f"Width consistency violated: w20={len_20}, w50={len_50}, w200={len_200}"

    # At width 200, should be exactly 3 rows (no wrapping)
    assert len_200 == 3, f"At large width, should be {len(log)} rows, got {len_200}"

    # All views should have at least as many rows as lines
    assert len_20 >= 3
    assert len_50 >= 3
    assert len_200 >= 3

    log.close()


def test_incremental_view_calculations(log_with_incremental_lines):
    """Test view calculations with incremental line lengths."""
    log = log_with_incremental_lines

    # Should have 82 lines: 0-80 chars + 1024 char line
    assert len(log) == 82

    # Test specific line lengths
    assert len(log[0]) == 0  # ""
    assert len(log[1]) == 1  # "0"
    assert len(log[10]) == 10  # "0123456789"
    assert len(log[80]) == 80  # 80 chars
    assert len(log[81]) == 1024  # 1024 chars

    # Test views at different widths
    test_widths = [10, 20, 40, 80, 160]

    for width in test_widths:
        view = log.width(width)
        view_rows = len(view)

        # Manual calculation
        expected_rows = 0
        for i in range(len(log)):
            line_width = len(log[i])
            rows_for_line = max(1, (line_width + width - 1) // width) if line_width > 0 else 1
            expected_rows += rows_for_line

        print(f"\nWidth {width}:")
        print(f"  View reports: {view_rows} rows")
        print(f"  Expected: {expected_rows} rows")
        print(f"  Match: {view_rows == expected_rows}")

        # The key test: view calculation should match manual calculation
        assert view_rows == expected_rows, f"Width {width}: expected {expected_rows} rows, got {view_rows}"


def test_view_negative_indexing(log_with_incremental_lines):
    """Test that negative indexing works in views."""
    log = log_with_incremental_lines
    view = log.width(20)

    view_len = len(view)
    assert view_len > 0, "View should have some rows"

    # Test negative indexing

    # Should be same as positive indexing
    assert view[-1] == view[view_len - 1]
    assert view[-2] == view[view_len - 2]

    # Test edge cases
    assert view[-view_len] == view[0]  # First element via negative index

    # Test out of bounds negative indexing
    with pytest.raises(IndexError):
        _ = view[-(view_len + 1)]


def test_multi_line_wrapping(log_with_custom_content):
    """Test that long lines wrap multiple times correctly."""
    # Create a 100-character line that should wrap multiple times
    long_line = "x" * 100
    content = f"short\n{long_line}\nend\n"
    log = log_with_custom_content(content)

    # Test at width 20 - the 100-char line should become 5 rows
    view = log.width(20)

    print("\nTesting 100-char line at width 20:")
    print(f"Total view rows: {len(view)}")

    # Should have:
    # Row 0: "short" (5 chars -> 1 row)
    # Row 1-5: 100-char line split into 5 rows of 20 chars each
    # Row 6: "end" (3 chars -> 1 row)
    # Total: 7 rows
    expected_rows = 7
    assert len(view) == expected_rows, f"Expected {expected_rows} rows, got {len(view)}"

    # Check each row
    assert view[0] == "short"
    assert view[1] == "x" * 20  # First 20 chars
    assert view[2] == "x" * 20  # Next 20 chars
    assert view[3] == "x" * 20  # Next 20 chars
    assert view[4] == "x" * 20  # Next 20 chars
    assert view[5] == "x" * 20  # Last 20 chars
    assert view[6] == "end"

    print("✓ Multi-line wrapping works correctly")

    log.close()


def test_view_with_real_file(log_with_custom_content):
    """Test view creation works with actual content."""
    content = "Short line\n" + "x" * 100 + "\nAnother line\n"
    log = log_with_custom_content(content)

    # Should have 3 lines
    assert len(log) == 3

    # Create view at width 80
    view = log.width(80)

    # View should have some rows (not 0)
    view_length = len(view)
    assert view_length > 0, f"View should have rows, got {view_length}"

    # Should be able to access first row
    first_row = view[0]
    assert first_row == "Short line"

    log.close()


def test_view_iteration(simple_log):
    """Test WidthView __iter__ method to cover lines 79-80."""
    view = simple_log.width(80)

    # Test iteration using __iter__
    rows = list(view)
    assert rows == ["Line 1", "Line 2", "Line 3"]

    # Test iteration in a loop
    collected = []
    for row in view:  # This also uses __iter__
        collected.append(row)
    assert collected == ["Line 1", "Line 2", "Line 3"]


def test_view_zero_width(simple_log):
    """Test that zero width doesn't cause division by zero."""
    view = simple_log.width(width=0)
    assert len(view) == 0  # Should have zero logical rows


def test_line_at_negative_indexing(simple_log):
    """Test line_at with negative indexing."""
    view = simple_log.width(80)

    # simple_log has 3 lines, so 3 rows at width 80
    assert len(view) == 3

    # Test negative indexing
    line, offset = view.line_at(-1)  # Last row
    assert line == 2  # Third line (0-indexed)
    assert offset == 0  # No wrapping at width 80

    line, offset = view.line_at(-2)  # Second to last
    assert line == 1
    assert offset == 0

    line, offset = view.line_at(-3)  # First row
    assert line == 0
    assert offset == 0


def test_line_at_out_of_bounds(simple_log):
    """Test line_at with out of bounds access."""
    view = simple_log.width(80)

    # Test positive out of bounds
    with pytest.raises(IndexError, match="Display row 999 out of range"):
        view.line_at(999)

    # Test negative out of bounds
    with pytest.raises(IndexError, match="Display row -7 out of range"):
        view.line_at(-10)  # -10 + 3 = -7, which is out of bounds for 3 rows


def test_row_for_method(log_with_custom_content):
    """Test row_for method to find display row for logical line."""
    # Create content with known wrapping behavior
    content = "Short\n" + "x" * 100 + "\nEnd"
    log = log_with_custom_content(content)

    view = log.width(20)  # 100 chars will wrap to 5 rows at width 20

    # Line 0: "Short" - starts at row 0
    assert view.row_for(0) == 0

    # Line 1: 100 x's - starts at row 1 (after "Short")
    assert view.row_for(1) == 1

    # Line 2: "End" - starts at row 6 (after 1 + 5 rows)
    assert view.row_for(2) == 6

    log.close()
