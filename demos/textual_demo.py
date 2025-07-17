#!/usr/bin/env python3
import logging
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Header

from textual_window import Window, WindowBar, WindowSwitcher
from logloglog.ui.textual import LogWidget
from logloglog import LogLogLog


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
        self.log_data = LogLogLog(self.log_file)

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
                yield LogWidget(self.log_data, id="log_display")

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
