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
from .widgets.command_input_panel import CommandInputPanel
from .widgets.confirm_modal import ConfirmModal
from .widgets.database_panel import DatabasePanel
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
    ):
        super().__init__()
        self.state = AppState()
        self.recent_dbs = recent_databases or persistence.RecentDatabases()
        self.history_store = command_history or persistence.CommandHistory()
        self._initial_db_path = initial_db_path

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Vertical(
                DatabasePanel(recent_paths=self.recent_dbs.load(), id="database-panel"),
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
        if self._initial_db_path:
            self._open_database(self._initial_db_path)
        self.query_one(CommandInputPanel).focus_input()

    def action_focus_command(self) -> None:
        self.query_one(CommandInputPanel).focus_input()

    @work
    async def action_do_refresh(self) -> None:
        await self._run_command_line("/refresh")

    @on(DatabasePanel.DatabaseSelected)
    def handle_database_selected(self, event: DatabasePanel.DatabaseSelected) -> None:
        self._open_database(event.path)

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

    async def _run_command_line(self, line: str) -> None:
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
        self.query_one(DatabasePanel).set_recent_paths(self.recent_dbs.add(path))
        self.query_one(ResultsPanel).clear()
        self.query_one(CommandInputPanel).set_status(path, None)
        self._refresh_table_list()
        return True

    def _refresh_table_list(self) -> None:
        try:
            names = db.list_tables(self.state.connection)
        except CommandError as e:
            self.query_one(ResultsPanel).show_result(cmdresults.error(str(e)))
            return
        self.query_one(TableListPanel).set_tables(names)
