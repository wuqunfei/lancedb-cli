# 🗄️ lsql

**lsql** is a TUI for managing [LanceDB](https://lancedb.com/) databases easily. Pick a
database and a table visually, then run slash commands against whatever's selected — no
more retyping paths and table names for every single query.

Every example below runs against the standard **TPC-H** `customer` table
(`c_custkey`, `c_name`, `c_address`, `c_nationkey`, `c_phone`, `c_acctbal`,
`c_mktsegment`, `c_comment`) — generate it yourself with:

```bash
python scripts/generate_tcph_db.py --path tcph.lance
```

This seeds a LanceDB database with all 8 TPC-H tables (`region`, `nation`, `supplier`,
`customer`, `part`, `partsupp`, `orders`, `lineitem`), ~1000 rows each (`nation` and
`region` are small fixed-size reference tables in the TPC-H spec, so they load in full
at 25 and 5 rows).

Here's `tcph.lance` open with `customer` selected, after running
`/query --where "c_mktsegment = 'BUILDING'" --select "c_custkey,c_name,c_acctbal,c_mktsegment" --limit 10`:

![tcph customer query screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/01-tcph-customer-query.svg)

---

## ✨ Features

- 🖥️ **Four-panel layout** — database picker, table list, command input, and results,
  all on one screen
- 📁 **Folder-browser dialog** — open an existing database by browsing to it, no need
  to memorize or hand-type paths
- ⚡ **Slash commands with auto-suggestion** — type `/` and see every available command,
  filtered live as you type
- 🖱️ **Click a table to preview it** — instantly runs `select * from <table> limit 100`
  for you
- 🔍 **Double-click any cell** — pop open the full, untruncated value when a row is too
  wide to read comfortably, with buttons to **copy** it or **edit and write it back**
- 📄 **Pagination** — large result sets are paged 100 rows at a time instead of flooding
  the screen
- 🧮 **Raw SQL via DuckDB** — `/sql` runs across every table in the database
- 🧬 **Embeddings** — set a sentence-transformers model in the Embedding Model panel
  (downloading it on first use), then `/embedding` computes vector column(s) for a table
- 🔎 **Vector, full-text, and hybrid search** — `/search-vector` runs a kNN vector
  search, `/search-fts` a keyword full-text search, and `/search-hybrid` both combined
  (LanceDB's default RRF reranker) against the current table; `/index` builds the
  full-text index `/search-fts`/`/search-hybrid` need, or it's built for you
  automatically on first use
- 🛟 **Confirmation dialogs** — `/drop`, `/empty`, `/delete`, and `/embedding` always ask first
- ⏪ **Command history** — up/down arrow recall, just like a shell
- 📚 **Built-in help** — `/help` lists every command; `/help <command>` shows its flags
- 🌓 **Light/dark theme** — a one-click toggle, defaulting to your OS's current setting

---

## 📦 Installation

```bash
pip install lsql
```

## 🚀 Quick Start

```bash
lsql                      # launch the TUI
lsql /path/to/database    # launch pre-connected to a database
```

No database handy? Generate the TPC-H test database shown throughout this README:

```bash
python scripts/generate_tcph_db.py --path tcph.lance
lsql tcph.lance
```

---

## 🧭 The four panels

1. **Database** (top left) — type a path and hit Enter, or click **Connect...** to browse
   to one. Opening a path that doesn't exist yet creates a database there — same as
   `/create --path <path>`. The 🌙/☀️ icon toggles light/dark theme.
2. **Tables** (bottom left) — every table in the open database. Click one to select it
   and immediately preview its first 100 rows.
3. **Command input** (bottom) — type `/` for a filtered, live-updating dropdown of
   matching commands; `↑`/`↓` to navigate it, `Tab`/`Enter` to accept, `Esc` to dismiss.
   `↑`/`↓` also recall command history when the dropdown isn't open.
4. **Results** (top right) — renders whatever the last command produced: a data table,
   schema text, a status message, or a confirmation prompt for destructive commands.
   Large result sets paginate 100 rows at a time; double-click any cell to see its full
   value, copy it, or edit it and write the change back to the table.

---

## ⌨️ Command reference

Commands that operate on a table (`query`, `schema`, `delete`, `empty`, `drop`, `update`,
`dump`, `index`, `search-vector`, `search-fts`, `search-hybrid`) always act on whichever
table is currently selected in the table list — select it there rather than naming it in
the command.

| Command | What it does |
|---|---|
| `/create --path <path>` | Create (or open) a database at `path` |
| `/query [--where ...] [--limit 10] [--select "a,b"] [--output table\|json]` | Query the current table |
| `/schema` | Show the current table's schema |
| `/sql <SQL query>` | Raw SQL across **every** table — the one command that ignores the table selection |
| `/update --set-clause "col='val'" --where "..."` | Update rows in the current table |
| `/delete --where "..."` | Delete rows from the current table |
| `/empty` | Delete all rows from the current table |
| `/drop` | Drop the current table entirely |
| `/load --path file.csv --table name [--overwrite]` | Load a CSV into a new table |
| `/embedding --table name --source col[,col2] [--target vec[,vec2]] [--model org/name] [--overwrite]` | Compute embeddings for one or more columns into vector column(s) |
| `/index --column name` | Build a full-text index on a column of the current table |
| `/search-vector --query "..." [--vector-column c] [--model org/name] [--limit 10] [--where ...] [--select "a,b"]` | kNN vector search against the current table |
| `/search-fts --query "..." --text-column c [--limit 10] [--where ...] [--select "a,b"]` | Keyword full-text search against the current table |
| `/search-hybrid --query "..." --text-column c [--vector-column c] [--model org/name] [--limit 10] [--where ...] [--select "a,b"]` | Vector + full-text hybrid search against the current table |
| `/dump --path out.csv [--overwrite]` | Dump the current table to CSV |
| `/refresh` | Refresh the table list and SQL views |
| `/help [command]` | Show all commands, or details for one |
| `/exit` | Quit |

---

## 🧪 Walkthrough: every command against `tcph.lance`

Open `tcph.lance` (generated above), select **customer** in the table list, and work
through these in order — each one was run for real against the TPC-H `customer` table to
produce the output shown.

**`/create --path tcph.lance`** opens (or creates) the database — the same thing typing
the path into the Database panel and hitting Enter does.

**`/schema`** shows the current table's columns and types:

```
c_custkey: int64
c_name: large_string
c_address: large_string
c_nationkey: int32
c_phone: large_string
c_acctbal: double
c_mktsegment: large_string
c_comment: large_string
```

**`/query --where "c_mktsegment = 'BUILDING'" --select "c_custkey,c_name,c_acctbal" --limit 5`**
filters, projects, and limits the current table:

```
   c_custkey              c_name  c_acctbal
0          1  Customer#000000001     711.56
1          8  Customer#000000008    6819.74
2         11  Customer#000000011    -272.60
```

**`/sql SELECT c.c_name, n.n_name FROM customer c JOIN nation n ON c.c_nationkey = n.n_nationkey LIMIT 5`**
is the one command that ignores the table selection and runs raw SQL (via DuckDB) across
every table in the database — here joining `customer` against `nation`:

```
               c_name     n_name
0  Customer#000000001    MOROCCO
1  Customer#000000002     JORDAN
```

**`/update --set-clause "c_mktsegment='ENTERPRISE'" --where "c_custkey = 1"`** updates
matching rows in place — a follow-up `/query --where "c_custkey = 1" --select "c_mktsegment"`
confirms customer 1 is now `ENTERPRISE`.

**`/delete --where "c_custkey = 999999"`** deletes matching rows (here, none match, so it
reports `Deleted 0 row(s)`). `/delete`, along with `/empty`, `/drop`, and `/embedding`,
pops a confirmation dialog before running.

**`/dump --path customer_export.csv --overwrite`** writes the current table to CSV:
`Dumped 1000 row(s) from 'customer' to 'customer_export.csv'`.

**`/load --path customer_export.csv --table customer_staging --overwrite`** loads a CSV
into a brand-new table — `/load` (and `/embedding`) take an explicit `--table` name
instead of using the current selection, since `/load` creates the table and `/embedding`
is often pointed at a different table than the one selected.

**`/embedding --table customer --source c_comment --target c_comment_vector`** computes
vector embeddings for `c_comment` (the only free-text column) into a new
`c_comment_vector` column, using the model set in the Embedding Model panel, or
`all-MiniLM-L6-v2` if none is set; `--model org/name` overrides both for a single run.
With multiple `--source` columns and no `--target`, each gets its own `<source>_vector`.

**`/index --column c_comment`** builds a full-text index on `c_comment` — not required
before `/search-fts`/`/search-hybrid`, since they build it automatically on first use,
but worth running once up front if you'll be searching the column repeatedly.

**`/search-vector --query "careful special requests" --vector-column c_comment_vector --limit 3`**
embeds the query with the same model precedence as `/embedding` and runs an exact kNN
scan — no index required. `--vector-column` is only needed when a table has more than
one vector column; `customer` has exactly one, so it's auto-inferred and can be omitted.

**`/search-fts --query "quickly" --text-column c_comment --limit 3`** keyword-searches
`c_comment`. `--text-column` is always required — there's no single obvious text column
to default to.

**`/search-hybrid --query "careful special requests" --text-column c_comment --limit 3`**
runs both and combines them with LanceDB's default RRF reranker, so it needs both a
vector column (inferred or explicit) and `--text-column`.

**`/refresh`** refreshes the table list and SQL views — useful after creating or dropping
tables outside of lsql.

**`/help search-fts`** shows a single command's full usage:

```
Full-text keyword search on the current table (--query ... --text-column ... [--limit/--where/--select])

usage: /search-fts --query QUERY --text-column TEXT_COLUMN [--limit LIMIT]
                   [--where WHERE] [--select SELECT]

options:
  --query QUERY         Keyword search query
  --text-column TEXT_COLUMN
                        Text column to search — auto-creates its FTS index on
                        first use
  --limit LIMIT         Number of rows to return
  --where WHERE         WHERE clause filter (SQL syntax)
  --select SELECT       Columns to select (comma-separated)
```

**`/empty`** then **`/drop`** clean up the disposable `customer_staging` table created
above — `Emptied 'customer_staging' — deleted 1000 row(s)` followed by
`Dropped table 'customer_staging'`. Running either against `customer` itself would ask
for confirmation first, given it's destructive.

**`/exit`** quits lsql.

---

## 🛠️ Development

```bash
git clone https://github.com/wuqunfei/lsql.git
cd lsql
pip install -e ".[dev]"
```

Run the tests:

```bash
pytest
```

Regenerate the screenshot above after a visible UI change:

```bash
python scripts/generate_screenshots.py
```

### Requirements

- Python 3.10+
- lancedb, duckdb, pandas, pyarrow, typer, rich, textual, sentence-transformers

---

## 🤝 Contributing

Contributions are welcome! Please feel free to open a PR.

## 🐛 Issues

Found a bug or have an idea? [Open an issue](https://github.com/wuqunfei/lsql/issues).

## 📄 License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
