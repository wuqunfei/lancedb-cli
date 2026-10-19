"""The LanceDB TUI application: database panel, table list, command input, results."""

from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input

from .. import persistence
from ..commands import registry
from ..commands import results as cmdresults
from ..commands.results import AppState, CommandResult
from ..core import db
from ..core.exceptions import CommandError
from ..core.parsing import convert_value
from ..core.system_theme import system_prefers_dark
from .widgets.command_input_panel import CommandInputPanel
from .widgets.confirm_modal import ConfirmModal
from .widgets.database_panel import DatabasePanel
from .widgets.embedding_model_panel import EmbeddingModelPanel
from .widgets.results_panel import ResultsPanel
from .widgets.table_list_panel import TableListPanel


class LanceDBApp(App):
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("ctrl+l", "focus_command", "Focus command"),
        ("ctrl+r", "do_refresh", "Refresh"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(
        self,
        initial_db_path: Optional[str] = None,
        recent_databases: Optional[persistence.RecentDatabases] = None,
        command_history: Optional[persistence.CommandHistory] = None,
        last_embedding_model: Optional[persistence.LastEmbeddingModel] = None,
    ):
        super().__init__()
        self.state = AppState()
        self.recent_dbs = recent_databases or persistence.RecentDatabases()
        self.history_store = command_history or persistence.CommandHistory()
        self.last_embedding_model = last_embedding_model or persistence.LastEmbeddingModel()
        self._initial_db_path = initial_db_path
        self._last_command_line: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Vertical(
                DatabasePanel(id="database-panel"),
                EmbeddingModelPanel(id="embedding-model-panel"),
                TableListPanel(id="table-list-panel"),
                id="left-column",
            ),
            Vertical(
                CommandInputPanel(history=self.history_store.load(), id="command-input-panel"),
                ResultsPanel(id="results-panel"),
                id="right-column",
            ),
            id="root",
        )

    def on_mount(self) -> None:
        is_dark = system_prefers_dark()
        self.theme = "textual-dark" if is_dark else "textual-light"
        self.query_one(DatabasePanel).set_theme_icon(is_dark)
        if self._initial_db_path:
            self._open_database(self._initial_db_path)
        last_model = self.last_embedding_model.load()
        if last_model:
            self.state.current_embedding_model = last_model
            self.query_one(EmbeddingModelPanel).set_model_name(last_model)
        self.query_one(CommandInputPanel).focus_input()

    def action_focus_command(self) -> None:
        self.query_one(CommandInputPanel).focus_input()

    @work
    async def action_do_refresh(self) -> None:
        await self._run_command_line("/refresh")

    @on(DatabasePanel.DatabaseSelected)
    def handle_database_selected(self, event: DatabasePanel.DatabaseSelected) -> None:
        self._open_database(event.path)

    @on(EmbeddingModelPanel.ModelSelected)
    def handle_embedding_model_selected(self, event: EmbeddingModelPanel.ModelSelected) -> None:
        self.state.current_embedding_model = event.name
        self.last_embedding_model.set(event.name)
        self.query_one(EmbeddingModelPanel).set_model_name(event.name)
        self.notify(f"Embedding model set to '{event.name}'")

    @on(DatabasePanel.ThemeToggleRequested)
    def handle_theme_toggle_requested(self, event: DatabasePanel.ThemeToggleRequested) -> None:
        is_dark = self.theme != "textual-light"
        self.theme = "textual-light" if is_dark else "textual-dark"
        self.query_one(DatabasePanel).set_theme_icon(not is_dark)

    @on(TableListPanel.TableSelected)
    @work
    async def handle_table_selected(self, event: TableListPanel.TableSelected) -> None:
        self.state.current_table = event.name
        command_panel = self.query_one(CommandInputPanel)
        command_panel.set_status(self.state.current_db_path, self.state.current_table)
        query_line = f"/sql select * from {event.name} limit 100"
        command_panel.set_input_value(query_line)
        await self._run_command_line(query_line)

    @on(Input.Submitted, "#command-input")
    @work
    async def handle_command_submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        self.query_one(CommandInputPanel).clear_input()
        if not line:
            return
        history = self.history_store.add(line)
        self.query_one(CommandInputPanel).set_history(history)
        await self._run_command_line(line)

    @on(ResultsPanel.CellUpdateRequested)
    @work
    async def handle_cell_update_requested(self, event: ResultsPanel.CellUpdateRequested) -> None:
        if self.state.connection is None or not self.state.current_table:
            self.query_one(ResultsPanel).show_result(cmdresults.error("No table selected to update"))
            return
        try:
            where = db.build_row_where_clause(event.where_row)
            new_value = convert_value(event.new_text)
            db.update_rows(self.state.connection, self.state.current_table, {event.column: new_value}, where)
        except CommandError as e:
            self.query_one(ResultsPanel).show_result(cmdresults.error(str(e)))
            return
        self.notify(f"Updated '{event.column}'")
        if self._last_command_line:
            await self._run_command_line(self._last_command_line)

    async def _run_command_line(self, line: str) -> None:
        self._last_command_line = line
        prepared = registry.prepare(self.state, line)
        if prepared is None:
            return
        if isinstance(prepared, CommandResult):
            self._show_result(prepared)
            return

        if prepared.confirm_message:
            confirmed = await self.push_screen_wait(ConfirmModal(prepared.confirm_message))
            if not confirmed:
                self.query_one(ResultsPanel).show_result(cmdresults.cancelled())
                return

        result = registry.execute(prepared)
        self._show_result(result)

    def _show_result(self, result: CommandResult) -> None:
        if result.kind == "exit":
            self.exit()
            return
        if result.opened_db_path and not self._open_database(result.opened_db_path):
            return  # _open_database already rendered the error
        self.query_one(ResultsPanel).show_result(result)
        if result.refresh_tables:
            self._refresh_table_list()

    def _open_database(self, path: str) -> bool:
        try:
            conn = db.connect(path)
        except CommandError as e:
            self.query_one(ResultsPanel).show_result(cmdresults.error(str(e)))
            return False
        self.state.connection = conn
        self.state.current_db_path = path
        self.state.current_table = None
        self.recent_dbs.add(path)
        self.query_one(ResultsPanel).clear()
        self.query_one(CommandInputPanel).set_status(path, None)
        self.query_one(DatabasePanel).set_path(path)
        self._refresh_table_list()
        return True

    def _refresh_table_list(self) -> None:
        try:
            names = db.list_tables(self.state.connection)
        except CommandError as e:
            self.query_one(ResultsPanel).show_result(cmdresults.error(str(e)))
            return
        self.query_one(TableListPanel).set_tables(names)
