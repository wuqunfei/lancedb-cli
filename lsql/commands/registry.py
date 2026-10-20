"""Command registry and dispatcher: maps slash-command names to handlers, validates
table/connection prerequisites, and separates parsing+validation (prepare) from running
the handler (execute) so the TUI layer can insert an async confirmation step in between
for destructive commands."""

from dataclasses import dataclass
from typing import Callable, Optional, Union

from rich.text import Text

from ..core.exceptions import CommandError
from . import handlers, parser
from .parser import ArgParseExit
from .results import AppState, CommandResult, PreparedCommand, error, ok_text


@dataclass
class CommandSpec:
    name: str
    handler: Callable
    build_parser: Optional[Callable] = None  # None only for /sql, which takes raw text
    needs_table: bool = True
    needs_connection: bool = True  # False only for /create and /help
    destructive: bool = False
    confirm_template: Optional[str] = None
    raw_text: bool = False
    slow: bool = False  # True if the handler may take long enough to need a progress indicator
    help_text: str = ""  # one-line summary, shown by /help and the command-input suggestions


def _cmd_help(state: AppState, args) -> CommandResult:
    """Implemented here (not in handlers.py) since it needs to introspect COMMANDS itself,
    which would otherwise create a circular import between registry.py and handlers.py."""
    if args.command_name:
        name = args.command_name.lstrip("/").lower()
        spec = COMMANDS.get(name)
        if spec is None:
            return error(f"Unknown command: /{name}")
        if spec.raw_text:
            body = f"/sql <SQL query>\n\n{spec.help_text}"
        else:
            body = spec.build_parser().format_help()
            if spec.help_text:
                body = f"{spec.help_text}\n\n{body}"
        return ok_text(Text(body.strip()))

    width = max(len(n) for n in COMMANDS) + 1
    lines = [f"/{name:<{width}} {spec.help_text}" for name, spec in sorted(COMMANDS.items())]
    return ok_text(Text("Available commands — /help <command> for details:\n\n" + "\n".join(lines)))


