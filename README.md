# 🗄️ lsql

**lsql** is a TUI for managing [LanceDB](https://lancedb.com/) databases easily. Pick a
database and a table visually, then run slash commands against whatever's selected — no
more retyping paths and table names for every single query.

![launch screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/01-launch.svg)

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

---

## 🧭 A tour of the four panels

### 1️⃣ Database — type a path or browse to one

Type a path directly and hit Enter, or click **Open...** to pick a folder visually (with
an **Up** button to walk back up the directory tree). The 🌙/☀️ icon next to it toggles
light/dark theme — it defaults to whatever your OS is currently using.

![browse database screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/02-browse-database.svg)

Opening a path that doesn't exist yet creates a database there — same as running
`/create --path <path>`.

### 2️⃣ Tables — click to preview

Click any table in the list to select it and immediately see its first 100 rows.

![table selected screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/03-table-selected.svg)

### 3️⃣ Command input — slash commands with live suggestions

Start typing `/` and a filtered dropdown of matching commands appears. Use `↑`/`↓` to
pick one, `Tab` or `Enter` to accept it, `Esc` to dismiss. `↑`/`↓` also recall previous
commands when the dropdown isn't open.

![slash command suggestions screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/04-slash-suggestions.svg)

Forgot a flag? `/help` lists every command, and `/help <command>` shows its full usage:

![help command screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/06-help.svg)

### 4️⃣ Results — tables, schemas, and safety checks

`/schema` renders a table's columns and types right in the results panel:

![schema screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/05-schema.svg)

Destructive commands always confirm first:

![confirm destructive command screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/07-confirm-destructive.svg)

Large results are paginated — 100 rows per page, with `< Prev` / `Next >` controls:

![pagination screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/08-pagination.svg)

And if a cell's value is too long to read in the table, double-click it to see the full
text, copy it, or edit it and write the change back to the table:

![cell detail popup screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/09-cell-detail.svg)

`/search-vector`, `/search-fts`, and `/search-hybrid` run vector, full-text, or hybrid
search against the current table — here's
`/search-hybrid --query "remember to buy groceries" --text-column note` against a
table of unrelated notes, finding the shopping-list one even though "groceries" never
appears verbatim:

![search results screenshot](https://raw.githubusercontent.com/wuqunfei/lsql/main/docs/screenshots/10-search-results.svg)

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

`/drop`, `/empty`, `/delete`, and `/embedding` pop a confirmation dialog before running
(`/embedding` always rewrites the whole table under the hood, even without
`--overwrite`). `/load` and `/embedding` take an explicit `--table` name instead of
using the current selection — `/load` because it creates a brand-new table,
`/embedding` because it's often more convenient to target a table other than the one
currently selected.

`/embedding` uses the model set in the Embedding Model panel by default, or
`all-MiniLM-L6-v2` if none has been set; `--model` overrides both for a single run.
With multiple `--source` columns and no `--target`, each gets its own `<source>_vector`
column.

`/search-vector` embeds `--query` with the same model precedence as `/embedding` and runs
an exact kNN scan — no index required. `--vector-column` is only needed if the table has
more than one vector column (from repeated `/embedding` runs); with exactly one, it's
picked automatically. `/search-fts` keyword-searches `--text-column` (required — there's
no single obvious text column to default to), building its full-text index automatically
on first use if one doesn't exist yet (same as running `/index --column` on it
beforehand). `/search-hybrid` runs both and combines them with LanceDB's default RRF
reranker, so it needs both a vector column (inferred or explicit) and `--text-column`.

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

Regenerate the screenshots above after a visible UI change:

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
