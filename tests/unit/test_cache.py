"""Tests for cache module."""

import os
import tempfile
import pytest
from pathlib import Path

from logloglog.cache import Cache, CACHE_DIR, TMP_DIR


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_log_file():
    """Create a temporary log file."""
    fd, path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    log_path = Path(path)
    log_path.write_text("test log content\n")
    yield log_path
    log_path.unlink(missing_ok=True)


def test_cache_constants():
    """Test that cache constants are defined."""
    assert CACHE_DIR.name == "logloglog"
    assert TMP_DIR.name == "logloglog"


def test_cache_init_default():
    """Test Cache initialization with default directory."""
    cache = Cache()
    assert cache.cache_dir == CACHE_DIR
    assert cache.cache_dir.exists()


def test_cache_init_custom_dir(temp_cache_dir):
    """Test Cache initialization with custom directory."""
    cache = Cache(temp_cache_dir)
    assert cache.cache_dir == temp_cache_dir
    assert cache.cache_dir.exists()


def test_get_dir_creates_cache_directory(temp_cache_dir, temp_log_file):
    """Test that get_dir creates cache directory with correct name."""
    cache = Cache(temp_cache_dir)
    cache_path = cache.get_dir(temp_log_file)

    # Should be inside cache directory
    assert cache_path.parent == temp_cache_dir

    # Should contain file name and hash
    assert temp_log_file.name in cache_path.name
    assert "[" in cache_path.name and "]" in cache_path.name

    # Directory should exist
    assert cache_path.exists()
    assert cache_path.is_dir()


def test_get_dir_creates_symlink(temp_cache_dir, temp_log_file):
    """Test that get_dir creates symlink to original file."""
    cache = Cache(temp_cache_dir)
    cache_path = cache.get_dir(temp_log_file)

    symlink_path = cache_path / "file"
    assert symlink_path.exists()
    assert symlink_path.is_symlink()
    assert symlink_path.resolve() == temp_log_file.resolve()


def test_get_dir_consistent_hash(temp_cache_dir, temp_log_file):
    """Test that get_dir returns same directory for same file."""
    cache = Cache(temp_cache_dir)
    cache_path1 = cache.get_dir(temp_log_file)
    cache_path2 = cache.get_dir(temp_log_file)

    assert cache_path1 == cache_path2


def test_get_dir_different_files_different_dirs(temp_cache_dir):
    """Test that different files get different cache directories."""
    cache = Cache(temp_cache_dir)

    # Create two different log files
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f1:
        f1.write(b"content1\n")
        log1 = Path(f1.name)

    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f2:
        f2.write(b"content2\n")
        log2 = Path(f2.name)

    try:
        cache_path1 = cache.get_dir(log1)
        cache_path2 = cache.get_dir(log2)

        assert cache_path1 != cache_path2
    finally:
        log1.unlink()
        log2.unlink()


def test_get_dir_nonexistent_file(temp_cache_dir):
    """Test that get_dir fails for nonexistent file."""
    cache = Cache(temp_cache_dir)
    nonexistent = Path("/nonexistent/file.log")

    with pytest.raises(OSError):
        cache.get_dir(nonexistent)


def test_cleanup_removes_dead_symlinks(temp_cache_dir, temp_log_file):
    """Test that cleanup removes cache directories for deleted files."""
    cache = Cache(temp_cache_dir)
    cache_path = cache.get_dir(temp_log_file)

    # Verify cache directory exists
    assert cache_path.exists()

    # Delete the original file
    temp_log_file.unlink()

    # Run cleanup
    cache.cleanup()

    # Cache directory should be removed
    assert not cache_path.exists()


def test_cleanup_preserves_valid_symlinks(temp_cache_dir, temp_log_file):
    """Test that cleanup preserves cache directories for existing files."""
    cache = Cache(temp_cache_dir)
    cache_path = cache.get_dir(temp_log_file)

    # Run cleanup
    cache.cleanup()

    # Cache directory should still exist
    assert cache_path.exists()


def test_cleanup_handles_missing_cache_dir(tmp_path):
    """Test that cleanup handles missing cache directory gracefully."""
    nonexistent_cache = tmp_path / "nonexistent" / "cache"
    cache = Cache(nonexistent_cache)

    # Remove the directory after creation to simulate missing cache
    import shutil

    shutil.rmtree(nonexistent_cache)

    # Should not raise an exception
    cache.cleanup()


def test_cleanup_handles_broken_symlinks(temp_cache_dir, temp_log_file):
    """Test that cleanup handles broken symlinks correctly."""
    cache = Cache(temp_cache_dir)
    cache_path = cache.get_dir(temp_log_file)

    # Break the symlink by creating a direct file instead
    symlink_path = cache_path / "file"
    symlink_path.unlink()
    symlink_path.write_text("broken")

    # Run cleanup
    cache.cleanup()

    # Cache directory should still exist since symlink check failed
    assert cache_path.exists()


def test_cache_reuse_after_close_reopen(temp_cache_dir):
    """Test that cache directory is reused when file is unchanged."""
    from logloglog import LogLogLog

    # Create test file
    test_file = temp_cache_dir / "test.log"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    # First open - should create cache
    cache = Cache(temp_cache_dir)
    log1 = LogLogLog(test_file, cache=cache)
    cache_info1 = log1.get_cache_info()
    cache_path1 = Path(cache_info1["cache_dir"])
    assert cache_path1.exists()
    log1.close()

    # Second open - should reuse same cache directory
    log2 = LogLogLog(test_file, cache=cache)
    cache_info2 = log2.get_cache_info()
    cache_path2 = Path(cache_info2["cache_dir"])
    log2.close()

    # Should be the same cache directory
    assert cache_path1 == cache_path2, f"Expected same cache directory, got {cache_path1} vs {cache_path2}"


def test_cleanup_broken_symlinks(temp_cache_dir):
    """Test cleanup handling of broken symlinks to cover lines 77-84."""
    cache = Cache(temp_cache_dir)

    # Create a fake cache directory with broken symlink
    fake_cache_dir = temp_cache_dir / "fake_cache"
    fake_cache_dir.mkdir()

    broken_symlink = fake_cache_dir / "file"
    non_existent_target = Path("/non/existent/file")
    broken_symlink.symlink_to(non_existent_target)

    # Verify symlink exists but target doesn't
    assert broken_symlink.exists() is False  # Broken symlink
    assert broken_symlink.is_symlink() is True

    # Cleanup should remove the directory with broken symlink
    cache.cleanup()

    # Directory should be removed
    assert not fake_cache_dir.exists()


def test_cleanup_non_directory_files(temp_cache_dir):
    """Test cleanup with non-directory files in cache to cover line 67."""
    cache = Cache(temp_cache_dir)

    # Create a regular file in cache directory (not a subdirectory)
    regular_file = temp_cache_dir / "not_a_directory.txt"
    regular_file.write_text("some content")

    # Cleanup should skip non-directory files
    cache.cleanup()

    # File should still exist (not removed)
    assert regular_file.exists()
