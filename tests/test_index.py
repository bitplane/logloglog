"""Tests for index data structures."""

import tempfile
from pathlib import Path

from biglog.index import DisplayWidths, IndexMetadata


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
            expected = [20, 30, 40]
            assert list(result) == expected

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


# WrapTreeNode tests removed - using array-based storage now


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
