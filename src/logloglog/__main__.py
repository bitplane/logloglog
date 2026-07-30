"""Command line entry point for the package."""

import argparse

from . import LogLogLog


def main() -> None:
    """Print a wrapped view of a log file."""
    parser = argparse.ArgumentParser(description="Print a wrapped log view.")
    parser.add_argument("log_file", help="Path to the log file to display.")
    parser.add_argument("-w", "--width", type=int, default=80, help="Display width for wrapping. Default: 80.")
    args = parser.parse_args()

    with LogLogLog(args.log_file) as log:
        for row in log.width(args.width):
            print(row)


if __name__ == "__main__":
    main()
