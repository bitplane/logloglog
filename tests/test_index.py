"""Tests for index data structures."""

import tempfile
from pathlib import Path
import numpy as np

from biglog.index import DisplayWidths, WrapTreeNode, IndexMetadata


class TestDisplayWidths:
    """Test DisplayWidths functionality."""

    def test_create_and_append(self):
        """Test creating and appending widths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dw = DisplayWidths(Path(tmpdir))
            dw.open(create=True)

            # Append some widths
            dw.append(40)
            dw.append(120)
            dw.append(80)

            # Check length
            assert len(dw) == 3

            # Check values
            assert dw.get(0) == 40
            assert dw.get(1) == 120
            assert dw.get(2) == 80

            dw.close()

    def test_get_range(self):
        """Test getting ranges of widths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dw = DisplayWidths(Path(tmpdir))
            dw.open(create=True)

            # Add test data
            widths = [10, 20, 30, 40, 50]
            for w in widths:
                dw.append(w)

            # Test range access
            result = dw.get_range(1, 4)
            expected = np.array([20, 30, 40], dtype=np.uint16)
            np.testing.assert_array_equal(result, expected)

            dw.close()

    def test_persistence(self):
        """Test that widths persist across open/close."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First session
            dw1 = DisplayWidths(Path(tmpdir))
            dw1.open(create=True)
            dw1.append(100)
            dw1.append(200)
            dw1.close()

            # Second session
            dw2 = DisplayWidths(Path(tmpdir))
            dw2.open(create=False)

            assert len(dw2) == 2
            assert dw2.get(0) == 100
            assert dw2.get(1) == 200

            dw2.close()


class TestWrapTreeNode:
    """Test WrapTreeNode functionality."""

    def test_bucket_assignment(self):
        """Test histogram bucket assignment."""
        node = WrapTreeNode()

        # Test various widths
        assert node.find_bucket(10) == 0  # First bucket
        assert node.find_bucket(50) == 1  # Second bucket
        assert node.find_bucket(90) == 3  # Fourth bucket
        assert node.find_bucket(1000) == 13  # Near end
        assert node.find_bucket(100000) == 15  # Last bucket

    def test_histogram_updates(self):
        """Test adding widths to histogram."""
        node = WrapTreeNode()

        # Add some widths
        node.add_width(40)
        node.add_width(45)
        node.add_width(80)
        node.add_width(80)

        # Check histogram - based on actual bucket boundaries
        # 40, 45 -> bucket 1 (40-60 range)
        # 80, 80 -> bucket 3 (80-100 range)
        assert node.histogram[1] == 2  # Two widths in 40-60 range
        assert node.histogram[3] == 2  # Two widths in 80-100 range

    def test_row_estimation(self):
        """Test display row estimation."""
        node = WrapTreeNode()

        # Add known widths
        node.add_width(40)  # Should be 1 row at width 80
        node.add_width(120)  # Should be 2 rows at width 80
        node.add_width(200)  # Should be 3 rows at width 80

        # Estimate at width 80
        estimated = node.estimate_rows(80)

        # Should be approximately 6 rows total
        # (exact depends on bucket centers)
        assert 5 <= estimated <= 7

    def test_serialization(self):
        """Test node serialization/deserialization."""
        node = WrapTreeNode()
        node.start_line = 100
        node.end_line = 200
        node.is_leaf = False
        node.fanout = 3
        node.child_offsets = [1000, 2000, 3000]

        # Add some histogram data
        node.add_width(50)
        node.add_width(100)

        # Serialize and deserialize
        data = node.to_bytes()
        assert len(data) == WrapTreeNode.NODE_SIZE

        node2 = WrapTreeNode.from_bytes(data)

        # Check fields
        assert node2.start_line == 100
        assert node2.end_line == 200
        assert not node2.is_leaf
        assert node2.fanout == 3
        assert node2.child_offsets == [1000, 2000, 3000]

        # Check histogram
        np.testing.assert_array_equal(node2.histogram, node.histogram)


class TestIndexMetadata:
    """Test IndexMetadata functionality."""

    def test_save_and_load(self):
        """Test saving and loading metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta = IndexMetadata(Path(tmpdir))

            # Save some metadata
            data = {"version": 1, "line_count": 100, "last_position": 5000, "ctime": 1234567890.0}
            meta.save(data)

            # Load it back
            loaded = meta.load()
            assert loaded == data

    def test_validation(self):
        """Test index validation against file stats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta = IndexMetadata(Path(tmpdir))

            # Create mock file stats
            class MockStat:
                def __init__(self, ctime, size):
                    self.st_ctime = ctime
                    self.st_size = size

            # Save metadata
            meta.save({"ctime": 1000.0, "size": 500})

            # Test validation
            assert meta.validate(MockStat(1000.0, 500))  # Same - valid
            assert meta.validate(MockStat(1000.0, 600))  # Grew - valid
            assert not meta.validate(MockStat(2000.0, 500))  # Different ctime - invalid
            assert not meta.validate(MockStat(1000.0, 300))  # Shrank - invalid
