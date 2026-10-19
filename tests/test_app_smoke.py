"""Headless Pilot-driven smoke tests for the Textual app."""

from pathlib import Path

import pytest

from lsql import persistence
from lsql.core import db
from lsql.tui.app import LanceDBApp
from lsql.tui.widgets.command_input_panel import CommandInputPanel, HistoryInput
from lsql.tui.widgets.database_panel import DatabasePanel
from lsql.tui.widgets.embedding_model_panel import EmbeddingModelPanel
from lsql.tui.widgets.results_panel import ResultsDataTable, ResultsPanel
from lsql.tui.widgets.table_list_panel import TableListPanel

SAMPLE_CSV = Path(__file__).parent.parent / "test_data" / "sample.csv"

# Standalone host apps below (for testing a single modal/widget in isolation) don't get
# LanceDBApp's CSS_PATH for free, so without this they'd render with Textual's default
# styling instead of app.tcss — which can overflow the test terminal in ways the real
# app never would.
import lsql.tui.app as _app_module  # noqa: E402

APP_TCSS = str(Path(_app_module.__file__).parent / "app.tcss")


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
    user's real ~/.config/lsql/."""
    return LanceDBApp(
        initial_db_path=initial_db_path,
        recent_databases=persistence.RecentDatabases(path=tmp_path / "recent.json"),
        command_history=persistence.CommandHistory(path=tmp_path / "history.json"),
        last_embedding_model=persistence.LastEmbeddingModel(path=tmp_path / "last_model.json"),
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


async def test_embedding_model_panel_renders(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        assert app.query_one(EmbeddingModelPanel)


async def test_last_embedding_model_prefills_without_loading(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(db, "get_embedding_function", lambda name: calls.append(name))

    persistence.LastEmbeddingModel(path=tmp_path / "last_model.json").set("org/saved-model")

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        assert app.state.current_embedding_model == "org/saved-model"
        assert app.query_one("#embedding-model-input").value == "org/saved-model"
    assert calls == []


async def test_setting_embedding_model_updates_state_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "get_embedding_function", lambda name: object())

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        app.query_one("#embedding-model-input").value = "org/new-model"
        await pilot.click("#set-embedding-button")
        await _wait_until(lambda: app.state.current_embedding_model is not None, pilot)
        assert app.state.current_embedding_model == "org/new-model"
        assert app.query_one("#embedding-model-input").value == "org/new-model"

    assert persistence.LastEmbeddingModel(path=tmp_path / "last_model.json").load() == "org/new-model"


async def test_cancelling_embedding_modal_leaves_state_unset(tmp_path, monkeypatch):
    import threading

    never_set = threading.Event()

    def blocking_get(name):
        never_set.wait(timeout=5)
        return object()

    monkeypatch.setattr(db, "get_embedding_function", blocking_get)

    app = make_app(tmp_path)
    try:
        async with app.run_test() as pilot:
            app.query_one("#embedding-model-input").value = "org/new-model"
            await pilot.click("#set-embedding-button")
            await _wait_until(lambda: app.screen.query("#embedding-modal-cancel"), pilot)
            await pilot.pause()
            await pilot.click("#embedding-modal-cancel")
            await pilot.pause()
            assert app.state.current_embedding_model is None
    finally:
        never_set.set()


async def test_table_list_scrolls_with_many_tables(tmp_path):
    import pandas as pd
    from textual.widgets import ListView

    from lsql.core import db as core_db

    db_path = tmp_path / "manytables.lance"
    conn = core_db.connect(str(db_path))
    for i in range(50):
        conn.create_table(f"table_{i:03d}", data=pd.DataFrame({"id": [1]}))

    app = make_app(tmp_path, initial_db_path=str(db_path))
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        list_view = app.query_one("#table-list", ListView)
        assert len(list_view.children) == 50
        # more rows than fit on screen -> scrolling is possible and reaches every item
        assert list_view.virtual_size.height > list_view.region.height
        list_view.scroll_end(animate=False)
        await pilot.pause()
        assert list_view.scroll_y == list_view.max_scroll_y > 0


async def test_theme_toggle_switches_theme_and_icon(tmp_path):
    from textual.widgets import Button

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        icon_button = app.query_one("#theme-toggle-button", Button)
        starting_theme = app.theme

        await pilot.click("#theme-toggle-button")
        await pilot.pause(0.3)
        assert app.theme != starting_theme
        assert str(icon_button.label) == ("🌙" if app.theme == "textual-dark" else "☀️")

        await pilot.click("#theme-toggle-button")
        await pilot.pause(0.3)
        assert app.theme == starting_theme


async def test_create_command_opens_database_and_populates_table_list(tmp_path, db_with_table):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await type_and_submit(pilot, "#command-input", f"/create --path {db_with_table}")
        assert app.state.current_db_path == db_with_table
        names = [item.table_name for item in app.query_one(TableListPanel).query("ListItem")]
        assert names == ["people"]


async def test_open_button_opens_and_cancel_closes_modal(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.click("#open-db-button")
        await pilot.pause()
        assert len(app.screen_stack) == 2
        await pilot.click("#browser-cancel")
        await pilot.pause()
        assert len(app.screen_stack) == 1
        assert app.state.current_db_path is None


async def test_submitting_typed_path_keeps_path_in_input(tmp_path, db_with_table):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await type_and_submit(pilot, "#db-path-input", db_with_table)
        assert app.state.current_db_path == db_with_table
        assert app.query_one("#db-path-input").value == db_with_table


async def test_opening_via_folder_browser_fills_in_input(tmp_path, db_with_table):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        # Pre-fill the path so the browser opens with db_with_table pre-selected,
        # then "Open" on the modal confirms that same path without navigating.
        app.query_one("#db-path-input").value = db_with_table
        await pilot.click("#open-db-button")
        await pilot.pause()
        await pilot.click("#browser-open")
        await pilot.pause()
        assert app.state.current_db_path == db_with_table
        assert app.query_one("#db-path-input").value == db_with_table


async def test_directory_browser_modal_open_returns_start_path(tmp_path, db_with_table):
    from textual.app import App

    from lsql.tui.widgets.directory_browser_modal import DirectoryBrowserModal

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


async def _wait_until(condition, pilot, attempts=20):
    """Poll `condition()` across event-loop pauses, since the download modal's
    @work(thread=True) load crosses a real thread boundary — a single pilot.pause()
    isn't guaranteed to observe the call_from_thread callback having landed yet."""
    for _ in range(attempts):
        if condition():
            return True
        await pilot.pause()
    return condition()


async def test_embedding_download_modal_success_dismisses_true(monkeypatch):
    from textual import work
    from textual.app import App

    from lsql.core import db
    from lsql.tui.widgets.embedding_model_download_modal import EmbeddingModelDownloadModal

    monkeypatch.setattr(db, "get_embedding_function", lambda name: object())

    class ModalHostApp(App):
        CSS_PATH = APP_TCSS
        result = "unset"

        @work
        async def on_mount(self) -> None:
            self.result = await self.push_screen_wait(EmbeddingModelDownloadModal("org/model"))

    app = ModalHostApp()
    async with app.run_test() as pilot:
        await _wait_until(lambda: app.result is not True, pilot)
        await _wait_until(lambda: app.result is True, pilot)
    assert app.result is True


async def test_embedding_download_modal_cancel_dismisses_false(monkeypatch):
    import threading

    from textual import work
    from textual.app import App

    from lsql.core import db
    from lsql.tui.widgets.embedding_model_download_modal import EmbeddingModelDownloadModal

    # Blocks until the test is done with it, so the worker thread can never race ahead
    # and dismiss(True) before the test gets a chance to click Cancel.
    never_set = threading.Event()

    def blocking_get(name):
        never_set.wait(timeout=5)
        return object()

    monkeypatch.setattr(db, "get_embedding_function", blocking_get)

    class ModalHostApp(App):
        CSS_PATH = APP_TCSS
        result = "unset"

        @work
        async def on_mount(self) -> None:
            self.result = await self.push_screen_wait(EmbeddingModelDownloadModal("org/model"))

    app = ModalHostApp()
    try:
        async with app.run_test() as pilot:
            await _wait_until(lambda: app.screen.query("#embedding-modal-cancel"), pilot)
            await pilot.pause()
            await pilot.click("#embedding-modal-cancel")
            await _wait_until(lambda: app.result is False, pilot)
        assert app.result is False
    finally:
        never_set.set()  # let the blocked worker thread return instead of waiting out its timeout


async def test_embedding_download_modal_failure_shows_retry_then_succeeds(monkeypatch):
    from textual import work
    from textual.app import App
    from textual.widgets import Button, Label, LoadingIndicator

    from lsql.core import db
    from lsql.core.exceptions import CommandError
    from lsql.tui.widgets.embedding_model_download_modal import EmbeddingModelDownloadModal

    attempts = {"count": 0}

    def flaky_get(name):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise CommandError("network down")
        return object()

    monkeypatch.setattr(db, "get_embedding_function", flaky_get)

    class ModalHostApp(App):
        CSS_PATH = APP_TCSS
        result = "unset"

        @work
        async def on_mount(self) -> None:
            self.result = await self.push_screen_wait(EmbeddingModelDownloadModal("org/model"))

    def retry_enabled():
        buttons = app.screen.query("#embedding-modal-retry")
        return bool(buttons) and not buttons.first(Button).disabled

    app = ModalHostApp()
    async with app.run_test() as pilot:
        await _wait_until(retry_enabled, pilot)
        assert "Failed" in str(app.screen.query_one("#embedding-modal-status", Label).render())
        assert app.screen.query_one("#embedding-modal-spinner", LoadingIndicator).display is False

        await pilot.click("#embedding-modal-retry")
        await _wait_until(lambda: app.result is True, pilot)
    assert app.result is True
    assert attempts["count"] == 2


async def test_embedding_model_panel_set_button_posts_model_selected(monkeypatch):
    from textual import work
    from textual.app import App

    from lsql.core import db
    from lsql.tui.widgets.embedding_model_panel import EmbeddingModelPanel

    monkeypatch.setattr(db, "get_embedding_function", lambda name: object())

    class PanelHostApp(App):
        CSS_PATH = APP_TCSS
        selected = None

        def compose(self):
            yield EmbeddingModelPanel(id="embedding-model-panel")

        def on_embedding_model_panel_model_selected(self, event):
            self.selected = event.name

    app = PanelHostApp()
    async with app.run_test() as pilot:
        app.query_one("#embedding-model-input").value = "org/panel-model"
        await pilot.click("#set-embedding-button")
        await _wait_until(lambda: app.selected is not None, pilot)
    assert app.selected == "org/panel-model"


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

    from lsql.core import db as core_db
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
    from textual.widgets import TextArea

    from lsql.core import db as core_db

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
        value_area = app.screen.query_one("#cell-detail-value", TextArea)
        assert "notes" in title
        assert value_area.text == long_text

        await pilot.click("#cell-detail-close")
        await pilot.pause()
        assert len(app.screen_stack) == 1


async def test_cell_detail_copy_button_copies_full_value(tmp_path):
    import pandas as pd

    from lsql.core import db as core_db

    db_path = tmp_path / "copydb.lance"
    conn = core_db.connect(str(db_path))
    long_text = "Y" * 150
    conn.create_table("t", data=pd.DataFrame({"id": [1], "notes": [long_text]}))

    app = make_app(tmp_path, initial_db_path=str(db_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#table-list ListItem")
        await pilot.pause(0.2)

        table = app.query_one("#results-table", ResultsDataTable)
        notes_x = table.ordered_columns[0].width + 3
        await pilot.click("#results-table", offset=(notes_x, 1), times=2)
        await pilot.pause(0.2)

        await pilot.click("#cell-detail-copy")
        await pilot.pause()
        assert app.clipboard == long_text


async def test_cell_detail_update_writes_new_value_and_refreshes(tmp_path):
    import pandas as pd
    from textual.widgets import TextArea

    from lsql.core import db as core_db

    db_path = tmp_path / "editdb.lance"
    conn = core_db.connect(str(db_path))
    conn.create_table("people", data=pd.DataFrame({"id": [1, 2], "city": ["NYC", "LA"]}))

    app = make_app(tmp_path, initial_db_path=str(db_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#table-list ListItem")
        await pilot.pause(0.2)

        table = app.query_one("#results-table", ResultsDataTable)
        city_x = table.ordered_columns[0].width + 3
        await pilot.click("#results-table", offset=(city_x, 1), times=2)  # row 0 = id 1, city NYC
        await pilot.pause(0.2)
        assert len(app.screen_stack) == 2

        app.screen.query_one("#cell-detail-value", TextArea).text = "Remote"
        await pilot.click("#cell-detail-update")
        await pilot.pause(0.3)

        assert len(app.screen_stack) == 1
        result = core_db.query_table(app.state.connection, "people", where="id = 1")
        assert result["city"].iloc[0] == "Remote"
        # row 2 (LA) must be untouched
        other = core_db.query_table(app.state.connection, "people", where="id = 2")
        assert other["city"].iloc[0] == "LA"


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
