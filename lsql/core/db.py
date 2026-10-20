"""lancedb/duckdb access layer. Raises CommandError on user-facing failures."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import lancedb
import numpy as np
import pandas as pd
import pyarrow as pa

from .exceptions import CommandError

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def connect(db_path: str) -> lancedb.DBConnection:
    """Connect to (and implicitly create, if missing) a LanceDB database directory."""
    try:
        return lancedb.connect(db_path)
    except Exception as e:
        raise CommandError(f"Could not open database at '{db_path}': {e}")


def list_tables(conn: lancedb.DBConnection) -> List[str]:
    """Return the sorted list of table names in a database."""
    result = conn.list_tables()
    names = result.tables if hasattr(result, "tables") else result
    return sorted(names)


def table_exists(conn: lancedb.DBConnection, table_name: str) -> bool:
    return table_name in list_tables(conn)


def open_table(conn: lancedb.DBConnection, table_name: str):
    """Open a table, raising CommandError if it doesn't exist."""
    if not table_exists(conn, table_name):
        raise CommandError(f"Table '{table_name}' not found in database")
    return conn.open_table(table_name)


def get_schema(conn: lancedb.DBConnection, table_name: str) -> Any:
    return open_table(conn, table_name).schema


def _apply_select(df: pd.DataFrame, select: Optional[str]) -> pd.DataFrame:
    """Narrow `df` to a comma-separated column list, silently dropping any names not
    present (shared by query_table and search_table)."""
    if not select:
        return df
    cols = [c.strip() for c in select.split(",")]
    return df[[c for c in cols if c in df.columns]]


def query_table(
    conn: lancedb.DBConnection,
    table_name: str,
    limit: int = 10,
    where: Optional[str] = None,
    select: Optional[str] = None,
) -> pd.DataFrame:
    """Query a table, optionally filtering/limiting/selecting columns."""
    tbl = open_table(conn, table_name)

    try:
        if where:
            results = tbl.search().where(where).to_pandas()
        else:
            results = tbl.to_pandas()
    except Exception as e:
        raise CommandError(f"Query failed: {e}")

    if limit and len(results) > limit:
        results = results.head(limit)

    return _apply_select(results, select)


def refresh_sql_views(conn: lancedb.DBConnection) -> None:
    """(Re)register every table in the database as a DuckDB view, by name."""
    for table_name in list_tables(conn):
        try:
            tbl = conn.open_table(table_name)
            duckdb.register(table_name, tbl.to_arrow())
        except Exception as e:
            raise CommandError(f"Could not refresh view for '{table_name}': {e}")


def run_sql(conn: lancedb.DBConnection, sql_query: str) -> pd.DataFrame:
    """Run a raw SQL query across all tables in the database (registered as DuckDB views)."""
    refresh_sql_views(conn)
    try:
        return duckdb.sql(sql_query).to_df()
    except Exception as e:
        if "types don't match" in str(e) or "Contents of view were altered" in str(e):
            refresh_sql_views(conn)
            try:
                return duckdb.sql(sql_query).to_df()
            except Exception as retry_e:
                raise CommandError(f"SQL query failed: {retry_e}")
        raise CommandError(f"SQL query failed: {e}")


def delete_rows(conn: lancedb.DBConnection, table_name: str, where: str) -> int:
    """Delete rows matching `where`. Returns the number of rows deleted."""
    tbl = open_table(conn, table_name)
    try:
        rows_before = tbl.count_rows()
        tbl.delete(where)
        rows_after = tbl.count_rows()
    except Exception as e:
        raise CommandError(f"Delete failed: {e}")
    return rows_before - rows_after


def empty_table(conn: lancedb.DBConnection, table_name: str) -> int:
    """Delete all rows in a table. Returns the number of rows deleted."""
    return delete_rows(conn, table_name, "1=1")


def drop_table(conn: lancedb.DBConnection, table_name: str) -> None:
    """Drop (delete) an entire table."""
    if not table_exists(conn, table_name):
        raise CommandError(f"Table '{table_name}' not found in database")
    try:
        conn.drop_table(table_name)
    except Exception as e:
        raise CommandError(f"Drop failed: {e}")
    try:
        duckdb.sql(f"DROP VIEW IF EXISTS {table_name}")
    except Exception:
        pass


def update_rows(conn: lancedb.DBConnection, table_name: str, values: Dict[str, Any], where: str) -> None:
    """Update rows matching `where`, setting the given column values."""
    tbl = open_table(conn, table_name)
    try:
        tbl.update(where=where, values=values)
    except Exception as e:
        raise CommandError(f"Update failed. Columns: {values}, WHERE: {where}. Error: {e}")


def _sql_literal(value: Any) -> str:
    if hasattr(value, "item"):
        # Unwrap numpy scalars (int64, float64, bool_, ...) to native Python types —
        # isinstance(numpy.int64(1), int) is False, which would otherwise misquote them.
        value = value.item()
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _is_vector_value(value: Any) -> bool:
    """True for embedding/vector-column values (multi-element arrays or lists) — these
    can't be expressed as a single SQL equality literal, so they're excluded from
    row-matching WHERE clauses."""
    size = getattr(value, "size", None)
    if size is not None:
        return size != 1
    return isinstance(value, (list, tuple)) and len(value) != 1


