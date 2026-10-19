"""Modal dialog for picking an existing folder to open as a database."""

from pathlib import Path
from typing import Iterable, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Label


class FolderOnlyDirectoryTree(DirectoryTree):
    """A DirectoryTree that only ever lists directories — no files to pick through."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [p for p in paths if p.is_dir()]


class DirectoryBrowserModal(ModalScreen[Optional[str]]):
    """Lets the user browse the filesystem and pick an existing folder to open."""

    BINDINGS = [("escape", "cancel_", "Cancel")]

    def __init__(self, start_path: str = ".") -> None:
        super().__init__()
        self._selected_path = str(Path(start_path).resolve())

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Button("Up", id="browser-up"),
                Label("Select a database folder", id="browser-title"),
                id="browser-header",
            ),
            FolderOnlyDirectoryTree(self._selected_path, id="browser-tree"),
            Label(self._selected_path, id="browser-selected-path"),
            Horizontal(
                Button("Open", id="browser-open", variant="primary"),
                Button("Cancel", id="browser-cancel"),
                id="browser-buttons",
            ),
            id="browser-dialog",
        )

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self._selected_path = str(event.path)
        self.query_one("#browser-selected-path", Label).update(self._selected_path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "browser-open":
            self.dismiss(self._selected_path)
        elif event.button.id == "browser-cancel":
            self.dismiss(None)
        elif event.button.id == "browser-up":
            self._go_up()

    def _go_up(self) -> None:
        tree = self.query_one("#browser-tree", FolderOnlyDirectoryTree)
        parent = str(Path(tree.path).resolve().parent)
        tree.path = parent
        self._selected_path = parent
        self.query_one("#browser-selected-path", Label).update(parent)

    def action_cancel_(self) -> None:
        self.dismiss(None)
