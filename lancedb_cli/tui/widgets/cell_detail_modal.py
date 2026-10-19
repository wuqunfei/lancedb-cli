"""Modal dialog showing the full, untruncated value of a double-clicked results cell."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class CellDetailModal(ModalScreen[None]):
    BINDINGS = [("escape", "close_", "Close")]

    def __init__(self, column_name: str, value: Any) -> None:
        super().__init__()
        self._column_name = column_name
        self._value = value

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(f"Column: {self._column_name}", id="cell-detail-title"),
            VerticalScroll(Static(str(self._value), id="cell-detail-value")),
            Button("Close", id="cell-detail-close", variant="primary"),
            id="cell-detail-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close_(self) -> None:
        self.dismiss(None)
