"""Generate a LanceDB database seeded with TPC-H benchmark data, for manual testing.

Uses DuckDB's built-in `tpch` extension (`dbgen`) to synthesize the standard 8-table
TPC-H schema, then caps each table at --rows (default 1000) before loading it into a
LanceDB database at --path. `nation` (25 rows) and `region` (5 rows) are fixed-size
reference tables in the TPC-H spec and load in full regardless of --rows; the other
six tables are capped independently per table, so cross-table foreign keys (e.g.
lineitem.l_orderkey -> orders.o_orderkey) are not guaranteed to all resolve — that's
fine for exercising lsql's commands, not for join-correctness testing.
"""

import argparse
import shutil
from pathlib import Path

import duckdb

from lsql.core import db

TABLES = ["region", "nation", "supplier", "customer", "part", "partsupp", "orders", "lineitem"]


def generate(path: str, rows: int, scale_factor: float, overwrite: bool) -> None:
    out_path = Path(path)
    if out_path.exists():
        if not overwrite:
            raise SystemExit(f"{path} already exists (use --overwrite to replace it)")
        shutil.rmtree(out_path)

    dgen = duckdb.connect()
    dgen.execute("INSTALL tpch")
    dgen.execute("LOAD tpch")
    dgen.execute(f"CALL dbgen(sf={scale_factor})")

    conn = db.connect(path)
    for table in TABLES:
        df = dgen.execute(f"SELECT * FROM {table} LIMIT {rows}").df()
        conn.create_table(table, data=df)
        print(f"{table}: {len(df)} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="tcph.lance", help="Output LanceDB database path")
    parser.add_argument("--rows", type=int, default=1000, help="Max rows per table")
    parser.add_argument(
        "--scale-factor",
        type=float,
        default=0.01,
        help="TPC-H dbgen scale factor — must be large enough that every table has at least --rows rows",
    )
    parser.add_argument("--overwrite", action="store_true", help="Delete --path first if it already exists")
    args = parser.parse_args()
    generate(args.path, args.rows, args.scale_factor, args.overwrite)


if __name__ == "__main__":
    main()
