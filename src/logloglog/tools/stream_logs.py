#!/usr/bin/env python3
"""
Stream system logs for logloglog.

This tool discovers and streams system logs from /var/log, handling both
historical logs (sorted by creation time) and live log following.
"""

import argparse
import asyncio
import gzip
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator, List, Tuple


def discover_historical_logs() -> Iterator[Tuple[float, Path]]:
    """
    Discover all log files in /var/log sorted by creation time.

    Yields:
        Tuple of (creation_time, filepath) sorted by creation time (oldest first)
    """
    log_dir = Path("/var/log")
    if not log_dir.exists():
        return

    files_with_ctime = []

    try:
        for filepath in log_dir.rglob("*"):
            if filepath.is_file():
                try:
                    # Get creation/change time (ctime)
                    ctime = filepath.stat().st_ctime
                    files_with_ctime.append((ctime, filepath))
                except (PermissionError, OSError):
                    # Skip files we can't access
                    continue
    except PermissionError:
        # If we can't read /var/log at all, return empty
        return

    # Sort by creation time (oldest first)
    files_with_ctime.sort(key=lambda x: x[0])

    for ctime, filepath in files_with_ctime:
        yield ctime, filepath


def discover_live_logs(last_modified_minutes: int = 60) -> List[Path]:
    """
    Discover .log files that were modified within the last N minutes.

    Args:
        last_modified_minutes: Only include files modified within this many minutes

    Returns:
        List of .log file paths
    """
    log_dir = Path("/var/log")
    if not log_dir.exists():
        return []

    cutoff_time = time.time() - (last_modified_minutes * 60)
    live_logs = []

    try:
        for filepath in log_dir.rglob("*.log"):
            if filepath.is_file():
                try:
                    # Check if modified recently
                    if filepath.stat().st_mtime > cutoff_time:
                        live_logs.append(filepath)
                except (PermissionError, OSError):
                    continue
    except PermissionError:
        pass

    # Limit to 10 files as in the original script
    return live_logs[-10:]


def is_text_file(filepath: Path) -> bool:
    """
    Check if a file is a text file using the file command.

    Args:
        filepath: Path to check

    Returns:
        True if the file appears to be text
    """
    try:
        result = subprocess.run(["file", "-b", str(filepath)], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            filetype = result.stdout.lower()
            return "ascii text" in filetype or "utf-8" in filetype
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass

    return False


def stream_file_content(filepath: Path) -> None:
    """
    Stream the content of a file to stdout, handling compression.

    Args:
        filepath: File to stream
    """
    try:
        if filepath.suffix == ".gz":
            # Handle compressed files
            try:
                with gzip.open(filepath, "rt", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        print(line, end="")
                        sys.stdout.flush()
            except (gzip.BadGzipFile, UnicodeDecodeError, OSError):
                # Skip corrupted or unreadable compressed files
                pass
        elif is_text_file(filepath):
            # Handle text files
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        print(line, end="")
                        sys.stdout.flush()
            except (UnicodeDecodeError, OSError):
                # Skip unreadable text files
                pass
    except (PermissionError, OSError):
        # Skip files we can't read
        pass


def stream_historical_logs() -> None:
    """Stream all historical log files to stdout."""
    print("Dumping logs...", file=sys.stderr)

    for ctime, filepath in discover_historical_logs():
        # Print progress indicator
        print("🪵", end="", file=sys.stderr)
        sys.stderr.flush()

        stream_file_content(filepath)

    # Add newline after progress indicators
    print("", file=sys.stderr)


async def follow_live_logs(last_modified_minutes: int = 60) -> None:
    """
    Follow live log files using pure Python implementation.

    Args:
        last_modified_minutes: Only follow files modified within this many minutes
    """
    live_logs = discover_live_logs(last_modified_minutes)

    if not live_logs:
        print("No recent log files found to follow.", file=sys.stderr)
        return

    print("Following logs...", file=sys.stderr)
    for logfile in live_logs:
        print(f"Will tail: {logfile}", file=sys.stderr)

    # Pure Python implementation of tail -F
    await tail_multiple_files(live_logs)


async def tail_multiple_files(filepaths: List[Path]) -> None:
    """
    Pure Python implementation of tail -F for multiple files.

    Args:
        filepaths: List of file paths to tail
    """
    # Keep track of file handles and positions
    file_states = {}

    # Initialize file states - seek to end (like tail -n0)
    for filepath in filepaths:
        try:
            f = open(filepath, "r", encoding="utf-8", errors="ignore")
            f.seek(0, 2)  # Seek to end
            file_states[filepath] = {
                "handle": f,
                "position": f.tell(),
                "inode": filepath.stat().st_ino if filepath.exists() else None,
            }
        except (OSError, PermissionError):
            # Skip files we can't open
            pass

    try:
        while True:
            any_output = False

            for filepath in list(file_states.keys()):
                state = file_states[filepath]

                try:
                    # Check if file was rotated/recreated (inode changed)
                    if filepath.exists():
                        current_inode = filepath.stat().st_ino
                        if state["inode"] != current_inode:
                            # File was rotated, reopen
                            state["handle"].close()
                            f = open(filepath, "r", encoding="utf-8", errors="ignore")
                            file_states[filepath] = {"handle": f, "position": 0, "inode": current_inode}
                            state = file_states[filepath]

                    # Read new content
                    f = state["handle"]
                    f.seek(state["position"])
                    new_content = f.read()

                    if new_content:
                        print(new_content, end="")
                        sys.stdout.flush()
                        any_output = True
                        state["position"] = f.tell()

                except (OSError, PermissionError):
                    # File became unreadable, remove from tracking
                    if filepath in file_states:
                        try:
                            file_states[filepath]["handle"].close()
                        except Exception:
                            pass
                        del file_states[filepath]

            if not any_output:
                await asyncio.sleep(0.1)  # Brief sleep when no new content

    except KeyboardInterrupt:
        pass
    finally:
        # Clean up file handles
        for state in file_states.values():
            try:
                state["handle"].close()
            except Exception:
                pass


def setup_signal_handlers() -> None:
    """Set up clean signal handling."""

    def signal_handler(signum, frame):
        print("\nShutting down...", file=sys.stderr)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Stream system logs for logloglog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Stream historical + follow live logs
  %(prog)s --follow-only             # Only follow live logs
  %(prog)s --last-modified 120       # Follow logs modified in last 2 hours
        """,
    )

    parser.add_argument("--historical-only", action="store_true", help="Only dump historical logs, then exit")

    parser.add_argument("--follow-only", action="store_true", help="Only follow live logs")

    parser.add_argument(
        "--last-modified",
        type=int,
        default=60,
        metavar="MINUTES",
        help="Follow logs modified within MINUTES (default: 60)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.historical_only and args.follow_only:
        print("Error: Cannot use both --historical-only and --follow-only", file=sys.stderr)
        sys.exit(1)

    setup_signal_handlers()

    try:
        if args.historical_only:
            stream_historical_logs()
        elif args.follow_only:
            await follow_live_logs(args.last_modified)
        else:
            # Default: both historical then live (original behavior)
            stream_historical_logs()
            await follow_live_logs(args.last_modified)

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
