"""Modal shown while loading an embedding model — the load (via core.db.get_embedding_function)
is a blocking call (huggingface_hub download + torch model load on first use), so it runs
in a worker thread to avoid freezing the whole Textual event loop."""

from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, LoadingIndicator

from ...core import db  # module import so tests can monkeypatch db.get_embedding_function


class EmbeddingModelDownloadModal(ModalScreen[bool]):
    """Loads (downloading + caching on first use) a sentence-transformers model by name,
    showing a spinner while the blocking load runs off the Textual event loop."""

    BINDINGS = [("escape", "cancel_", "Cancel")]

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self.model_name = model_name
        self._error: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(f"Loading embedding model '{self.model_name}'...", id="embedding-modal-title"),
            LoadingIndicator(id="embedding-modal-spinner"),
            Label("", id="embedding-modal-status"),
            Horizontal(
                Button("Retry", id="embedding-modal-retry", disabled=True),
                Button("Cancel", id="embedding-modal-cancel", disabled=True),
                id="embedding-modal-buttons",
            ),
            id="embedding-modal-dialog",
        )

    def on_mount(self) -> None:
        self._load()

    @work(thread=True)
    def _load(self) -> None:
        try:
            db.get_embedding_function(self.model_name)
        except Exception as e:
            self._error = str(e)
            self.app.call_from_thread(self._show_error)
            return
        self.app.call_from_thread(self.dismiss, True)

    def _show_error(self) -> None:
        self.query_one("#embedding-modal-spinner", LoadingIndicator).display = False
        self.query_one("#embedding-modal-status", Label).update(f"Failed: {self._error}")
        self.query_one("#embedding-modal-retry", Button).disabled = False
        self.query_one("#embedding-modal-cancel", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "embedding-modal-cancel":
            self.dismiss(False)
        elif event.button.id == "embedding-modal-retry":
            self.query_one("#embedding-modal-status", Label).update("")
            self.query_one("#embedding-modal-spinner", LoadingIndicator).display = True
            self.query_one("#embedding-modal-retry", Button).disabled = True
            self.query_one("#embedding-modal-cancel", Button).disabled = True
            self._load()

    def action_cancel_(self) -> None:
        # Mirrors the Cancel button's own disabled state — Escape is a screen-level
        # keybinding and bypasses a disabled widget's click-blocking, so it needs its
        # own guard against cancelling a load that's still actively running.
        if not self.query_one("#embedding-modal-cancel", Button).disabled:
            self.dismiss(False)
