"""Top-left panel: type a database path directly, or browse to one via a folder-picker
dialog. Opening a path that doesn't exist yet creates it there (same as the /create
slash command) — lancedb does this automatically.
"""

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input

from ...core.connection import ConnectionRequest
from .connect_modal import ConnectModal

DARK_ICON = "🌙"
LIGHT_ICON = "☀️"


class DatabasePanel(Vertical):
    """Lets the user type a database path or browse to one."""

    class DatabaseSelected(Message):
        def __init__(self, request: ConnectionRequest) -> None:
            self.request = request
            super().__init__()

    class ThemeToggleRequested(Message):
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.border_title = "Database"

    def compose(self) -> ComposeResult:
        yield Input(placeholder="path to open...", id="db-path-input")
        yield Horizontal(
            Button("Connect...", id="open-db-button", variant="primary"),
            Button(DARK_ICON, id="theme-toggle-button"),
            id="database-panel-actions",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "db-path-input":
            return
        path = event.value.strip()
        if path:
            self.post_message(self.DatabaseSelected(ConnectionRequest.local(path)))

    def set_theme_icon(self, is_dark: bool) -> None:
        self.query_one("#theme-toggle-button", Button).label = DARK_ICON if is_dark else LIGHT_ICON

    def set_path(self, path: str) -> None:
        self.query_one("#db-path-input", Input).value = path

    @work
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "theme-toggle-button":
            self.post_message(self.ThemeToggleRequested())
            return
        if event.button.id != "open-db-button":
            return
        typed = self.query_one("#db-path-input", Input).value.strip()
        start = typed if typed and Path(typed).is_dir() else "."
        request = await self.app.push_screen_wait(ConnectModal(recent=self.app.recent_dbs, initial_path=start))
        if request:
            self.post_message(self.DatabaseSelected(request))
