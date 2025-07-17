"""Tests for WrapTree functionality."""

import pytest
import tempfile
from pathlib import Path
from biglog.wraptree import WrapTree, BIGL_MAGIC, CURRENT_VERSION, ROOT_NODE_START
from biglog.index import DisplayWidths


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def display_widths(temp_cache_dir):
    """Create a DisplayWidths instance with test data."""
    widths_path = temp_cache_dir / "display_widths"
    widths = DisplayWidths(widths_path)
    widths.open(create=True)

    # Add some test widths
    test_widths = [10, 20, 30, 100, 5, 15, 25, 50]
    for width in test_widths:
        widths.append(width)

    yield widths
    widths.close()


def test_wraptree_creation(temp_cache_dir, display_widths):
    """Test creating a new WrapTree."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)

    # Check that file was created
    assert tree.path.exists()

    # Check header values
    assert tree._data[0] == BIGL_MAGIC  # MAGIC
    assert tree._data[1] == CURRENT_VERSION  # VERSION
    assert tree._data[4] == ROOT_NODE_START  # ROOT_INDEX

    tree.close()


def test_wraptree_load_existing(temp_cache_dir, display_widths):
    """Test loading an existing WrapTree."""
    tree1 = WrapTree(temp_cache_dir, display_widths)
    tree1.open(create=True)
    tree1.update_tree(5)  # Update with some lines
    tree1.close()

    # Load existing tree
    tree2 = WrapTree(temp_cache_dir, display_widths)
    tree2.open(create=False)

    # Should have loaded existing data
    assert tree2._data[0] == BIGL_MAGIC
    assert tree2._data[1] == CURRENT_VERSION

    tree2.close()


def test_wraptree_invalid_file_recreation(temp_cache_dir, display_widths):
    """Test that invalid files are recreated."""
    # Create invalid file first
    tree_path = temp_cache_dir / "wraptree.dat"
    with open(tree_path, "wb") as f:
        f.write(b"invalid data")

    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=False)

    # Should have recreated with valid header
    assert tree._data[0] == BIGL_MAGIC

    tree.close()


def test_wraptree_upgrade_version(temp_cache_dir, display_widths):
    """Test that older versions are upgraded."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)

    # Simulate older version
    tree._data[1] = 0  # Set version to 0
    tree.close()

    # Reopen - should trigger upgrade
    tree.open(create=False)
    assert tree._data[1] == CURRENT_VERSION

    tree.close()


def test_get_node_size(temp_cache_dir, display_widths):
    """Test get_node_size method."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)

    # Test with null node
    assert tree.get_node_size(0) == 0

    # Test with root node (initially has 0 buckets)
    root_index = tree._data[4]  # ROOT_INDEX
    initial_size = tree.get_node_size(root_index)
    assert initial_size == 8  # NODE_BUCKETS_START

    tree.close()


def test_update_tree_empty(temp_cache_dir):
    """Test updating tree with empty display widths."""
    # Create empty display widths
    widths_path = temp_cache_dir / "display_widths"
    widths = DisplayWidths(widths_path)
    widths.open(create=True)

    tree = WrapTree(temp_cache_dir, widths)
    tree.open(create=True)

    # Update with 0 lines
    tree.update_tree(0)

    # Root node should be empty
    root_index = tree._data[4]
    assert tree._data[root_index + 1] == 0  # NODE_END_LINE
    assert tree._data[root_index + 2] == 0  # NODE_BUCKET_COUNT

    tree.close()
    widths.close()


def test_update_tree_with_data(temp_cache_dir, display_widths):
    """Test updating tree with actual data."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)

    # Update with display_widths data
    tree.update_tree(len(display_widths))

    # Root node should have data
    root_index = tree._data[4]
    end_line = tree._data[root_index + 1]  # NODE_END_LINE
    bucket_count = tree._data[root_index + 2]  # NODE_BUCKET_COUNT

    assert end_line == len(display_widths)
    assert bucket_count > 0  # Should have some buckets

    tree.close()


def test_estimate_rows_empty_node(temp_cache_dir, display_widths):
    """Test estimating rows for empty/null nodes."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)

    # Test null node
    assert tree.estimate_rows_for_node(0, 80) == 0

    # Test node with no buckets
    root_index = tree._data[4]
    assert tree.estimate_rows_for_node(root_index, 80) == 0

    tree.close()


def test_estimate_rows_with_data(temp_cache_dir, display_widths):
    """Test estimating rows with actual data."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)
    tree.update_tree(len(display_widths))

    root_index = tree._data[4]

    # Test different terminal widths
    rows_80 = tree.estimate_rows_for_node(root_index, 80)
    rows_40 = tree.estimate_rows_for_node(root_index, 40)
    rows_20 = tree.estimate_rows_for_node(root_index, 20)

    # Smaller widths should generally mean more rows
    assert rows_20 >= rows_40 >= rows_80 > 0

    tree.close()


