"""Panel for setting the embedding model used by /embedding. Typing a model name and
submitting it, or clicking "Set", opens a modal that loads (downloading + caching on
first use) the model before reporting success back to the app."""

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input

from .embedding_model_download_modal import EmbeddingModelDownloadModal


class EmbeddingModelPanel(Vertical):
    """Lets the user type an embedding model name and "Set" it (downloading first)."""

    class ModelSelected(Message):
        def __init__(self, name: str) -> None:
            self.name = name
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.border_title = "Embedding Model"

    def compose(self) -> ComposeResult:
        yield Input(placeholder="org/model-name...", id="embedding-model-input")
        yield Horizontal(
            Button("Set", id="set-embedding-button", variant="primary"),
            id="embedding-panel-actions",
        )

    def set_model_name(self, name: str) -> None:
        self.query_one("#embedding-model-input", Input).value = name

    async def _prompt_and_set(self, name: str) -> None:
        ok = await self.app.push_screen_wait(EmbeddingModelDownloadModal(name))
        if ok:
            self.post_message(self.ModelSelected(name))

    @work
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "embedding-model-input":
            return
        name = event.value.strip()
        if name:
            await self._prompt_and_set(name)

    @work
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "set-embedding-button":
            return
        name = self.query_one("#embedding-model-input", Input).value.strip()
        if name:
            await self._prompt_and_set(name)
