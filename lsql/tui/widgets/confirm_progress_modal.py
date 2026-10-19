"""Confirmation dialog for commands that may take a while to run (currently just
/embedding — model load/download plus a full-table read+rewrite). Clicking "Yes"
disables both buttons and shows a spinner while the command runs in a worker thread,
instead of freezing the whole event loop for the duration with no feedback."""

from typing import Callable

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, LoadingIndicator

from ...commands.results import CommandResult, cancelled


class ConfirmProgressModal(ModalScreen[CommandResult]):
    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n", "cancel_", "No"),
        ("escape", "cancel_", "Cancel"),
    ]

    def __init__(self, message: str, run: Callable[[], CommandResult]) -> None:
        super().__init__()
        self.message = message
        self._run = run
        self._running = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.message, id="confirm-progress-message"),
            LoadingIndicator(id="confirm-progress-spinner"),
            Horizontal(
                Button("Yes", id="confirm-progress-yes"),
                Button("No", id="confirm-progress-no"),
                id="confirm-progress-buttons",
            ),
            id="confirm-progress-dialog",
        )

    def on_mount(self) -> None:
        self.query_one("#confirm-progress-spinner", LoadingIndicator).display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-progress-yes":
            self._start()
        elif event.button.id == "confirm-progress-no":
            self.dismiss(cancelled())

    def action_confirm(self) -> None:
        if not self._running:
            self._start()

    def action_cancel_(self) -> None:
        # Mirrors the "No" button's own disabled state — Escape/"n" are screen-level
        # keybindings and bypass a disabled widget's click-blocking, so once running
        # (no meaningful way to cancel a thread already in flight) they need their own
        # guard, same as EmbeddingModelDownloadModal's Cancel.
        if not self._running:
            self.dismiss(cancelled())

    def _start(self) -> None:
        self._running = True
        self.query_one("#confirm-progress-yes", Button).disabled = True
        self.query_one("#confirm-progress-no", Button).disabled = True
        self.query_one("#confirm-progress-spinner", LoadingIndicator).display = True
        self._execute()

    @work(thread=True)
    def _execute(self) -> None:
        result = self._run()
        self.app.call_from_thread(self.dismiss, result)