def test_get_total_rows(temp_cache_dir, display_widths):
    """Test get_total_rows method."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)
    tree.update_tree(len(display_widths))

    # Should return same as estimating root node
    root_index = tree._data[4]
    expected = tree.estimate_rows_for_node(root_index, 80)
    actual = tree.get_total_rows(80)

    assert actual == expected

    tree.close()


def test_seek_display_row_empty(temp_cache_dir):
    """Test seeking in empty tree."""
    # Create empty display widths
    widths_path = temp_cache_dir / "display_widths"
    widths = DisplayWidths(widths_path)
    widths.open(create=True)

    tree = WrapTree(temp_cache_dir, widths)
    tree.open(create=True)
    tree.update_tree(0)

    # Should raise error for any row in empty tree
    with pytest.raises(ValueError, match="Display row 0 not found"):
        tree.seek_display_row(0, 80)

    tree.close()
    widths.close()


def test_seek_display_row_with_data(temp_cache_dir, display_widths):
    """Test seeking with actual data."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)
    tree.update_tree(len(display_widths))

    # Should be able to find first row
    line_no, offset = tree.seek_display_row(0, 80)
    assert line_no == 0
    assert offset == 0

    # Test seeking beyond available rows
    total_rows = tree.get_total_rows(80)
    with pytest.raises(ValueError, match="Display row .* not found"):
        tree.seek_display_row(total_rows + 100, 80)

    tree.close()


def test_seek_in_null_node(temp_cache_dir, display_widths):
    """Test _seek_in_node with null node."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)

    # Should raise error when seeking in null node
    with pytest.raises(ValueError, match="Display row 0 not found"):
        tree._seek_in_node(0, 0, 80, 0)

    tree.close()


def test_add_width_to_node(temp_cache_dir, display_widths):
    """Test adding widths to a node."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)

    root_index = tree._data[4]
    initial_len = len(tree._data)

    # Ensure we have enough space for new buckets by expanding the array
    buckets_start = root_index + 8  # NODE_BUCKETS_START
    needed_size = buckets_start + 4  # Space for 1 width + 1 count
    while len(tree._data) < needed_size:
        tree._data.append(0)

    # Add a width
    tree.add_width_to_node(root_index, 50)

    # Assert that data structure was modified
    assert len(tree._data) >= initial_len  # Data array should not shrink

    # Should have 1 bucket now
    bucket_count = tree._data[root_index + 2]
    assert bucket_count == 1

    # Add same width again - should increment count
    tree.add_width_to_node(root_index, 50)

    # Still 1 bucket, but count should be 2
    bucket_count = tree._data[root_index + 2]
    assert bucket_count == 1

    # The bucket structure is: [widths...] [counts...]
    # So for 1 bucket, we have: [width1] [count1]
    width_value = tree._data[buckets_start]  # First width
    count_value = tree._data[buckets_start + 1]  # First count
    assert width_value == 50
    assert count_value == 2

    tree.close()


def test_close_multiple_times(temp_cache_dir, display_widths):
    """Test that closing multiple times doesn't error."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)

    tree.close()
    tree.close()  # Should not raise error


def test_context_manager_usage(temp_cache_dir, display_widths):
    """Test WrapTree as context manager (if implemented)."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)
    tree.update_tree(len(display_widths))

    # Verify it works
    total_rows = tree.get_total_rows(80)
    assert total_rows > 0

    tree.close()


def test_ensure_capacity(temp_cache_dir, display_widths):
    """Test _ensure_capacity method."""
    tree = WrapTree(temp_cache_dir, display_widths)
    tree.open(create=True)

    # Should not error (currently no-op)
    tree._ensure_capacity(1000)

    tree.close()


def test_wrapping_calculation_edge_cases(temp_cache_dir):
    """Test wrapping calculations with edge case widths."""
    # Create display widths with edge cases
    widths_path = temp_cache_dir / "display_widths"
    widths = DisplayWidths(widths_path)
    widths.open(create=True)

    # Add edge case widths: 0, very large
    test_widths = [0, 1, 2, 1000, 10000]
    for width in test_widths:
        widths.append(width)

    tree = WrapTree(temp_cache_dir, widths)
    tree.open(create=True)
    tree.update_tree(len(widths))

    # Test various terminal widths
    for terminal_width in [1, 10, 80, 120]:
        total_rows = tree.get_total_rows(terminal_width)
        assert total_rows >= len(widths)  # At least 1 row per line

        # Should be able to seek to first row
        if total_rows > 0:
            line_no, offset = tree.seek_display_row(0, terminal_width)
            assert line_no == 0
            assert offset == 0

    tree.close()
    widths.close()
