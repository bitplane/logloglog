#!/usr/bin/env python3
import logging
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Header

from textual_window import Window, WindowBar, WindowSwitcher
from logloglog.ui.textual import LogWidget


class WindowDemo(App):
    CSS = """
    #main_container {
        align: center middle;
        background: transparent;
    }

    #log_display {
        width: 100%;
        height: 100%;
    }

    #logloglog {
        width: 60;
        height: 20;
    }

    #logloglog > * {
        padding: 0;
        margin: 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+e", "toggle_windowbar", "Window Bar"),
        Binding("f1", "toggle_switcher", "Window Switcher", key_display="F1"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.title = "Textual-Window Test App"

        # Setup logging
        log_file = Path("./logs/textual_demo.log")
        log_file.parent.mkdir(exist_ok=True)

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            filemode="a",
        )
        self.logger = logging.getLogger(__name__)

        self.log_file = Path("./logs/log.log.log")
        self.log_data = None  # Will be created by widget
        self.current_width = 80  # Default width

        self.logger.info("Textual Window Demo app started")

    def compose(self) -> ComposeResult:
        yield WindowSwitcher()
        yield WindowBar(start_open=True)
        yield Header()

        with Container(id="main_container"):
            with Window(
                id="logloglog",
                icon="🪵",
                name="log.log.log",
                starting_horizontal="center",
                starting_vertical="middle",
                start_open=True,
            ):
                yield LogWidget(self.log_file, id="log_display")

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.update_window_stats()

    def get_stats_text(self) -> str:
        """Generate stats text for the window."""
        try:
            # Get file size
            file_size = self.log_file.stat().st_size if self.log_file.exists() else 0
            if file_size > 1024 * 1024:
                size_str = f"{file_size/(1024*1024):.0f}MB"
            elif file_size > 1024:
                size_str = f"{file_size/1024:.0f}KB"
            else:
                size_str = f"{file_size}B"

            # Get log info
            log_widget = self.query_one("#log_display", LogWidget)
            total_lines = len(log_widget.log_data) if log_widget.log_data else 0

            if total_lines > 0:
                # Try to get current scroll position from LogWidget
                try:
                    log_widget = self.query_one("#log_display")
                    current_row = int(log_widget.scroll_y) if hasattr(log_widget, "scroll_y") else 0
                    total_rows = (
                        len(log_widget.log_view) if hasattr(log_widget, "log_view") and log_widget.log_view else 0
                    )
                    width = log_widget.current_width if hasattr(log_widget, "current_width") else 80
                    return f"{current_row}/{total_rows} [{width}] | {size_str}"
                except Exception:
                    return f"0/0 [80] | {size_str}"
            else:
                return f"Empty | {size_str}"
        except Exception:
            return "Stats error"

    def update_window_stats(self) -> None:
        """Update the window bottom bar with stats."""
        try:
            # Find the bottom bar text element within our window
            bottom_text = self.query_one("#logloglog #bottom_bar_text")
            stats_text = self.get_stats_text()
            # Set the content of the bottom bar text
            bottom_text.update(stats_text)
        except Exception:
            pass  # Silently ignore if elements not ready yet

    def on_log_widget_log_updated(self, event: LogWidget.LogUpdated) -> None:
        """Handle LogUpdated events from the LogWidget."""
        self.current_width = event.width
        self.update_window_stats()

    def action_toggle_windowbar(self) -> None:
        windowbar = self.query_one(WindowBar)
        windowbar.toggle_bar()
        self.logger.info("WindowBar toggled")

    def action_toggle_switcher(self) -> None:
        cycler = self.query_one(WindowSwitcher)
        cycler.show()
        self.logger.info("Window switcher shown")


def run_demo() -> None:
    WindowDemo().run()


if __name__ == "__main__":
    run_demo()
