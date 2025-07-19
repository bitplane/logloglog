"""Tests for LineIndex."""

import pytest
import tempfile
from pathlib import Path
from logloglog.line_index import LineIndex, MAX_WIDTH, SUMMARY_INTERVAL


@pytest.fixture
def temp_index_dir():
    """Create a temporary directory for index files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_line_index_creation(temp_index_dir):
    """Test creating a new LineIndex."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Should start empty
    assert len(index) == 0

    index.close()


def test_append_lines(temp_index_dir):
    """Test appending lines to index."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Append some lines
    index.append_line(0, 10)
    index.append_line(100, 20)
    index.append_line(200, 30)

    assert len(index) == 3
    assert index.get_line_position(0) == 0
    assert index.get_line_position(1) == 100
    assert index.get_line_position(2) == 200
    assert index.get_line_width(0) == 10
    assert index.get_line_width(1) == 20
    assert index.get_line_width(2) == 30

    index.close()


def test_total_display_rows(temp_index_dir):
    """Test calculating total display rows."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Add lines with different widths
    index.append_line(0, 10)  # 1 row at width 80
    index.append_line(100, 100)  # 2 rows at width 80
    index.append_line(200, 240)  # 3 rows at width 80

    # Test different terminal widths
    assert index.get_total_display_rows(80) == 6  # 1 + 2 + 3
    assert index.get_total_display_rows(40) == 10  # 1 + 3 + 6
    assert index.get_total_display_rows(20) == 18  # 1 + 5 + 12

    index.close()


def test_display_row_for_line(temp_index_dir):
    """Test getting display row for logical line."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Add lines
    index.append_line(0, 10)  # 1 row at width 80
    index.append_line(100, 100)  # 2 rows at width 80
    index.append_line(200, 240)  # 3 rows at width 80

    # At width 80
    assert index.get_display_row_for_line(0, 80) == 0
    assert index.get_display_row_for_line(1, 80) == 1  # After 1 row
    assert index.get_display_row_for_line(2, 80) == 3  # After 1 + 2 rows

    # At width 40
    assert index.get_display_row_for_line(0, 40) == 0
    assert index.get_display_row_for_line(1, 40) == 1  # After 1 row
    assert index.get_display_row_for_line(2, 40) == 4  # After 1 + 3 rows

    index.close()


def test_line_for_display_row(temp_index_dir):
    """Test finding logical line for display row."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Add lines
    index.append_line(0, 10)  # 1 row at width 80
    index.append_line(100, 100)  # 2 rows at width 80
    index.append_line(200, 240)  # 3 rows at width 80

    # At width 80
    assert index.get_line_for_display_row(0, 80) == (0, 0)
    assert index.get_line_for_display_row(1, 80) == (1, 0)
    assert index.get_line_for_display_row(2, 80) == (1, 1)  # Second row of line 1
    assert index.get_line_for_display_row(3, 80) == (2, 0)
    assert index.get_line_for_display_row(4, 80) == (2, 1)
    assert index.get_line_for_display_row(5, 80) == (2, 2)

    # Test out of range
    with pytest.raises(IndexError):
        index.get_line_for_display_row(6, 80)

    index.close()


def test_summary_creation(temp_index_dir):
    """Test that summaries are created every SUMMARY_INTERVAL lines."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Add exactly SUMMARY_INTERVAL lines
    for i in range(SUMMARY_INTERVAL):
        index.append_line(i * 100, i % 100 + 1)  # Varying widths

    # Summaries should have been created
    assert len(index._summaries) == MAX_WIDTH

    # Add one more line to start next summary block
    index.append_line(SUMMARY_INTERVAL * 100, 50)

    # Still just one summary
    assert len(index._summaries) == MAX_WIDTH

    index.close()


def test_reopen_existing_index(temp_index_dir):
    """Test reopening an existing index."""
    # Create and populate index
    index = LineIndex(temp_index_dir)
    index.open(create=True)
    index.append_line(0, 10)
    index.append_line(100, 20)
    index.append_line(200, 30)
    index.close()

    # Reopen
    index2 = LineIndex(temp_index_dir)
    index2.open(create=False)

    # Should have same data
    assert len(index2) == 3
    assert index2.get_line_position(0) == 0
    assert index2.get_line_position(1) == 100
    assert index2.get_line_position(2) == 200
    assert index2.get_line_width(0) == 10
    assert index2.get_line_width(1) == 20
    assert index2.get_line_width(2) == 30

    index2.close()


def test_edge_cases(temp_index_dir):
    """Test edge cases."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Very wide line (capped at uint16 max)
    index.append_line(0, 100000)
    assert index.get_line_width(0) == 65535

    # Zero width terminal
    assert index.get_total_display_rows(0) == 0  # No display possible

    # Width beyond MAX_WIDTH (line width 65535, terminal width clamped to MAX_WIDTH)
    expected_rows = (65535 + MAX_WIDTH - 1) // MAX_WIDTH  # Ceiling division
    assert index.get_total_display_rows(MAX_WIDTH + 100) == expected_rows

    index.close()


