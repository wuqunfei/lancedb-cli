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


def test_get_embedding_function_wraps_backend_errors(monkeypatch):
    import lancedb.embeddings

    def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(lancedb.embeddings, "get_registry", boom)
    db.get_embedding_function.cache_clear()
    with pytest.raises(CommandError, match="Could not load embedding model"):
        db.get_embedding_function("some/model")
    db.get_embedding_function.cache_clear()
