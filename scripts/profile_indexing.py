#!/usr/bin/env python3
"""Profile indexing performance for snakeviz analysis."""

import cProfile
import pstats
import sys
import tempfile
from pathlib import Path

from logloglog import LogLogLog
from logloglog.cache import Cache


def profile_indexing(log_path: str, output_file: str = "logs/profile.stats"):
    """Profile indexing of a log file."""

    # Ensure output directory exists
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a temporary cache to ensure fresh indexing
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = Cache(Path(tmpdir))

        print(f"Profiling indexing of {log_path}")
        print(f"Output will be saved to {output_file}")
        print("Running profiler...")

        profiler = cProfile.Profile()
        profiler.enable()

        # This is what we're profiling
        log = LogLogLog(log_path, cache=cache)
        log.close()

        profiler.disable()

        # Save stats
        profiler.dump_stats(output_file)

        # Print summary
        print(f"\nProfile saved to {output_file}")
        print("To view with snakeviz:")
        print(f"  snakeviz {output_file}")
        print("\nTop 20 functions by cumulative time:")
        stats = pstats.Stats(output_file)
        stats.sort_stats("cumulative")
        stats.print_stats(20)

        print("\n\nArrayfile functions:")
        stats.print_stats("arrayfile")

        print("\n\nLineIndex functions:")
        stats.print_stats("line_index")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python profile_indexing.py <log_file> [output.stats]")
        print("Example: python profile_indexing.py logs/log.log.log profile.stats")
        sys.exit(1)

    log_path = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "profile.stats"

    if not Path(log_path).exists():
        print(f"Error: {log_path} does not exist")
        sys.exit(1)

    profile_indexing(log_path, output_file)
