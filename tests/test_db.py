"""Tests for lsql.core.db against a real throwaway LanceDB directory."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lsql.core import db
from lsql.core.exceptions import CommandError

SAMPLE_CSV = Path(__file__).parent.parent / "test_data" / "sample.csv"


@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "mydb.lance"))


@pytest.fixture
def people(conn):
    db.load_csv(conn, str(SAMPLE_CSV), "people")
    return conn


def test_connect_creates_empty_database(conn):
    assert db.list_tables(conn) == []


def test_load_csv_creates_table(people):
    assert db.list_tables(people) == ["people"]


def test_load_csv_missing_file_raises(conn):
    with pytest.raises(CommandError, match="not found"):
        db.load_csv(conn, "/no/such/file.csv", "people")


def test_load_csv_existing_table_without_overwrite_raises(people):
    with pytest.raises(CommandError, match="already exists"):
        db.load_csv(people, str(SAMPLE_CSV), "people")


def test_load_csv_with_overwrite_replaces_table(people):
    df = db.load_csv(people, str(SAMPLE_CSV), "people", overwrite=True)
    assert len(df) == 10
    assert db.list_tables(people) == ["people"]


def test_open_table_missing_raises(conn):
    with pytest.raises(CommandError, match="not found"):
        db.open_table(conn, "nope")


def test_get_schema(people):
    schema = db.get_schema(people, "people")
    assert "name" in schema.names


def test_query_table_defaults(people):
    result = db.query_table(people, "people")
    assert len(result) == 10


def test_query_table_limit(people):
    result = db.query_table(people, "people", limit=3)
    assert len(result) == 3


def test_query_table_where(people):
    result = db.query_table(people, "people", where="age > 40")
    assert set(result["name"]) == {"David Brown", "Henry Wilson"}


def test_query_table_select(people):
    result = db.query_table(people, "people", select="name, age")
    assert list(result.columns) == ["name", "age"]


def test_apply_select_filters_and_strips_whitespace():
    import pandas as pd

    df = pd.DataFrame({"name": ["a"], "age": [1], "city": ["x"]})
    result = db._apply_select(df, "name, age")
    assert list(result.columns) == ["name", "age"]


def test_apply_select_drops_unknown_columns():
    import pandas as pd

    df = pd.DataFrame({"name": ["a"]})
    result = db._apply_select(df, "name,nope")
    assert list(result.columns) == ["name"]


def test_apply_select_none_returns_unchanged():
    import pandas as pd

    df = pd.DataFrame({"name": ["a"], "age": [1]})
    result = db._apply_select(df, None)
    assert list(result.columns) == ["name", "age"]


def test_run_sql_across_tables(people):
    db.load_csv(people, str(SAMPLE_CSV), "people_copy")
    result = db.run_sql(people, "SELECT count(*) AS n FROM people")
    assert result["n"].iloc[0] == 10
    joined = db.run_sql(people, "SELECT count(*) AS n FROM people p JOIN people_copy c ON p.id = c.id")
    assert joined["n"].iloc[0] == 10


def test_delete_rows(people):
    deleted = db.delete_rows(people, "people", "age > 40")
    assert deleted == 2
    assert db.query_table(people, "people", limit=100).shape[0] == 8


def test_empty_table(people):
    deleted = db.empty_table(people, "people")
    assert deleted == 10
    assert db.query_table(people, "people", limit=100).shape[0] == 0


def test_drop_table(people):
    db.drop_table(people, "people")
    assert db.list_tables(people) == []


def test_drop_missing_table_raises(conn):
    with pytest.raises(CommandError, match="not found"):
        db.drop_table(conn, "nope")


def test_update_rows(people):
    db.update_rows(people, "people", {"city": "Remote"}, "name = 'Alice Johnson'")
    result = db.query_table(people, "people", where="name = 'Alice Johnson'")
    assert result["city"].iloc[0] == "Remote"


def test_dump_csv(people, tmp_path):
    out = tmp_path / "out.csv"
    df = db.dump_csv(people, "people", str(out))
    assert out.exists()
    assert len(df) == 10
    reloaded = pd.read_csv(out)
    assert len(reloaded) == 10


def test_dump_csv_existing_without_overwrite_raises(people, tmp_path):
    out = tmp_path / "out.csv"
    out.write_text("x")
    with pytest.raises(CommandError, match="already exists"):
        db.dump_csv(people, "people", str(out))


def test_build_row_where_clause_quotes_strings_and_leaves_numbers_bare():
    clause = db.build_row_where_clause({"id": 1, "name": "O'Brien", "active": True, "note": None})
    assert clause == "id = 1 AND name = 'O''Brien' AND active = TRUE AND note IS NULL"


def test_build_row_where_clause_raises_on_empty_row():
    with pytest.raises(CommandError, match="no other columns"):
        db.build_row_where_clause({})


def test_build_row_where_clause_skips_vector_columns():
    # Regression test: a vector/embedding column's value is a multi-element array,
    # which can't be expressed as a single SQL equality literal. Including it used to
    # crash with "ValueError: can only convert an array of size 1 to a Python scalar".
    row = {"id": 1, "embedding": np.array([0.1, 0.2, 0.3]), "name": "O'Brien"}
    clause = db.build_row_where_clause(row)
    assert clause == "id = 1 AND name = 'O''Brien'"
    assert "embedding" not in clause


def test_build_row_where_clause_handles_numpy_scalars_from_a_real_dataframe(people):
    # Regression test: numpy.int64/float64/bool_ from df.iloc[...] are not instances of
    # Python's int/float, so a naive isinstance check would wrongly quote them as strings
    # (e.g. "id = '1'"), which lancedb's strict filter engine rejects against an Int64 column.
    row = db.query_table(people, "people", where="id = 1").iloc[0]
    where_row = {col: val for col, val in row.items() if col != "city"}
    clause = db.build_row_where_clause(where_row)
    assert "id = 1" in clause
    assert "id = '1'" not in clause

    # And it must actually work against the real table, not just look right as a string.
    db.update_rows(people, "people", {"name": "Updated Name"}, clause)
    result = db.query_table(people, "people", where="id = 1")
    assert result["name"].iloc[0] == "Updated Name"


class _FakeEmbeddingFunction:
    """Deterministic 4-dim stand-in for a real sentence-transformers model, so these
    tests never hit the network or download hundreds of MB of torch weights."""

    def generate_embeddings(self, texts):
        return [[float(len(t)), 0.0, 0.0, 0.0] for t in texts]


@pytest.fixture
def fake_embedding(monkeypatch):
    monkeypatch.setattr(db, "get_embedding_function", lambda name: _FakeEmbeddingFunction())


def test_embed_table_single_column_defaults_name(people, fake_embedding):
    df = db.embed_table(people, "people", ["name"], ["vector"])
    assert "vector" in df.columns
    assert len(df["vector"].iloc[0]) == 4

    schema_names = db.get_schema(people, "people").names
    assert "vector" in schema_names


def test_embed_table_multi_column_writes_both_targets(people, fake_embedding):
    df = db.embed_table(people, "people", ["name", "city"], ["name_vector", "city_vector"])
    assert "name_vector" in df.columns
    assert "city_vector" in df.columns


def test_embed_table_missing_source_column_raises(people, fake_embedding):
    with pytest.raises(CommandError, match="not found"):
        db.embed_table(people, "people", ["nope"], ["vector"])


def test_embed_table_existing_target_without_overwrite_raises(people, fake_embedding):
    db.embed_table(people, "people", ["name"], ["vector"])
    with pytest.raises(CommandError, match="already exist"):
        db.embed_table(people, "people", ["city"], ["vector"])


def test_embed_table_existing_target_with_overwrite_replaces(people, fake_embedding):
    db.embed_table(people, "people", ["name"], ["vector"])
    df = db.embed_table(people, "people", ["city"], ["vector"], overwrite=True)
    assert "vector" in df.columns


def test_embed_table_mismatched_column_counts_raises(people, fake_embedding):
    with pytest.raises(CommandError, match="must pair up one-to-one"):
        db.embed_table(people, "people", ["name", "city"], ["vector"])


def test_embed_table_target_colliding_with_later_source_does_not_corrupt_it(people, monkeypatch):
    # Regression test: when an earlier pair's target column name equals a later pair's
    # source column name, the later pair must still embed the ORIGINAL text — not the
    # vector that was just written into that column by the earlier pair.
    calls = []

    class RecordingEmbed:
        def generate_embeddings(self, texts):
            calls.append(list(texts))
            return [[float(len(t)), 0.0] for t in texts]

    monkeypatch.setattr(db, "get_embedding_function", lambda name: RecordingEmbed())

    original_names = sorted(db.query_table(people, "people", limit=1000)["name"].tolist())

    db.embed_table(people, "people", ["city", "name"], ["name", "final"], overwrite=True)

    assert len(calls) == 2
    second_call_texts = sorted(calls[1])
    assert second_call_texts == original_names
    assert not any(text.startswith("[") for text in second_call_texts)


def test_get_embedding_function_wraps_backend_errors(monkeypatch):
    import lancedb.embeddings

    def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(lancedb.embeddings, "get_registry", boom)
    db.get_embedding_function.cache_clear()
    with pytest.raises(CommandError, match="Could not load embedding model"):
        db.get_embedding_function("some/model")
    db.get_embedding_function.cache_clear()


def test_get_embedding_function_disables_tqdm_multiprocessing_lock(monkeypatch):
    # Regression test: loading a real model triggers a tqdm progress bar
    # ("Loading weights"), whose TqdmDefaultWriteLock.create_mp_lock() calls
    # multiprocessing.RLock() to coordinate output across forked processes. Inside a
    # running Textual app (raw-mode pty, unusual fd layout), registering that lock
    # spawns Python's resource_tracker subprocess, which can fail with
    # "ValueError: bad value(s) in fds_to_keep" — crashing /embedding entirely, even
    # though we never fork our own child processes and have no use for a
    # multiprocessing-safe tqdm lock in the first place. Pre-setting mp_lock skips
    # multiprocessing.RLock() construction entirely (create_mp_lock no-ops once the
    # class attribute already exists).
    import lancedb.embeddings
    import tqdm.std

    if hasattr(tqdm.std.TqdmDefaultWriteLock, "mp_lock"):
        monkeypatch.delattr(tqdm.std.TqdmDefaultWriteLock, "mp_lock")

    class _FakeEmbed:
        def generate_embeddings(self, texts):
            return [[0.0] for _ in texts]

    monkeypatch.setattr(
        lancedb.embeddings,
        "get_registry",
        lambda: type(
            "Registry", (), {"get": lambda self, name: type("Fn", (), {"create": lambda self, **kw: _FakeEmbed()})()}
        )(),
    )
    db.get_embedding_function.cache_clear()
    db.get_embedding_function("some/model")
    db.get_embedding_function.cache_clear()

    assert tqdm.std.TqdmDefaultWriteLock.mp_lock is None


def test_has_fts_index_false_before_creation(people):
    tbl = db.open_table(people, "people")
    assert db.has_fts_index(tbl, "city") is False


def test_create_fts_index_then_has_fts_index_true(people):
    db.create_fts_index(people, "people", "city")
    tbl = db.open_table(people, "people")
    assert db.has_fts_index(tbl, "city") is True


def test_create_fts_index_missing_column_raises(people):
    with pytest.raises(CommandError, match="not found"):
        db.create_fts_index(people, "people", "nope")


def test_search_vector_mode_returns_closest_row(people, fake_embedding):
    # _FakeEmbeddingFunction embeds any text as [len(text), 0, 0, 0] — query with text
    # of the same length as a target row's "name" to get an (almost) exact vector match.
    db.embed_table(people, "people", ["name"], ["vector"])
    target_name = db.query_table(people, "people", limit=1)["name"].iloc[0]
    result = db.search_table(people, "people", mode="vector", query="x" * len(target_name), limit=1)
    assert len(result) == 1
    assert result["name"].iloc[0] == target_name


def test_search_vector_mode_infers_single_vector_column(people, fake_embedding):
    db.embed_table(people, "people", ["name"], ["vector"])
    # No --vector-column given — only one vector column exists, so it's auto-inferred.
    result = db.search_table(people, "people", mode="vector", query="hello", limit=3)
    assert len(result) == 3


def test_search_vector_mode_ambiguous_without_explicit_column_raises(people, fake_embedding):
    db.embed_table(people, "people", ["name", "city"], ["name_vector", "city_vector"])
    with pytest.raises(CommandError, match="Multiple vector columns"):
        db.search_table(people, "people", mode="vector", query="hello", limit=3)


def test_search_vector_mode_with_explicit_column_resolves_ambiguity(people, fake_embedding):
    db.embed_table(people, "people", ["name", "city"], ["name_vector", "city_vector"])
    result = db.search_table(
        people, "people", mode="vector", query="hello", vector_column="city_vector", limit=3
    )
    assert len(result) == 3


def test_search_vector_mode_unknown_explicit_column_raises(people, fake_embedding):
    db.embed_table(people, "people", ["name"], ["vector"])
    with pytest.raises(CommandError, match="not a vector column"):
        db.search_table(people, "people", mode="vector", query="hello", vector_column="nope")


def test_search_vector_mode_no_vector_columns_raises(people):
    with pytest.raises(CommandError, match="No vector columns"):
        db.search_table(people, "people", mode="vector", query="hello")


def test_search_fts_mode_auto_creates_index_and_returns_results(people):
    tbl = db.open_table(people, "people")
    assert db.has_fts_index(tbl, "city") is False
    result = db.search_table(people, "people", mode="fts", query="New York", text_column="city", limit=5)
    assert len(result) >= 1
    tbl = db.open_table(people, "people")
    assert db.has_fts_index(tbl, "city") is True


def test_search_fts_mode_reuses_existing_index(people, monkeypatch):
    db.create_fts_index(people, "people", "city")
    calls = []
    original = db.create_fts_index

    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "create_fts_index", spy)
    db.search_table(people, "people", mode="fts", query="New York", text_column="city", limit=5)
    assert calls == []  # index already existed — must not be rebuilt


def test_search_fts_mode_requires_text_column(people):
    with pytest.raises(CommandError, match="--text-column"):
        db.search_table(people, "people", mode="fts", query="New York")


def test_search_hybrid_mode_requires_text_column(people, fake_embedding):
    db.embed_table(people, "people", ["name"], ["vector"])
    with pytest.raises(CommandError, match="--text-column"):
        db.search_table(people, "people", mode="hybrid", query="New York")


def test_search_hybrid_mode_validates_text_column_before_embedding(people, monkeypatch):
    # Regression test: --text-column's presence/existence must be checked BEFORE the
    # (expensive, first-use-downloads-a-model) query embedding happens — a missing
    # --text-column is a cheap, instant mistake that shouldn't cost a model load.
    db.embed_table(people, "people", ["name"], ["vector"])
    calls = []
    monkeypatch.setattr(db, "get_embedding_function", lambda name: calls.append(name))

    with pytest.raises(CommandError, match="--text-column"):
        db.search_table(people, "people", mode="hybrid", query="New York")
    assert calls == []

    with pytest.raises(CommandError, match="not found"):
        db.search_table(people, "people", mode="hybrid", query="New York", text_column="nope")
    assert calls == []


def test_search_hybrid_mode_returns_results(people, fake_embedding):
    db.embed_table(people, "people", ["name"], ["vector"])
    result = db.search_table(
        people, "people", mode="hybrid", query="New York", text_column="city", limit=5
    )
    assert len(result) >= 1
    assert "_relevance_score" in result.columns


def test_search_unknown_mode_raises(people):
    with pytest.raises(CommandError, match="Unknown search mode"):
        db.search_table(people, "people", mode="nope", query="x")


def test_search_applies_select(people, fake_embedding):
    db.embed_table(people, "people", ["name"], ["vector"])
    result = db.search_table(people, "people", mode="vector", query="hello", select="name", limit=3)
    assert list(result.columns) == ["name"]