def test_line_index_error_paths(temp_index_dir):
    """Test error handling in LineIndex."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Add some test data
    index.append_line(0, 10)
    index.append_line(100, 20)

    # Test negative indices
    with pytest.raises(IndexError, match="Line -1 out of range"):
        index.get_line_position(-1)

    with pytest.raises(IndexError, match="Line -1 out of range"):
        index.get_line_width(-1)

    with pytest.raises(IndexError, match="Line -1 out of range"):
        index.get_display_row_for_line(-1, 80)

    # Test beyond bounds
    with pytest.raises(IndexError, match="Line 2 out of range"):
        index.get_line_position(2)

    with pytest.raises(IndexError, match="Line 2 out of range"):
        index.get_line_width(2)

    with pytest.raises(IndexError, match="Line 2 out of range"):
        index.get_display_row_for_line(2, 80)

    # Test display row lookup with zero width
    with pytest.raises(IndexError, match="Display row 0 out of range"):
        index.get_line_for_display_row(0, 0)

    # Test display row beyond available rows
    with pytest.raises(IndexError, match="Display row 999 out of range"):
        index.get_line_for_display_row(999, 80)

    index.close()


def test_line_index_summary_edge_cases(temp_index_dir):
    """Test edge cases with summary calculations."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Add lines to create partial summary blocks
    for i in range(SUMMARY_INTERVAL + 500):  # 1500 lines, creates 1 complete + 1 partial summary
        index.append_line(i * 100, i % 50 + 1)  # Varying widths 1-50

    # Test calculations that cross summary boundaries
    total_rows = index.get_total_display_rows(25)
    assert total_rows > 0

    # Test display row calculation in partial summary block
    display_row = index.get_display_row_for_line(SUMMARY_INTERVAL + 100, 25)
    assert display_row > 0

    # Test line lookup in partial summary block
    line_no, offset = index.get_line_for_display_row(display_row, 25)
    assert line_no == SUMMARY_INTERVAL + 100
    assert offset == 0

    # Test with MAX_WIDTH to hit boundary conditions
    total_rows_max = index.get_total_display_rows(MAX_WIDTH)
    assert total_rows_max == len(index)  # Each line should be 1 row at max width

    index.close()


def test_line_index_empty_lines_in_summary(temp_index_dir):
    """Test empty lines handling in summary creation (lines 104-105)."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Add a mix of empty and non-empty lines to create a summary
    for i in range(SUMMARY_INTERVAL):
        if i % 3 == 0:
            # Empty line - should always take 1 row
            index.append_line(i * 100, 0)
        else:
            # Non-empty line with width 50 (wraps at narrower widths)
            index.append_line(i * 100, 50)

    # Verify summary was created
    assert len(index._summaries) == MAX_WIDTH

    # Check that empty lines are handled correctly at different widths
    # Empty lines should always contribute 1 row regardless of terminal width
    total_rows_w10 = index.get_total_display_rows(10)
    total_rows_w20 = index.get_total_display_rows(20)
    total_rows_w40 = index.get_total_display_rows(40)

    # All should be > 0 and decrease as width increases (except empty lines stay 1)
    assert total_rows_w10 > total_rows_w20 > total_rows_w40 > 0

    index.close()


def test_line_index_width_clamping(temp_index_dir):
    """Test width clamping to MAX_WIDTH (lines 177, 210)."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Add some lines
    index.append_line(0, 100)
    index.append_line(100, 200)
    index.append_line(200, 300)

    # Test get_display_row_for_line with width > MAX_WIDTH
    # Should clamp to MAX_WIDTH
    display_row_max = index.get_display_row_for_line(1, MAX_WIDTH)
    display_row_beyond = index.get_display_row_for_line(1, MAX_WIDTH + 100)
    assert display_row_max == display_row_beyond

    # Test get_line_for_display_row with width > MAX_WIDTH
    # Should clamp to MAX_WIDTH
    line_no_max, _ = index.get_line_for_display_row(0, MAX_WIDTH)
    line_no_beyond, _ = index.get_line_for_display_row(0, MAX_WIDTH + 100)
    assert line_no_max == line_no_beyond

    index.close()


def test_line_index_binary_search_edge_case(temp_index_dir):
    """Test binary search edge case in get_line_for_display_row (lines 223-224)."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Create exactly SUMMARY_INTERVAL lines for one complete summary
    for i in range(SUMMARY_INTERVAL):
        index.append_line(i * 100, 10)  # All lines width 10

    # Add one more line to start incomplete block
    index.append_line(SUMMARY_INTERVAL * 100, 10)

    # Test finding a line in the first summary block
    # At width 10, each line takes 1 row
    line_no, offset = index.get_line_for_display_row(500, 10)  # Middle of first block
    assert line_no == 500
    assert offset == 0

    # Test finding a line in the incomplete block
    line_no, offset = index.get_line_for_display_row(SUMMARY_INTERVAL, 10)  # First line of incomplete block
    assert line_no == SUMMARY_INTERVAL
    assert offset == 0

    index.close()


def test_line_index_zero_width_display_row(temp_index_dir):
    """Test get_display_row_for_line with zero width (line 175)."""
    index = LineIndex(temp_index_dir)
    index.open(create=True)

    # Add some lines
    index.append_line(0, 10)
    index.append_line(100, 20)
    index.append_line(200, 30)

    # Test with zero width - should return 0
    row = index.get_display_row_for_line(0, 0)
    assert row == 0

    row = index.get_display_row_for_line(1, 0)
    assert row == 0

    row = index.get_display_row_for_line(2, 0)
    assert row == 0

    # Test with negative width - should also return 0
    row = index.get_display_row_for_line(0, -5)
    assert row == 0

    index.close()
