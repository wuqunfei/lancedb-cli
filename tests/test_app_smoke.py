"""Headless Pilot-driven smoke tests for the Textual app."""

from pathlib import Path

import pytest

from lancedb_cli import persistence
from lancedb_cli.core import db
from lancedb_cli.tui.app import LanceDBApp
from lancedb_cli.tui.widgets.command_input_panel import CommandInputPanel, HistoryInput
from lancedb_cli.tui.widgets.database_panel import DatabasePanel
from lancedb_cli.tui.widgets.results_panel import ResultsDataTable, ResultsPanel
from lancedb_cli.tui.widgets.table_list_panel import TableListPanel

SAMPLE_CSV = Path(__file__).parent.parent / "test_data" / "sample.csv"


async def type_and_submit(pilot, selector, text):
    """Click the input, clear any pre-filled text (e.g. the auto-query a table click
    leaves behind), then type `text` and submit it."""
    await pilot.click(selector)
    pilot.app.query_one(selector).value = ""
    for ch in text:
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


def make_app(tmp_path, initial_db_path=None):
    """Build a LanceDBApp with persistence isolated to tmp_path, never touching the
    user's real ~/.config/lancedb-cli/."""
    return LanceDBApp(
        initial_db_path=initial_db_path,
        recent_databases=persistence.RecentDatabases(path=tmp_path / "recent.json"),
        command_history=persistence.CommandHistory(path=tmp_path / "history.json"),
    )


@pytest.fixture
def db_with_table(tmp_path):
    db_path = tmp_path / "mydb.lance"
    conn = db.connect(str(db_path))
    db.load_csv(conn, str(SAMPLE_CSV), "people")
    return str(db_path)


