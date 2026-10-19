"""Tests for the command dispatcher (prepare/execute) against a real LanceDB database."""

from pathlib import Path

import pytest

from lancedbx.commands import registry
from lancedbx.commands.results import AppState, CommandResult, PreparedCommand
from lancedbx.core import db

SAMPLE_CSV = Path(__file__).parent.parent / "test_data" / "sample.csv"


@pytest.fixture
def state(tmp_path):
    conn = db.connect(str(tmp_path / "mydb.lance"))
    db.load_csv(conn, str(SAMPLE_CSV), "people")
    return AppState(connection=conn, current_db_path=str(tmp_path / "mydb.lance"), current_table="people")


def run(state, line):
    prepared = registry.prepare(state, line)
    assert isinstance(prepared, PreparedCommand), f"expected PreparedCommand, got {prepared!r}"
    return registry.execute(prepared)


def test_blank_line_returns_none(state):
    assert registry.prepare(state, "   ") is None


def test_unknown_command_is_an_error(state):
    result = registry.prepare(state, "/nope")
    assert isinstance(result, CommandResult)
    assert result.kind == "error"


def test_no_database_open_is_an_error():
    state = AppState()
    result = registry.prepare(state, "/schema")
    assert result.kind == "error"


def test_table_commands_require_current_table(state):
    state.current_table = None
    result = registry.prepare(state, "/schema")
    assert result.kind == "error"
    assert "No table selected" in str(result.renderable)


def test_sql_does_not_require_current_table(state):
    state.current_table = None
    result = run(state, "/sql SELECT count(*) AS n FROM people")
    assert result.kind == "dataframe"
    assert result.dataframe["n"].iloc[0] == 10


def test_query_returns_dataframe(state):
    result = run(state, "/query --limit 3")
    assert result.kind == "dataframe"
    assert len(result.dataframe) == 3


def test_query_json_output_is_text(state):
    result = run(state, "/query --limit 2 --output json")
    assert result.kind == "text"


def test_schema_returns_text(state):
    result = run(state, "/schema")
    assert result.kind == "text"


def test_delete_is_destructive_and_requires_confirmation(state):
    prepared = registry.prepare(state, "/delete --where 'age > 40'")
    assert isinstance(prepared, PreparedCommand)
    assert prepared.confirm_message is not None
    assert "people" in prepared.confirm_message


def test_empty_is_destructive(state):
    prepared = registry.prepare(state, "/empty")
    assert prepared.confirm_message is not None


def test_drop_is_destructive(state):
    prepared = registry.prepare(state, "/drop")
    assert prepared.confirm_message is not None


def test_query_is_not_destructive(state):
    prepared = registry.prepare(state, "/query")
    assert prepared.confirm_message is None


def test_drop_execute_removes_table_and_flags_refresh(state):
    prepared = registry.prepare(state, "/drop")
    result = registry.execute(prepared)
    assert result.kind == "text"
    assert result.refresh_tables is True
    assert db.list_tables(state.connection) == []


def test_load_does_not_require_current_table(state):
    state.current_table = None
    result = run(state, f"/load --path {SAMPLE_CSV} --table people2")
    assert result.kind == "text"
    assert result.refresh_tables is True
    assert "people2" in db.list_tables(state.connection)


def test_update_and_requery(state):
    run(state, "/update --set-clause \"city='Remote'\" --where \"name = 'Alice Johnson'\"")
    result = run(state, "/query --where \"name = 'Alice Johnson'\"")
    assert result.dataframe["city"].iloc[0] == "Remote"


def test_dump_writes_file(state, tmp_path):
    out = tmp_path / "out.csv"
    result = run(state, f"/dump --path {out}")
    assert out.exists()
    assert result.kind == "text"


def test_exit_returns_exit_kind(state):
    result = run(state, "/exit")
    assert result.kind == "exit"


def test_refresh_flags_table_refresh(state):
    result = run(state, "/refresh")
    assert result.refresh_tables is True


def test_bad_flag_value_is_an_error_not_a_crash(state):
    result = registry.prepare(state, "/query --output xml")
    assert result.kind == "error"
