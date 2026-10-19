"""Modal dialog for a double-clicked results cell: view the full untruncated value,
copy it, or edit it and write the change back to the table."""

from dataclasses import dataclass
from typing import Any, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, TextArea


@dataclass
class CellDialogResult:
    action: str  # "close" | "update"
    new_text: Optional[str] = None


class CellDetailModal(ModalScreen[CellDialogResult]):
    BINDINGS = [("escape", "close_", "Close")]

    def __init__(self, column_name: str, value: Any) -> None:
        super().__init__()
        self._column_name = column_name
        self._original_text = str(value)

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(f"Column: {self._column_name}", id="cell-detail-title"),
            TextArea(self._original_text, id="cell-detail-value"),
            Horizontal(
                Button("Copy", id="cell-detail-copy"),
                Button("Update", id="cell-detail-update"),
                Button("Close", id="cell-detail-close"),
                id="cell-detail-buttons",
            ),
            id="cell-detail-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cell-detail-close":
            self.dismiss(CellDialogResult(action="close"))
        elif event.button.id == "cell-detail-copy":
            self.app.copy_to_clipboard(self.query_one("#cell-detail-value", TextArea).text)
            self.notify("Copied to clipboard")
        elif event.button.id == "cell-detail-update":
            new_text = self.query_one("#cell-detail-value", TextArea).text
            self.dismiss(CellDialogResult(action="update", new_text=new_text))

    def action_close_(self) -> None:
        self.dismiss(CellDialogResult(action="close"))
