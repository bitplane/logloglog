#!/usr/bin/env python3
"""
Basic usage example for BigLog.

This example demonstrates:
- Opening a log file
- Basic line access
- Creating views at different terminal widths
- Appending new lines
- Custom width functions
"""

import tempfile
from pathlib import Path
from biglog import BigLog


def main():
    # Create a sample log file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write("Welcome to BigLog example!\n")
        f.write("This is a short line.\n")
        f.write(
            "This is a much longer line that will wrap when displayed at narrow terminal widths like 40 or 60 characters.\n"
        )
        f.write("Here's another line with some unicode: 🚀 📊 🎉\n")
        f.write("And a very long line: " + "x" * 200 + "\n")
        log_path = f.name

    print(f"Created sample log at: {log_path}")

    try:
        # Open the log with BigLog
        with BigLog(log_path) as log:
            print("\n=== Basic Access ===")
            print(f"Total lines: {len(log)}")
            print(f"First line: '{log[0]}'")
            print(f"Last line: '{log[-1][:50]}...'")

            print("\n=== All Lines ===")
            for i, line in enumerate(log):
                print(f"Line {i}: {line[:60]}{'...' if len(line) > 60 else ''}")

            print("\n=== View at 40 characters width ===")
            view40 = log.at(width=40)
            print(f"Total display rows at width 40: {len(view40)}")
            for i in range(min(10, len(view40))):
                print(f"Row {i:2}: '{view40[i]}'")

            print("\n=== View at 80 characters width ===")
            view80 = log.at(width=80)
            print(f"Total display rows at width 80: {len(view80)}")
            for i in range(min(10, len(view80))):
                print(f"Row {i:2}: '{view80[i]}'")

            print("\n=== Appending new lines ===")
            log.append("This is a new line added via BigLog!")
            log.append("Another line with emojis: 🔥 💻 📈")

            print(f"Total lines after append: {len(log)}")
            print("New lines:")
            print(f"  Line {len(log)-2}: '{log[-2]}'")
            print(f"  Line {len(log)-1}: '{log[-1]}'")

            print("\n=== Partial view (rows 5-10 at width 60) ===")
            partial_view = log.at(width=60, start=5, end=10)
            print(f"Partial view length: {len(partial_view)}")
            for i, row in enumerate(partial_view):
                print(f"Row {i+5}: '{row}'")

    finally:
        # Clean up
        Path(log_path).unlink()
        print(f"\nCleaned up {log_path}")


def custom_width_example():
    """Example with custom width calculation."""
    print(f"\n{'='*50}")
    print("CUSTOM WIDTH FUNCTION EXAMPLE")
    print(f"{'='*50}")

    def tab_aware_width(line: str) -> int:
        """Custom width function that handles tabs."""
        # Replace tabs with 4 spaces
        expanded = line.replace("\t", "    ")
        return len(expanded)

    # Create log with tabs
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write("Column1\tColumn2\tColumn3\n")
        f.write("A\tB\tC\n")
        f.write("LongValue\tAnotherLong\tThirdColumn\n")
        log_path = f.name

    try:
        # Compare default vs custom width
        print("Default width calculation:")
        with BigLog(log_path) as log_default:
            for i, line in enumerate(log_default):
                print(f"  Line {i}: '{line}' (displayed length varies)")

        print("\nCustom width calculation (tabs = 4 spaces):")
        with BigLog(log_path, get_width=tab_aware_width) as log_custom:
            view = log_custom.at(width=20)
            print(f"Display rows at width 20: {len(view)}")
            for i in range(len(view)):
                print(f"  Row {i}: '{view[i]}'")

    finally:
        Path(log_path).unlink()


if __name__ == "__main__":
    main()
    custom_width_example()
    print("\nExample complete!")