def build_row_where_clause(row: Dict[str, Any]) -> str:
    """Build a WHERE clause matching a row by exact equality on every given column —
    used to target a specific row (e.g. the one behind a cell a user just edited) when
    there's no known primary key. Vector/embedding columns are skipped, since their
    values can't be expressed as a SQL equality literal. Raises CommandError if given
    no columns to match on."""
    parts = []
    for col, value in row.items():
        if _is_vector_value(value):
            continue
        if value is None or (isinstance(value, float) and pd.isna(value)):
            parts.append(f"{col} IS NULL")
        else:
            parts.append(f"{col} = {_sql_literal(value)}")
    if not parts:
        raise CommandError("Cannot identify this row to update: no other columns to match on")
    return " AND ".join(parts)


def load_csv(conn: lancedb.DBConnection, csv_path: str, table_name: str, overwrite: bool = False) -> pd.DataFrame:
    """Load a CSV file into a table, returning the loaded DataFrame."""
    path = Path(csv_path)
    if not path.exists():
        raise CommandError(f"CSV file '{csv_path}' not found")

    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise CommandError(f"Error reading CSV file: {e}")

    if len(df) == 0:
        raise CommandError("CSV file is empty")

    if table_exists(conn, table_name) and not overwrite:
        raise CommandError(f"Table '{table_name}' already exists. Use --overwrite to replace it")

    mode = "overwrite" if overwrite else "create"
    try:
        conn.create_table(table_name, data=df, mode=mode)
    except Exception as e:
        raise CommandError(f"Load failed: {e}")

    return df


def dump_csv(conn: lancedb.DBConnection, table_name: str, output_path: str, overwrite: bool = False) -> pd.DataFrame:
    """Dump a table to a CSV file, returning the dumped DataFrame."""
    tbl = open_table(conn, table_name)

    out_path = Path(output_path)
    if out_path.exists() and not overwrite:
        raise CommandError(f"Output file '{output_path}' already exists. Use --overwrite to replace it")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = tbl.to_pandas()
    try:
        df.to_csv(out_path, index=False)
    except Exception as e:
        raise CommandError(f"Dump failed: {e}")
    return df


@lru_cache(maxsize=4)
def get_embedding_function(model_name: str):
    """Load (and cache for the process lifetime) a sentence-transformers embedding
    function by name. The .create() call is what triggers huggingface_hub's download
    + local cache on first use of a given model — no custom downloader needed."""
    try:
        # transformers' "Loading weights" progress bar makes tqdm construct a
        # multiprocessing.RLock() to coordinate output across forked processes. Inside
        # a running Textual app's raw-mode terminal, registering that lock spawns
        # Python's resource_tracker subprocess, which can fail with "bad value(s) in
        # fds_to_keep" and crash the whole load — even though we never fork child
        # processes and have no use for a multiprocessing-safe tqdm lock. Pre-setting
        # mp_lock makes tqdm skip constructing one at all (create_mp_lock no-ops once
        # the class attribute already exists).
        import tqdm.std

        tqdm.std.TqdmDefaultWriteLock.mp_lock = None

        from lancedb.embeddings import get_registry

        return get_registry().get("sentence-transformers").create(name=model_name)
    except Exception as e:
        raise CommandError(f"Could not load embedding model '{model_name}': {e}")


