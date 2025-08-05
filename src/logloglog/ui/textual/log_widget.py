import asyncio
import logging
from pathlib import Path
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.geometry import Size
from textual.message import Message
from rich.segment import Segment
from rich.markup import escape

# Configure logger
logger = logging.getLogger(__name__)


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

    def __init__(self, log_data_or_path, **kwargs):
        super().__init__(**kwargs)
        self.log_data = None
        self.log_view = None
        self.current_width = 0
        self._refresh_task = None
        self._auto_refresh_enabled = True

        # Handle both LogLogLog instances and file paths
        if isinstance(log_data_or_path, (str, Path)):
            self._log_path = Path(log_data_or_path)
            self._needs_async_init = True
        else:
            self.log_data = log_data_or_path
            self._log_path = None
            self._needs_async_init = False

    def on_mount(self):
        """Called when widget is mounted."""
        logger.info(f"LogWidget on_mount called, needs_async_init={self._needs_async_init}")

        if self._needs_async_init:
            # Start auto-refresh - it will create LogLogLog on first iteration
            logger.info(f"Starting auto-refresh for async init of path: {self._log_path}")
            if self._auto_refresh_enabled:
                self.start_auto_refresh()
        else:
            # Only set width if we have log data
            if self.size.width > 0 and self.log_data:
                self.set_width(self.size.width)
            if self._auto_refresh_enabled and self.log_data:
                # Start auto-refresh for existing log data
                self.start_auto_refresh()

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

    def start_auto_refresh(self, interval: float = 1.0):
        """Start background task to automatically refresh log data."""
        if self._refresh_task is None:
            logger.info(f"Starting auto-refresh with {interval}s interval")
            self._refresh_task = self.run_worker(self._auto_refresh_loop(interval))
            # Also start a timer to update the UI periodically
            self.set_timer(0.5, self._update_display, name="display_update")

    def stop_auto_refresh(self):
        """Stop the background refresh task."""
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

    def enable_auto_refresh(self, enabled: bool = True):
        """Enable or disable auto-refresh functionality."""
        self._auto_refresh_enabled = enabled
        if enabled and self.is_mounted:
            self.start_auto_refresh()
        elif not enabled:
            self.stop_auto_refresh()

    async def _auto_refresh_loop(self, interval: float):
        """Background task that periodically checks for log updates."""
        logger.info("Auto-refresh loop started")
        try:
            logger.info(
                f"Loop conditions: auto_refresh_enabled={self._auto_refresh_enabled}, is_mounted={self.is_mounted}"
            )
            while self._auto_refresh_enabled and self.is_mounted:
                logger.info("Auto-refresh loop iteration starting")
                await self.arefresh_log_data()
                logger.info(f"Auto-refresh complete, sleeping for {interval}s")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Auto-refresh loop cancelled")
        except Exception as e:
            logger.error(f"Auto-refresh error: {e}")
            import traceback

            logger.error(traceback.format_exc())

    async def arefresh_log_data(self):
        """Async method to refresh log data without blocking the UI."""
        logger.info("arefresh_log_data called")
        try:
            # Create LogLogLog if needed (for deferred initialization)
            if self.log_data is None and self._needs_async_init and self._log_path:
                from logloglog import LogLogLog

                logger.info(f"Creating deferred LogLogLog for {self._log_path}")
                self.log_data = LogLogLog(self._log_path, defer_indexing=True)
                logger.info(f"LogLogLog created successfully, self.log_data = {self.log_data}")
                logger.info(f"Type of self.log_data: {type(self.log_data)}")
                logger.info(f"Bool of self.log_data: {bool(self.log_data)}")

            # Skip if still no log data object
            if self.log_data is None:
                logger.info("arefresh_log_data: no log data object, skipping")
                return

            logger.info(f"Proceeding with refresh, log_data exists: {type(self.log_data)}")

            # Check if log data has async update capability
            if hasattr(self.log_data, "aupdate"):
                await self.log_data.aupdate()
            else:
                # Fall back to sync update in a thread
                await asyncio.to_thread(self.log_data.update)

            logger.info(f"Data update complete, LogLogLog has {len(self.log_data)} lines")

            # Set initial width if not set yet
            if self.current_width == 0 and self.size.width > 0:
                self.current_width = self.size.width
                logger.info(f"Setting initial width to {self.current_width}")

            # Update the view if we have a width set
            if self.current_width > 0:
                # Just call set_width to trigger the same update that works on resize
                self.call_from_thread(lambda: self.set_width(self.current_width))

        except Exception as e:
            # Log error but don't crash
            logger.warning(f"Failed to refresh log data: {e}")

    async def aset_width(self, width: int):
        """Async version of set_width for non-blocking width changes."""
        if hasattr(self.log_data, "width"):
            # Run width calculation in thread to avoid blocking
            self.log_view = await asyncio.to_thread(self.log_data.width, width)
        else:
            self.log_view = self.log_data.width(width)

        self.virtual_size = Size(width, len(self.log_view))
        self.current_width = width
        self.refresh()

    def _update_display(self):
        """Update the display - runs on main thread via timer."""
        if self.log_data and self.current_width > 0:
            # Call set_width to update the view and refresh
            self.set_width(self.current_width)
            # Reschedule the timer
            self.set_timer(0.5, self._update_display, name="display_update")

    def on_unmount(self):
        """Called when widget is unmounted - cleanup background tasks."""
        self.stop_auto_refresh()
