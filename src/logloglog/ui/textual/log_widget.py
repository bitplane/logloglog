from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.geometry import Size
from textual.message import Message
from rich.segment import Segment
from rich.markup import escape


class LogWidget(ScrollView):
    """A scrollable widget to display log data."""

    class LogUpdated(Message):
        """Posted when log display updates (scroll, resize, etc)."""

        def __init__(self, scroll_y: int, total_rows: int, width: int) -> None:
            super().__init__()
            self.scroll_y = scroll_y
            self.total_rows = total_rows
            self.width = width

    DEFAULT_CSS = """
    LogWidget {
        padding: 0;
        margin: 0;
        border: none;
        scrollbar-size-horizontal: 0;
        overflow-y: scroll;
        width: 100%;
        height: 100%;
    }
    """

    can_focus = True

    def __init__(self, log_data, **kwargs):
        super().__init__(**kwargs)
        self.log_data = log_data
        self.log_view = None
        self.current_width = 0

    def on_mount(self):
        """Called when widget is mounted."""
        if self.size.width > 0:
            self.set_width(self.size.width)

    def on_resize(self, event):
        """Called when widget is resized."""
        if event.size.width > 0 and event.size.width != self.current_width:
            current_scroll_y = self.scroll_y if self.log_view else 0

            if self.log_view and self.current_width > 0 and current_scroll_y > 0:
                try:
                    # Find which logical line we're currently viewing using OLD width
                    logical_line, line_offset = self.log_data.line_at_row(current_scroll_y, self.current_width)

                    # Use the new API to get display row at NEW width
                    new_display_row = self.log_data.row_for_line(logical_line, event.size.width)
                    new_display_row += line_offset

                    # Now update width and scroll
                    self.set_width(event.size.width)
                    self.scroll_to(y=new_display_row, animate=False)
                except Exception:
                    # Fallback
                    self.set_width(event.size.width)
            else:
                self.set_width(event.size.width)

    def set_width(self, width: int):
        self.log_view = self.log_data.width(width)
        self.virtual_size = Size(width, len(self.log_view))
        self.current_width = width
        self.refresh()

    def _post_log_updated(self):
        """Post a LogUpdated message with current state."""
        if self.log_view is not None:
            self.post_message(
                self.LogUpdated(scroll_y=int(self.scroll_y), total_rows=len(self.log_view), width=self.current_width)
            )

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        """Called when scroll position changes."""
        super().watch_scroll_y(old_value, new_value)
        if round(old_value) != round(new_value):
            self._post_log_updated()

    def watch_virtual_size(self, old_size: Size, new_size: Size) -> None:
        """Called when virtual (scrollable) size changes."""
        self._post_log_updated()

    def render_line(self, y: int) -> Strip:
        """Render a single line of the log."""
        if self.log_view is None:
            return Strip.blank(self.size.width)

        scroll_y = self.scroll_offset.y
        line_index = scroll_y + y

        try:
            line_text = self.log_view[line_index]
            return Strip([Segment(escape(line_text))])
        except IndexError:
            return Strip.blank(self.size.width)

    def scroll_to(self, x=None, y=None, **kwargs):
        """Override scroll_to to always disable animation."""
        return super().scroll_to(x=x, y=y, animate=False)

    def scroll_up(self, **kwargs):
        """Override scroll_up to always disable animation."""
        return super().scroll_up(animate=False)

    def scroll_down(self, **kwargs):
        """Override scroll_down to always disable animation."""
        return super().scroll_down(animate=False)
