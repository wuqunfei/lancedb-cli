# GitHub Copilot Instructions for lsql

## Project Overview

`lsql` is a terminal GUI (Textual) for managing LanceDB databases. It is **not** a
flat one-shot CLI — the only interface is the four-panel TUI: a database picker, a
table list, a slash-command input, and a results panel. SQL execution across tables
is handled via DuckDB integration.

**Command Name:** `lsql`
**Main Technologies:** LanceDB, DuckDB, Textual, Typer (launcher only), Rich, pandas

## Architecture

```
lsql/
  __main__.py       # thin Typer launcher — parses an optional db_path, runs the Textual app
  core/
    parsing.py       # value/clause parsing helpers (pure functions, no I/O)
    rendering.py      # Rich renderable builders (no module-level Console)
    db.py             # all lancedb/duckdb access; raises CommandError on failure
    exceptions.py       # CommandError
  persistence.py        # recent-database paths + command history, JSON under ~/.config/lsql/
  commands/
    parser.py            # SilentArgumentParser (raises instead of sys.exit), per-command argparse factories
    registry.py            # CommandSpec/COMMANDS, prepare()/execute() dispatcher
    handlers.py               # cmd_* functions; take (AppState, args) -> CommandResult
    results.py                  # AppState, CommandResult, PreparedCommand
  tui/
    app.py                       # LanceDBApp — the Textual App, holds AppState
    app.tcss                      # layout/styling
    widgets/                       # one module per panel + ConfirmModal
```

### Key rule: commands never touch a terminal directly

Command handlers (`commands/handlers.py`) return a `CommandResult`; they never call
`print`/`console.print` and never `sys.exit`. `core/db.py` functions raise
`CommandError` on failure; the dispatcher (`commands/registry.py`) catches it and
converts it into an error `CommandResult`. This is what makes the command layer
unit-testable without a running Textual app (see `tests/test_handlers.py`).

### Table targeting

Commands that need a table (`query`, `schema`, `delete`, `empty`, `drop`, `update`,
`dump`) always use `AppState.current_table` — the table selected in the table list
panel. They do **not** accept a table-name argument. `/sql` is the one exception: it
runs across every table in the database and ignores `current_table` entirely. `/load`
is the other exception: since it creates a new table, it takes an explicit `--table`
flag.

### Destructive commands

`/drop`, `/empty`, `/delete` are marked `destructive=True` in the `COMMANDS` registry
with a `confirm_template`. `registry.prepare()` builds the confirmation message but
does **not** show it — that's the TUI's job: `tui/app.py` calls
`push_screen_wait(ConfirmModal(...))` (inside a method decorated with `@work`, since
`push_screen_wait` requires a Textual worker context) before calling
`registry.execute()`.

## Code Style and Conventions

- Follow PEP 8, use type hints, max line length 100
- Docstrings only where the *why* isn't obvious from the code — don't restate what a
  well-named function already says
- `core/` and `commands/` modules must stay Textual-free and UI-free, so they can be
  tested directly without spinning up the app

## Adding a new slash command

1. Add a handler to `commands/handlers.py`: `def cmd_foo(state: AppState, args) -> CommandResult`
2. If it takes flags, add a parser factory to `commands/parser.py` using `SilentArgumentParser`
3. Register it in `commands/registry.py`'s `COMMANDS` dict as a `CommandSpec`
   (set `needs_table=False` if it doesn't use `current_table`, `destructive=True` +
   `confirm_template` if it should ask for confirmation)
4. Add tests to `tests/test_handlers.py`
5. Update the command list in `README.md`

## Testing

- `tests/test_db.py`, `tests/test_command_parser.py`, `tests/test_handlers.py` — plain
  unit tests, no Textual, run against real throwaway LanceDB directories (`tmp_path`)
- `tests/test_app_smoke.py` — Textual `Pilot` tests (`app.run_test()`), headless
- **Never construct `LanceDBApp()` in a test without injecting `recent_databases=`/
  `command_history=` pointed at `tmp_path`** — the defaults write to the user's real
  `~/.config/lsql/`. See `make_app()` in `tests/test_app_smoke.py`.

## Dependencies

**Core:** `lancedb`, `duckdb`, `pandas`, `typer`, `rich`, `textual`
**Dev:** pytest, pytest-asyncio (for Pilot tests), pytest-cov, black, isort, flake8, mypy

## Documentation

- Keep `README.md`'s command list in sync with `commands/registry.py`
- Keep this file in sync with the module structure above when it changes
