"""Tests for LogView functionality."""

import tempfile
import os
import pytest
from pathlib import Path
from biglog import BigLog


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def log_with_incremental_lines(temp_cache_dir):
    """Create a log file with incremental line lengths for testing."""
    lines = []

    # Lines from 0 to 80 chars: "0", "01", "012", ... "012345678901234567890123456789012345678901234567890123456789012345678901234567890"
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
        log = BigLog(log_path, cache_dir=temp_cache_dir)
        yield log
        log.close()
    finally:
        os.unlink(log_path)


def test_view_width_consistency(temp_cache_dir):
    """Test that view lengths are consistent across widths."""
    # Create content with known line lengths
    content = "short\n" + "x" * 50 + "\n" + "y" * 100 + "\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)
        assert len(log) == 3

        # Test different widths
        view_20 = log.at(20)
        view_50 = log.at(50)
        view_200 = log.at(200)

        len_20 = len(view_20)
        len_50 = len(view_50)
        len_200 = len(view_200)

        # Basic consistency: larger widths should have fewer or equal rows
        assert len_200 <= len_50 <= len_20, f"Width consistency violated: w20={len_20}, w50={len_50}, w200={len_200}"

        # At width 200, should be exactly 3 rows (no wrapping)
        assert len_200 == 3, f"At large width, should be {log.__len__()} rows, got {len_200}"

        # All views should have at least as many rows as lines
        assert len_20 >= 3
        assert len_50 >= 3
        assert len_200 >= 3

        log.close()

    finally:
        os.unlink(log_path)


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
        view = log.at(width)
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


def test_view_math_debugging(log_with_incremental_lines):
    """Debug view calculations by examining specific lines."""
    log = log_with_incremental_lines

    # Test width 20 specifically
    width = 20
    view = log.at(width)

    print(f"\nDebugging width {width}:")
    print(f"Total lines in log: {len(log)}")
    print(f"View reports: {len(view)} rows")

    # Check first few lines manually
    manual_total = 0
    for i in range(min(10, len(log))):
        line_len = len(log[i])
        expected_rows = max(1, (line_len + width - 1) // width) if line_len > 0 else 1
        manual_total += expected_rows
        print(f"  Line {i}: len={line_len} -> {expected_rows} rows (running total: {manual_total})")

    # Check the large line
    line_81_len = len(log[81])
    line_81_rows = (line_81_len + width - 1) // width
    print(f"  Line 81: len={line_81_len} -> {line_81_rows} rows")

    # Full manual calculation
    full_manual = sum(max(1, (len(log[i]) + width - 1) // width) if len(log[i]) > 0 else 1 for i in range(len(log)))
    print(f"  Full manual total: {full_manual}")

    # This should help us see where the discrepancy is
    assert len(view) == full_manual


def test_view_negative_indexing(log_with_incremental_lines):
    """Test that negative indexing works in views."""
    log = log_with_incremental_lines
    view = log.at(20)

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


def test_multi_line_wrapping(temp_cache_dir):
    """Test that long lines wrap multiple times correctly."""
    # Create a 100-character line that should wrap multiple times
    long_line = "x" * 100
    content = f"short\n{long_line}\nend\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)

        # Test at width 20 - the 100-char line should become 5 rows
        view = log.at(20)

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

    finally:
        os.unlink(log_path)


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


def test_view_with_explicit_end(temp_cache_dir):
    """Test LogView with explicit end parameter to cover line 73."""
    content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)

        # Create view with explicit start and end
        view = log.at(80, start=1, end=4)  # This should trigger line 73

        # Should be exactly 3 rows (end - start = 4 - 1 = 3)
        assert len(view) == 3

        # Test that we can access these rows
        assert view[0] == "Line 2"  # Row 1 in original log
        assert view[1] == "Line 3"  # Row 2 in original log
        assert view[2] == "Line 4"  # Row 3 in original log

        log.close()
    finally:
        os.unlink(log_path)


def test_view_iteration(temp_cache_dir):
    """Test LogView __iter__ method to cover lines 79-80."""
    content = "A\nB\nC\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        log_path = f.name

    try:
        log = BigLog(log_path, cache_dir=temp_cache_dir)
        view = log.at(80)

        # Test iteration using __iter__
        rows = list(view)  # This calls __iter__ and yields each row
        assert rows == ["A", "B", "C"]

        # Test iteration in a loop
        collected = []
        for row in view:  # This also uses __iter__
            collected.append(row)
        assert collected == ["A", "B", "C"]

        log.close()
    finally:
        os.unlink(log_path)
