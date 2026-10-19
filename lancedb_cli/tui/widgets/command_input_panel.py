"""Top-right panel: a single command-line input with history recall and slash-command
auto-suggestion (type "/" to see matching commands; Up/Down to pick one, Tab/Enter to
accept, Escape to dismiss)."""

from typing import List, Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from ...commands.registry import COMMANDS

COMMAND_NAMES = sorted(COMMANDS.keys())


class HistoryInput(Input):
    """An Input that cycles through a list of previous values on up/down arrow — unless
    the slash-command suggestion list is open, in which case up/down/tab/enter/escape
    control that instead."""

    def __init__(self, history: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)
        self._history = history or []
        self._index: Optional[int] = None
        self._draft = ""
        self.suggestions: Optional[OptionList] = None  # wired by CommandInputPanel after mount

    def set_history(self, history: List[str]) -> None:
        self._history = history
        self._index = None

    def key_up(self) -> None:
        if not self._history:
            return
        if self._index is None:
            self._draft = self.value
            self._index = len(self._history)
        if self._index > 0:
            self._index -= 1
            self.value = self._history[self._index]
            self.cursor_position = len(self.value)
        if self.suggestions is not None:
            self.suggestions.display = False

    def key_down(self) -> None:
        if self._index is None:
            return
        self._index += 1
        if self._index >= len(self._history):
            self._index = None
            self.value = self._draft
        else:
            self.value = self._history[self._index]
        self.cursor_position = len(self.value)
        if self.suggestions is not None:
            self.suggestions.display = False

    def reset_history_cursor(self) -> None:
        self._index = None
        self._draft = ""

    def _suggestions_open(self) -> bool:
        return self.suggestions is not None and self.suggestions.display

    def _accept_suggestion(self) -> None:
        index = self.suggestions.highlighted or 0
        option = self.suggestions.get_option_at_index(index)
        self.value = f"/{option.id} "
        self.cursor_position = len(self.value)
        self.suggestions.display = False

    async def _on_key(self, event: events.Key) -> None:
        if self._suggestions_open():
            if event.key == "down":
                self.suggestions.action_cursor_down()
                event.stop()
                event.prevent_default()
                return
            if event.key == "up":
                self.suggestions.action_cursor_up()
                event.stop()
                event.prevent_default()
                return
            if event.key in ("tab", "enter"):
                self._accept_suggestion()
                event.stop()
                event.prevent_default()
                return
            if event.key == "escape":
                self.suggestions.display = False
                event.stop()
                event.prevent_default()
                return
        await super()._on_key(event)


class CommandInputPanel(Vertical):
    """Hosts the status line (current db/table), the slash-command input, and its
    auto-suggestion dropdown."""

    def __init__(self, history: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)
        self._initial_history = history or []
        self.border_title = "Command"

    def compose(self) -> ComposeResult:
        yield Static("No database open", id="status-line")
        yield HistoryInput(
            history=self._initial_history,
            placeholder="/schema, /query --where \"x > 5\", /sql SELECT ...",
            id="command-input",
        )
        yield OptionList(id="command-suggestions")

    def on_mount(self) -> None:
        suggestions = self.query_one("#command-suggestions", OptionList)
        suggestions.display = False
        self.query_one("#command-input", HistoryInput).suggestions = suggestions

    def set_status(self, db_path: Optional[str], table: Optional[str]) -> None:
        status = self.query_one("#status-line", Static)
        if not db_path:
            status.update("No database open")
        elif not table:
            status.update(f"db: {db_path}")
        else:
            status.update(f"db: {db_path} | table: {table}")

    def set_history(self, history: List[str]) -> None:
        self.query_one("#command-input", HistoryInput).set_history(history)

    def set_input_value(self, text: str) -> None:
        """Display `text` in the command input without submitting it."""
        command_input = self.query_one("#command-input", HistoryInput)
        command_input.value = text
        command_input.cursor_position = len(text)
        self.query_one("#command-suggestions", OptionList).display = False

    def clear_input(self) -> None:
        command_input = self.query_one("#command-input", HistoryInput)
        command_input.value = ""
        command_input.reset_history_cursor()
        self.query_one("#command-suggestions", OptionList).display = False

    def focus_input(self) -> None:
        self.query_one("#command-input", HistoryInput).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "command-input":
            return
        self._update_suggestions(event.value)

    def _update_suggestions(self, value: str) -> None:
        suggestions = self.query_one("#command-suggestions", OptionList)
        if not value.startswith("/") or " " in value:
            suggestions.display = False
            return

        prefix = value[1:].lower()
        if prefix in COMMANDS:
            # Full command name already typed — hide suggestions so Enter submits
            # the command instead of being intercepted as "accept suggestion".
            suggestions.display = False
            return

        matches = [name for name in COMMAND_NAMES if name.startswith(prefix)]
        if not matches:
            suggestions.display = False
            return

        suggestions.clear_options()
        for name in matches:
            hint = COMMANDS[name].help_text
            label = f"/{name}" + (f"  — {hint}" if hint else "")
            suggestions.add_option(Option(label, id=name))
        suggestions.highlighted = 0
        suggestions.display = True
