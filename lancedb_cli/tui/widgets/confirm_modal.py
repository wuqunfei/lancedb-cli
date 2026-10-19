"""Confirmation dialog shown before destructive commands (/drop, /empty, /delete)."""

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n", "cancel_", "No"),
        ("escape", "cancel_", "Cancel"),
    ]

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(self.message, id="confirm-message"),
            Button("Yes", id="confirm-yes", variant="error"),
            Button("No", id="confirm-no", variant="primary"),
            id="confirm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel_(self) -> None:
        self.dismiss(False)