def embed_table(
    conn: lancedb.DBConnection,
    table_name: str,
    source_columns: List[str],
    target_columns: List[str],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Compute embeddings for one or more text columns into one or more vector columns.

    Local/OSS LanceDB's Table.add_columns(transforms=...) only accepts SQL expressions
    or Cloud/Enterprise-only Python function-columns — there is no schema-evolution API
    to attach a Python embedding call for a local database. So: read the whole table
    into a DataFrame, compute embeddings in Python, assign them as new column(s), and
    rewrite the table via create_table(..., mode="overwrite"). Same whole-table-in-memory
    ceiling as /dump and /sql (see build_row_where_clause)."""
    if len(source_columns) != len(target_columns):
        raise CommandError(
            f"Got {len(source_columns)} source column(s) but {len(target_columns)} target "
            "column(s) — they must pair up one-to-one"
        )

    tbl = open_table(conn, table_name)
    schema_names = set(tbl.schema.names)
    for col in source_columns:
        if col not in schema_names:
            raise CommandError(f"Source column '{col}' not found in table '{table_name}'")

    existing_targets = [c for c in target_columns if c in schema_names]
    if existing_targets and not overwrite:
        raise CommandError(
            f"Target column(s) {', '.join(existing_targets)} already exist in '{table_name}'. "
            "Use --overwrite to replace them"
        )

    embed_fn = get_embedding_function(model_name)
    df = tbl.to_pandas()

    try:
        # Compute every embedding from the untouched original columns first, then
        # assign them all afterward — if a pair's target name collides with a later
        # pair's source name (e.g. --source city,name --target name,final), computing
        # and assigning in a single pass would make the later pair embed the vector
        # just written into that column instead of the real source text.
        computed = {}
        for source_col, target_col in zip(source_columns, target_columns):
            texts = df[source_col].fillna("").astype(str).tolist()
            embeddings = embed_fn.generate_embeddings(texts)
            # One np.ndarray per row (not a nested python list) — needed so lancedb's
            # pandas->arrow conversion infers FixedSizeList<float32>, not a variable-
            # length List, which is required for vector search to work on the result.
            computed[target_col] = list(np.asarray(embeddings, dtype=np.float32))
        for target_col, values in computed.items():
            df[target_col] = values
    except Exception as e:
        raise CommandError(f"Embedding failed: {e}")

    try:
        conn.create_table(table_name, data=df, mode="overwrite")
    except Exception as e:
        raise CommandError(f"Writing embedded table failed: {e}")

    return df


def has_fts_index(tbl, column: str) -> bool:
    """True if `column` already has a full-text (inverted) index built on it."""
    return any(idx.index_type == "FTS" and column in idx.columns for idx in tbl.list_indices())


def create_fts_index(conn: lancedb.DBConnection, table_name: str, column: str) -> None:
    """Create (or replace) a full-text index on `column`. Required before /search can
    run in fts or hybrid mode — LanceDB raises a hard error for either without one."""
    tbl = open_table(conn, table_name)
    if column not in tbl.schema.names:
        raise CommandError(f"Column '{column}' not found in table '{table_name}'")
    try:
        from lancedb.index import FTS

        tbl.create_index(column, config=FTS())
    except Exception as e:
        raise CommandError(f"Could not create FTS index on '{column}': {e}")


def _resolve_vector_column(tbl, explicit: Optional[str]) -> str:
    """Pick which vector column to search against. An explicit --vector-column always
    wins; otherwise auto-infer only if the table has exactly one vector-shaped column —
    tables can carry several after repeated /embedding runs, and guessing wrong would
    silently search the wrong embedding space."""
    vector_cols = [f.name for f in tbl.schema if pa.types.is_fixed_size_list(f.type)]
    if explicit:
        if explicit not in vector_cols:
            raise CommandError(
                f"'{explicit}' is not a vector column. Vector columns in this table: "
                f"{', '.join(vector_cols) or 'none'}"
            )
        return explicit
    if not vector_cols:
        raise CommandError("No vector columns found in this table. Run /embedding first.")
    if len(vector_cols) > 1:
        raise CommandError(
            f"Multiple vector columns found ({', '.join(vector_cols)}); specify --vector-column"
        )
    return vector_cols[0]


def search_table(
    conn: lancedb.DBConnection,
    table_name: str,
    mode: str,
    query: str,
    vector_column: Optional[str] = None,
    text_column: Optional[str] = None,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    limit: int = 10,
    where: Optional[str] = None,
    select: Optional[str] = None,
) -> pd.DataFrame:
    """Vector, full-text, or hybrid search against a table.

    vector: embeds `query` via the current embedding model and runs an exact kNN scan
    (brute-force — lsql's tables are small enough that no ANN index is required).
    fts: keyword search against `text_column`, auto-creating its FTS index on first use.
    hybrid: both of the above combined via LanceDB's default RRF reranker.
    """
    if mode not in ("vector", "fts", "hybrid"):
        raise CommandError(f"Unknown search mode '{mode}'. Use vector, fts, or hybrid")

    tbl = open_table(conn, table_name)
    needs_vector = mode in ("vector", "hybrid")
    needs_text = mode in ("fts", "hybrid")

    # Cheap validation (schema/column checks) runs before any expensive work — notably
    # before get_embedding_function, which can trigger a multi-hundred-MB model
    # download on first use. A missing/typo'd --text-column shouldn't cost that.
    resolved_vector_col = None
    if needs_vector:
        resolved_vector_col = _resolve_vector_column(tbl, vector_column)

    if needs_text:
        if not text_column:
            raise CommandError("--text-column is required for fts/hybrid search")
        if text_column not in tbl.schema.names:
            raise CommandError(f"Column '{text_column}' not found in table '{table_name}'")

    vec = None
    if needs_vector:
        embed_fn = get_embedding_function(model_name)
        try:
            vec = np.asarray(embed_fn.generate_embeddings([query])[0], dtype=np.float32)
        except Exception as e:
            raise CommandError(f"Could not embed query: {e}")

    if needs_text:
        if not has_fts_index(tbl, text_column):
            create_fts_index(conn, table_name, text_column)
            tbl = open_table(conn, table_name)

    try:
        if mode == "vector":
            builder = tbl.search(vec, vector_column_name=resolved_vector_col, query_type="vector")
        elif mode == "fts":
            builder = tbl.search(query, query_type="fts", fts_columns=text_column)
        else:
            builder = tbl.search(
                query_type="hybrid", vector_column_name=resolved_vector_col, fts_columns=text_column
            )
            builder = builder.vector(vec).text(query)

        if where:
            builder = builder.where(where)
        results = builder.limit(limit).to_pandas()
    except Exception as e:
        raise CommandError(f"Search failed: {e}")

    return _apply_select(results, select)
