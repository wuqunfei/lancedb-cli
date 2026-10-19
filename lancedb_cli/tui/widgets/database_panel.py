"""Top-left panel: pick a recently-opened database, type a path directly, or browse
to one via a folder-picker dialog. Opening a path that doesn't exist yet creates it
there (same as the /create slash command) — lancedb does this automatically.
"""

from pathlib import Path
from typing import List

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Button, Input, Label, ListItem, ListView

from .directory_browser_modal import DirectoryBrowserModal


class DatabasePanel(Vertical):
    """Lists recent database paths and lets the user type or browse to another one."""

    class DatabaseSelected(Message):
        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    def __init__(self, recent_paths: List[str], **kwargs):
        super().__init__(**kwargs)
        self._recent_paths = recent_paths
        self.border_title = "Database"

    def compose(self) -> ComposeResult:
        yield ListView(
            *[self._make_item(p) for p in self._recent_paths],
            id="recent-db-list",
        )
        yield Input(placeholder="path to open...", id="db-path-input")
        yield Button("Browse...", id="browse-db-button", variant="primary")

    @staticmethod
    def _make_item(path: str) -> ListItem:
        item = ListItem(Label(path))
        item.path = path
        return item

    def set_recent_paths(self, paths: List[str]) -> None:
        self._recent_paths = paths
        list_view = self.query_one("#recent-db-list", ListView)
        list_view.clear()
        for p in paths:
            list_view.append(self._make_item(p))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.post_message(self.DatabaseSelected(event.item.path))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "db-path-input":
            return
        path = event.value.strip()
        if path:
            self.post_message(self.DatabaseSelected(path))
            event.input.value = ""

    @work
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "browse-db-button":
            return
        typed = self.query_one("#db-path-input", Input).value.strip()
        start = typed if typed and Path(typed).is_dir() else "."
        path = await self.app.push_screen_wait(DirectoryBrowserModal(start_path=start))
        if path:
            self.post_message(self.DatabaseSelected(path))
