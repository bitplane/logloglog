"""Tests for the log file abstraction."""

from logloglog.log_file import LogFile


def test_read_all_lines_preserves_blank_lines(tmp_path):
    path = tmp_path / "blank-lines.log"
    path.write_text("first\n\nthird\n")
    log_file = LogFile(path)
    log_file.open()

    try:
        assert log_file.read_all_lines() == ["first", "", "third"]
    finally:
        log_file.close()
