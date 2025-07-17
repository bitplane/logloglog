"""Tests for index data structures."""

import tempfile
import pytest
from pathlib import Path

from biglog.index import DisplayWidths


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_display_widths_create_and_append(temp_dir):
    """Test creating and appending widths."""
    dw = DisplayWidths(temp_dir)
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


def test_display_widths_get_range(temp_dir):
    """Test getting ranges of widths."""
    dw = DisplayWidths(temp_dir)
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


def test_display_widths_persistence(temp_dir):
    """Test that widths persist across open/close."""
    # First session
    dw1 = DisplayWidths(temp_dir)
    dw1.open(create=True)
    dw1.append(100)
    dw1.append(200)
    dw1.close()

    # Second session
    dw2 = DisplayWidths(temp_dir)
    dw2.open(create=False)

    assert len(dw2) == 2
    assert dw2.get(0) == 100
    assert dw2.get(1) == 200

    dw2.close()


def test_display_widths_uint16_cap(temp_dir):
    """Test that widths are capped at uint16 max value."""
    dw = DisplayWidths(temp_dir)
    dw.open(create=True)

    # Test capping large values
    dw.append(70000)  # Should be capped to 65535
    assert dw.get(0) == 65535

    dw.close()
