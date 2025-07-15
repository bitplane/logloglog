"""Tests for BigLog functionality."""

import tempfile
import os
from pathlib import Path
from biglog import BigLog


class TestBigLog:
    """Test BigLog core functionality."""

    def test_empty_log(self):
        """Test with empty log file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            log_path = f.name

        try:
            with tempfile.TemporaryDirectory() as cache_dir:
                log = BigLog(log_path, cache_dir=Path(cache_dir))
                assert len(log) == 0

                # Test empty view
                view = log.at(width=80)
                assert len(view) == 0

        finally:
            os.unlink(log_path)

    def test_simple_lines(self):
        """Test with simple text lines."""
        content = "Hello world\nThis is line 2\nShort\nA very long line that should wrap at 80 characters and continue beyond that point"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(content)
            log_path = f.name

        try:
            with tempfile.TemporaryDirectory() as cache_dir:
                log = BigLog(log_path, cache_dir=Path(cache_dir))

                # Test basic access
                assert len(log) == 4
                assert log[0] == "Hello world"
                assert log[1] == "This is line 2"
                assert log[2] == "Short"
                assert log[3].startswith("A very long line")

                # Test negative indexing
                assert log[-1] == log[3]
                assert log[-2] == log[2]

        finally:
            os.unlink(log_path)

    def test_iteration(self):
        """Test line iteration."""
        content = "Line 1\nLine 2\nLine 3\n"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(content)
            log_path = f.name

        try:
            with tempfile.TemporaryDirectory() as cache_dir:
                log = BigLog(log_path, cache_dir=Path(cache_dir))

                lines = list(log)
                assert lines == ["Line 1", "Line 2", "Line 3"]

        finally:
            os.unlink(log_path)

    def test_append(self):
        """Test appending lines."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("Initial line\n")
            log_path = f.name

        try:
            with tempfile.TemporaryDirectory() as cache_dir:
                log = BigLog(log_path, cache_dir=Path(cache_dir))

                assert len(log) == 1
                assert log[0] == "Initial line"

                # Append new lines
                log.append("Second line")
                log.append("Third line")

                assert len(log) == 3
                assert log[1] == "Second line"
                assert log[2] == "Third line"

        finally:
            os.unlink(log_path)

    def test_update(self):
        """Test updating with externally added lines."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("Line 1\n")
            log_path = f.name

        try:
            with tempfile.TemporaryDirectory() as cache_dir:
                log = BigLog(log_path, cache_dir=Path(cache_dir))
                assert len(log) == 1

                # Externally append to file
                with open(log_path, "a") as f:
                    f.write("Line 2\nLine 3\n")

                # Update should pick up new lines
                log.update()
                assert len(log) == 3
                assert log[1] == "Line 2"
                assert log[2] == "Line 3"

        finally:
            os.unlink(log_path)

    def test_wrapped_view(self):
        """Test LogView with wrapping."""
        # Create lines of known width
        content = "x" * 40 + "\n" + "y" * 120 + "\n" + "z" * 200

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(content)
            log_path = f.name

        try:
            with tempfile.TemporaryDirectory() as cache_dir:
                log = BigLog(log_path, cache_dir=Path(cache_dir))

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

        finally:
            os.unlink(log_path)

    def test_custom_width_function(self):
        """Test with custom width calculation."""

        def custom_width(line: str) -> int:
            # Simple: each char is 1 unit
            return len(line)

        content = "abc\ndefgh\n"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(content)
            log_path = f.name

        try:
            with tempfile.TemporaryDirectory() as cache_dir:
                log = BigLog(log_path, get_width=custom_width, cache_dir=Path(cache_dir))

                view = log.at(width=3)

                # Line 0: "abc" = 3 chars -> 1 row
                # Line 1: "defgh" = 5 chars -> 2 rows (ceil(5/3) = 2)
                assert len(view) == 3
                assert view[0] == "abc"
                assert view[1] == "def"
                assert view[2] == "gh"

        finally:
            os.unlink(log_path)

    def test_index_persistence(self):
        """Test that index persists across reopening."""
        content = "Line 1\nLine 2\nLine 3\n"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(content)
            log_path = f.name

        try:
            with tempfile.TemporaryDirectory() as cache_dir:
                # First open
                log1 = BigLog(log_path, cache_dir=Path(cache_dir))
                assert len(log1) == 3
                log1.close()

                # Second open - should reuse index
                log2 = BigLog(log_path, cache_dir=Path(cache_dir))
                assert len(log2) == 3
                assert log2[0] == "Line 1"

        finally:
            os.unlink(log_path)

    def test_context_manager(self):
        """Test BigLog as context manager."""
        content = "Test line\n"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(content)
            log_path = f.name

        try:
            with tempfile.TemporaryDirectory() as cache_dir:
                with BigLog(log_path, cache_dir=Path(cache_dir)) as log:
                    assert len(log) == 1
                    assert log[0] == "Test line"

        finally:
            os.unlink(log_path)
