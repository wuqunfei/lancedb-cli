"""lancedb/duckdb access layer. Raises CommandError on user-facing failures."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import lancedb
import pandas as pd

from .exceptions import CommandError


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

    if select:
        cols = [c.strip() for c in select.split(",")]
        results = results[[c for c in cols if c in results.columns]]

    return results


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