COMMANDS = {
    "help": CommandSpec(
        "help",
        _cmd_help,
        parser.build_help_parser,
        needs_table=False,
        needs_connection=False,
        help_text="Show all commands, or /help <command> for details on one",
    ),
    "create": CommandSpec(
        "create",
        handlers.cmd_create,
        parser.build_create_parser,
        needs_table=False,
        needs_connection=False,
        help_text="Create (or open) a database at --path",
    ),
    "query": CommandSpec(
        "query",
        handlers.cmd_query,
        parser.build_query_parser,
        help_text="Query the current table (--where/--limit/--select/--output)",
    ),
    "schema": CommandSpec(
        "schema", handlers.cmd_schema, parser.build_schema_parser, help_text="Show the current table's schema"
    ),
    "sql": CommandSpec(
        "sql",
        handlers.cmd_sql,
        needs_table=False,
        raw_text=True,
        help_text="Run raw SQL across every table in the database",
    ),
    "delete": CommandSpec(
        "delete",
        handlers.cmd_delete,
        parser.build_delete_parser,
        destructive=True,
        confirm_template="Delete rows from '{table}' where {where}? This cannot be undone.",
        help_text="Delete rows from the current table matching --where",
    ),
    "empty": CommandSpec(
        "empty",
        handlers.cmd_empty,
        parser.build_empty_parser,
        destructive=True,
        confirm_template="Delete ALL rows from '{table}'? This cannot be undone.",
        help_text="Delete all rows from the current table",
    ),
    "drop": CommandSpec(
        "drop",
        handlers.cmd_drop,
        parser.build_drop_parser,
        destructive=True,
        confirm_template="Drop table '{table}' entirely? This cannot be undone.",
        help_text="Drop the current table entirely",
    ),
    "update": CommandSpec(
        "update",
        handlers.cmd_update,
        parser.build_update_parser,
        help_text="Update rows in the current table (--set-clause/--where)",
    ),
    "load": CommandSpec(
        "load",
        handlers.cmd_load,
        parser.build_load_parser,
        needs_table=False,
        help_text="Load a CSV into a new table (--path/--table/--overwrite)",
    ),
    "embedding": CommandSpec(
        "embedding",
        handlers.cmd_embedding,
        parser.build_embedding_parser,
        needs_table=False,
        destructive=True,
        confirm_template=(
            "Compute embeddings for table '{table}' from column(s) '{source}'? "
            "This rewrites the entire table."
        ),
        slow=True,
        help_text="Compute embeddings for a table (--table/--source/--target/--model/--overwrite)",
    ),
    "index": CommandSpec(
        "index",
        handlers.cmd_index,
        parser.build_index_parser,
        help_text="Build a full-text index on a column of the current table (--column)",
    ),
    "search-vector": CommandSpec(
        "search-vector",
        handlers.cmd_search_vector,
        parser.build_search_vector_parser,
        help_text="kNN vector search on the current table (--query ... [--vector-column/--model/--limit/--where/--select])",
    ),
    "search-fts": CommandSpec(
        "search-fts",
        handlers.cmd_search_fts,
        parser.build_search_fts_parser,
        help_text="Full-text keyword search on the current table (--query ... --text-column ... [--limit/--where/--select])",
    ),
    "search-hybrid": CommandSpec(
        "search-hybrid",
        handlers.cmd_search_hybrid,
        parser.build_search_hybrid_parser,
        help_text=(
            "Vector + full-text hybrid search on the current table (--query ... --text-column ... "
            "[--vector-column/--model/--limit/--where/--select])"
        ),
    ),
    "dump": CommandSpec(
        "dump",
        handlers.cmd_dump,
        parser.build_dump_parser,
        help_text="Dump the current table to a CSV file (--path/--overwrite)",
    ),
    "refresh": CommandSpec(
        "refresh",
        handlers.cmd_refresh,
        parser.build_refresh_parser,
        needs_table=False,
        help_text="Refresh the table list and SQL views",
    ),
    "exit": CommandSpec(
        "exit", handlers.cmd_exit, parser.build_exit_parser, needs_table=False, help_text="Exit lsql"
    ),
}


def prepare(state: AppState, line: str) -> Optional[Union[CommandResult, PreparedCommand]]:
    """Parse and validate a command line. Returns None for a blank line, a CommandResult
    if parsing/validation failed (render it directly), or a PreparedCommand ready to run
    (check .confirm_message before calling execute())."""
    name, rest = parser.split_first_token(line)
    if name is None:
        return None

    spec = COMMANDS.get(name)
    if spec is None:
        return error(f"Unknown command: /{name}")

    if spec.needs_connection and state.connection is None:
        return error("No database open")

    if spec.needs_table and not state.current_table:
        return error("No table selected")

    if spec.raw_text:
        raw_sql = rest.strip()
        if not raw_sql:
            return error("Usage: /sql <SQL query>")
        return PreparedCommand(name=spec.name, run=lambda: spec.handler(state, raw_sql))

    try:
        tokens = parser.tokenize_rest(rest)
    except ValueError as e:
        return error(f"Could not parse command: {e}")

    p = spec.build_parser()
    try:
        args = p.parse_args(tokens)
    except ArgParseExit as e:
        return error(e.message)

    confirm_message = None
    if spec.destructive:
        fmt_kwargs = {"table": state.current_table}
        fmt_kwargs.update(vars(args))
        confirm_message = spec.confirm_template.format(**fmt_kwargs)

    return PreparedCommand(
        name=spec.name, run=lambda: spec.handler(state, args), confirm_message=confirm_message, slow=spec.slow
    )


def execute(prepared: PreparedCommand) -> CommandResult:
    """Run a prepared command, catching domain errors and rendering them as results."""
    try:
        return prepared.run()
    except CommandError as e:
        return error(str(e))