async def test_all_four_panels_render_on_launch(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        assert app.query_one(DatabasePanel)
        assert app.query_one(TableListPanel)
        assert app.query_one(CommandInputPanel)
        assert app.query_one(ResultsPanel)


async def test_create_command_opens_database_and_populates_table_list(tmp_path, db_with_table):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await type_and_submit(pilot, "#command-input", f"/create --path {db_with_table}")
        assert app.state.current_db_path == db_with_table
        names = [item.table_name for item in app.query_one(TableListPanel).query("ListItem")]
        assert names == ["people"]


async def test_clicking_recent_database_reopens_it(tmp_path, db_with_table):
    other_db = tmp_path / "other.lance"

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Recent list is most-recent-first: after opening these two in order, row 0 is
        # other_db and row 1 is db_with_table.
        await type_and_submit(pilot, "#command-input", f"/create --path {db_with_table}")
        await type_and_submit(pilot, "#command-input", f"/create --path {other_db}")
        assert app.state.current_db_path == str(other_db)

        await pilot.click("#recent-db-list", offset=(2, 1))
        await pilot.pause()
        assert app.state.current_db_path == db_with_table


async def test_browse_button_opens_and_cancel_closes_modal(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.click("#browse-db-button")
        await pilot.pause()
        assert len(app.screen_stack) == 2
        await pilot.click("#browser-cancel")
        await pilot.pause()
        assert len(app.screen_stack) == 1
        assert app.state.current_db_path is None


async def test_directory_browser_modal_open_returns_start_path(tmp_path, db_with_table):
    from textual.app import App

    from lancedb_cli.tui.widgets.directory_browser_modal import DirectoryBrowserModal

    from textual import work

    class ModalHostApp(App):
        result = "unset"

        @work
        async def on_mount(self) -> None:
            self.result = await self.push_screen_wait(DirectoryBrowserModal(start_path=db_with_table))
            self.exit()

    app = ModalHostApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#browser-open")
        await pilot.pause()
    assert Path(app.result).resolve() == Path(db_with_table).resolve()


async def test_selecting_table_sets_current_table(tmp_path, db_with_table):
    app = make_app(tmp_path, initial_db_path=db_with_table)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#table-list ListItem")
        await pilot.pause()
        assert app.state.current_table == "people"


async def test_schema_renders_with_table_selected(tmp_path, db_with_table):
    app = make_app(tmp_path, initial_db_path=db_with_table)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#table-list ListItem")
        await pilot.pause()
        await type_and_submit(pilot, "#command-input", "/schema")
        text = str(app.query_one("#results-static").render())
        assert "people" in text
        assert "age" in text


async def test_sql_works_with_no_table_selected(tmp_path, db_with_table):
    app = make_app(tmp_path, initial_db_path=db_with_table)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.state.current_table is None
        await type_and_submit(pilot, "#command-input", "/sql SELECT count(*) AS n FROM people")
        table = app.query_one("#results-table")
        assert table.display is True
        assert table.row_count == 1


async def test_drop_cancel_keeps_table(tmp_path, db_with_table):
    app = make_app(tmp_path, initial_db_path=db_with_table)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#table-list ListItem")
        await pilot.pause()
        await type_and_submit(pilot, "#command-input", "/drop")
        assert len(app.screen_stack) == 2
        await pilot.click("#confirm-no")
        await pilot.pause()
        assert len(app.screen_stack) == 1
        names = [item.table_name for item in app.query_one(TableListPanel).query("ListItem")]
        assert names == ["people"]


async def test_drop_confirm_removes_table(tmp_path, db_with_table):
    app = make_app(tmp_path, initial_db_path=db_with_table)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#table-list ListItem")
        await pilot.pause()
        await type_and_submit(pilot, "#command-input", "/drop")
        await pilot.click("#confirm-yes")
        await pilot.pause()
        names = [item.table_name for item in app.query_one(TableListPanel).query("ListItem")]
        assert names == []


async def test_exit_ends_the_app(tmp_path, db_with_table):
    app = make_app(tmp_path, initial_db_path=db_with_table)
    async with app.run_test() as pilot:
        await pilot.pause()
        await type_and_submit(pilot, "#command-input", "/exit")
        assert app.is_running is False


async def test_results_pagination(tmp_path):
    import pandas as pd

    from lancedb_cli.core import db as core_db
    from textual.widgets import Button, DataTable, Static

    db_path = tmp_path / "bigdb.lance"
    conn = core_db.connect(str(db_path))
    conn.create_table("big", data=pd.DataFrame({"id": range(250), "val": [f"r{i}" for i in range(250)]}))

    app = make_app(tmp_path, initial_db_path=str(db_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#table-list ListItem")
        await pilot.pause()
        await type_and_submit(pilot, "#command-input", "/query --limit 250")

        table = app.query_one("#results-table", DataTable)
        label = app.query_one("#pagination-label", Static)
        prev_btn = app.query_one("#prev-page-button", Button)
        next_btn = app.query_one("#next-page-button", Button)

        assert table.row_count == 100
        assert "Page 1/3" in str(label.render())
        assert prev_btn.disabled is True
        assert next_btn.disabled is False

        await pilot.click("#next-page-button")
        await pilot.pause(0.2)
        assert table.row_count == 100
        assert "Page 2/3" in str(label.render())
        assert prev_btn.disabled is False
        assert next_btn.disabled is False

        await pilot.click("#next-page-button")
        await pilot.pause(0.2)
        assert table.row_count == 50
        assert "Page 3/3" in str(label.render())
        assert next_btn.disabled is True

        # next is disabled on the last page; clicking it must be a no-op
        await pilot.click("#next-page-button")
        await pilot.pause(0.2)
        assert table.row_count == 50

        await pilot.click("#prev-page-button")
        await pilot.pause(0.2)
        assert table.row_count == 100
        assert "Page 2/3" in str(label.render())


async def test_double_click_cell_shows_full_value(tmp_path):
    import pandas as pd

    from lancedb_cli.core import db as core_db

    db_path = tmp_path / "longdb.lance"
    conn = core_db.connect(str(db_path))
    long_text = "X" * 200
    conn.create_table("t", data=pd.DataFrame({"id": [1, 2], "notes": [long_text, "short"]}))

    app = make_app(tmp_path, initial_db_path=str(db_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#table-list ListItem")
        await pilot.pause(0.2)

        table = app.query_one("#results-table", ResultsDataTable)
        # Click inside the "notes" column — it's the second column, so its content
        # starts right after the "id" column's rendered width.
        notes_x = table.ordered_columns[0].width + 3
        await pilot.click("#results-table", offset=(notes_x, 1), times=2)
        await pilot.pause(0.2)

        assert len(app.screen_stack) == 2
        title = str(app.screen.query_one("#cell-detail-title").render())
        value = str(app.screen.query_one("#cell-detail-value").render())
        assert "notes" in title
        assert value == long_text

        await pilot.click("#cell-detail-close")
        await pilot.pause()
        assert len(app.screen_stack) == 1


async def test_slash_command_autosuggestion(tmp_path):
    from textual.widgets import OptionList

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        suggestions = app.query_one("#command-suggestions", OptionList)
        command_input = app.query_one("#command-input", HistoryInput)

        await pilot.click("#command-input")
        await pilot.press("/", "d")
        await pilot.pause()
        assert suggestions.display is True
        assert {suggestions.get_option_at_index(i).id for i in range(suggestions.option_count)} == {
            "delete",
            "drop",
            "dump",
        }

        await pilot.press("down")
        await pilot.pause()
        assert suggestions.get_option_at_index(suggestions.highlighted).id == "drop"

        await pilot.press("tab")
        await pilot.pause()
        assert command_input.value == "/drop "
        assert suggestions.display is False

        # typing a full, exact command name should hide suggestions so Enter submits
        # the command instead of being swallowed as "accept suggestion"
        command_input.value = ""
        await pilot.press(*"/exit")
        await pilot.pause()
        assert suggestions.display is False


async def test_slash_command_suggestion_escape_dismisses_without_clearing(tmp_path):
    from textual.widgets import OptionList

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        suggestions = app.query_one("#command-suggestions", OptionList)
        command_input = app.query_one("#command-input", HistoryInput)

        await pilot.click("#command-input")
        await pilot.press(*"/q")
        await pilot.pause()
        assert suggestions.display is True

        await pilot.press("escape")
        await pilot.pause()
        assert suggestions.display is False
        assert command_input.value == "/q"


async def test_command_history_recall(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await type_and_submit(pilot, "#command-input", "/nope-one")
        await type_and_submit(pilot, "#command-input", "/nope-two")
        await pilot.click("#command-input")
        await pilot.press("up")
        history_input = app.query_one("#command-input", HistoryInput)
        assert history_input.value == "/nope-two"
        await pilot.press("up")
        assert history_input.value == "/nope-one"
