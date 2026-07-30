"""Tests for the Textual demo dependencies."""

import subprocess
import sys


def test_textual_demo_help_imports():
    """The Textual demo should import successfully with pinned dependencies."""
    result = subprocess.run(
        [sys.executable, "demos/textual_demo.py", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0
    assert "Textual demo for logloglog" in result.stdout
    assert result.stderr == ""
