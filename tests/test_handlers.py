"""Tests for the command dispatcher (prepare/execute) against a real LanceDB database."""

from pathlib import Path

import pytest

from lsql.commands import registry
from lsql.commands.results import AppState, CommandResult, PreparedCommand
from lsql.core import db

SAMPLE_CSV = Path(__file__).parent.parent / "test_data" / "sample.csv"


@pytest.fixture
def state(tmp_path):
    conn = db.connect(str(tmp_path / "mydb.lance"))
    db.load_csv(conn, str(SAMPLE_CSV), "people")
    return AppState(connection=conn, current_db_path=str(tmp_path / "mydb.lance"), current_table="people")


@pytest.fixture
def fake_embedding(monkeypatch):
    """Records every model name requested and returns a deterministic 2-dim stand-in,
    so these tests never download a real model."""
    calls = []

    class _FakeEmbed:
        def generate_embeddings(self, texts):
            return [[float(len(t)), 0.0] for t in texts]

    def fake_get(name):
        calls.append(name)
        return _FakeEmbed()

    monkeypatch.setattr(db, "get_embedding_function", fake_get)
    return calls


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


def test_embedding_does_not_require_current_table(state, fake_embedding):
    state.current_table = None
    result = run(state, "/embedding --table people --source name")
    assert result.kind == "text"
    assert result.refresh_tables is True
    assert "vector" in db.get_schema(state.connection, "people").names


def test_embedding_is_marked_slow(state, fake_embedding):
    prepared = registry.prepare(state, "/embedding --table people --source name")
    assert isinstance(prepared, PreparedCommand)
    assert prepared.slow is True


def test_drop_is_not_marked_slow(state):
    prepared = registry.prepare(state, "/drop")
    assert prepared.slow is False


def test_embedding_is_destructive_and_confirm_message_names_table(state, fake_embedding):
    prepared = registry.prepare(state, "/embedding --table people --source name")
    assert isinstance(prepared, PreparedCommand)
    assert prepared.confirm_message is not None
    assert "people" in prepared.confirm_message


def test_embedding_confirm_message_never_shows_none_for_omitted_target(state, fake_embedding):
    # Regression test: --target is omitted here, so args.target is None. The confirm
    # message must not literally say "None" — it can't yet know the resolved default
    # ("vector"), since that's computed by parse_embedding_columns inside the handler,
    # after confirmation — so it must not promise a target name it can't back up.
    prepared = registry.prepare(state, "/embedding --table people --source name")
    assert "None" not in prepared.confirm_message


def test_embedding_uses_explicit_model_flag(state, fake_embedding):
    run(state, "/embedding --table people --source name --model org/explicit-model")
    assert fake_embedding == ["org/explicit-model"]


def test_embedding_uses_state_model_when_no_flag(state, fake_embedding):
    state.current_embedding_model = "org/panel-model"
    run(state, "/embedding --table people --source name")
    assert fake_embedding == ["org/panel-model"]


def test_embedding_falls_back_to_default_model(state, fake_embedding):
    run(state, "/embedding --table people --source name")
    assert fake_embedding == [db.DEFAULT_EMBEDDING_MODEL]


def test_embedding_multi_column(state, fake_embedding):
    result = run(state, "/embedding --table people --source name,city")
    assert result.kind == "text"
    names = db.get_schema(state.connection, "people").names
    assert "name_vector" in names
    assert "city_vector" in names
