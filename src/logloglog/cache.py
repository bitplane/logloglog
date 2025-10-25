"""Cache management for LogLogLog."""

import os
import hashlib
import shutil
import tempfile
from pathlib import Path
import platformdirs


# Cache constants
CACHE_DIR = Path(platformdirs.user_cache_dir("logloglog"))
TMP_DIR = Path(tempfile.gettempdir()) / "logloglog"


class Cache:
    """Manages cache directories for log files."""

    def __init__(self, cache_dir: Path = None):
        """Initialize cache manager.

        Args:
            cache_dir: Cache directory (defaults to CACHE_DIR)
        """
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_dir(self, path: Path) -> Path:
        """Get cache directory for a log file.

        Args:
            path: Path to the log file

        Returns:
            Cache directory path

        Raises:
            OSError: If file cannot be accessed or cache directory cannot be created
        """
        # Get file stats for unique identification
        stat = os.stat(path)
        # Create hash from device and inode only (removed ctime for stability)
        hash_input = f"{stat.st_dev}_{stat.st_ino}"
        hash_digest = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        # Create cache directory name
        name = path.name
        cache_name = f"{name}[{hash_digest}]"
        cache_path = self.cache_dir / cache_name

        # Create directory if it doesn't exist
        cache_path.mkdir(parents=True, exist_ok=True)

        # Create symlink to original file for reference
        symlink_path = cache_path / "file"
        if not symlink_path.exists():
            symlink_path.symlink_to(path.resolve())

        return cache_path

    def cleanup(self):
        """Clean up cache directories for files that no longer exist."""
        if not self.cache_dir.exists():
            return

        for cache_subdir in self.cache_dir.iterdir():
            if not cache_subdir.is_dir():
                continue

            # Check if the symlink exists and points to a valid file
            symlink_path = cache_subdir / "file"
            if symlink_path.exists():
                try:
                    # Try to resolve the symlink
                    target = symlink_path.resolve()
                    if not target.exists():
                        # Original file is gone, remove cache directory
                        shutil.rmtree(cache_subdir)
                except (OSError, FileNotFoundError):
                    # Symlink is broken, remove cache directory
                    shutil.rmtree(cache_subdir)
            else:
                # No symlink found, directory is orphaned
                shutil.rmtree(cache_subdir)
            # TODO: Add inode-based cleanup for more robust file tracking
