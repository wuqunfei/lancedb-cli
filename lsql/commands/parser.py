"""Slash-command line parsing: tokenizing + per-command argparse factories.

argparse normally writes to real stderr and calls sys.exit() on bad input, which would
kill the whole Textual app. SilentArgumentParser raises ArgParseExit instead, which the
dispatcher catches and renders as an error in the results panel.
"""

import argparse
import shlex
from typing import List, Optional, Tuple


class ArgParseExit(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class SilentArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ArgParseExit(f"{self.prog}: {message}")

    def exit(self, status: int = 0, message: Optional[str] = None) -> None:
        raise ArgParseExit(message or "")


def split_first_token(line: str) -> Tuple[Optional[str], str]:
    """Split a raw input line into (command_name, rest_of_line) using plain whitespace
    splitting (not shlex) — the command name never contains quotes, and this lets /sql's
    raw SQL text (which may contain unbalanced quotes, e.g. "O'Brien") pass through
    untouched. command_name is lowercased and has its leading '/' stripped; returns
    (None, "") for a blank line."""
    parts = line.strip().split(None, 1)
    if not parts:
        return None, ""
    name = parts[0].lstrip("/").lower()
    rest = parts[1] if len(parts) > 1 else ""
    return name, rest


def tokenize_rest(rest: str) -> List[str]:
    """Shlex-tokenize everything after the command name, for flag-style commands."""
    return shlex.split(rest)


def _new_parser(prog: str) -> SilentArgumentParser:
    return SilentArgumentParser(prog=f"/{prog}", add_help=False)


def build_query_parser() -> SilentArgumentParser:
    p = _new_parser("query")
    p.add_argument("--where", default=None, help="WHERE clause filter (SQL syntax)")
    p.add_argument("--limit", type=int, default=10, help="Number of rows to return")
    p.add_argument("--select", default=None, help="Columns to select (comma-separated)")
    p.add_argument("--output", choices=["table", "json"], default="table", help="Output format")
    return p


def build_schema_parser() -> SilentArgumentParser:
    return _new_parser("schema")


def build_create_parser() -> SilentArgumentParser:
    p = _new_parser("create")
    p.add_argument("--path", required=True, help="Path to create (or open) a database at")
    return p


def build_help_parser() -> SilentArgumentParser:
    p = _new_parser("help")
    p.add_argument(
        "command_name", nargs="?", default=None, help="Name of a command to show detailed help for"
    )
    return p


def build_delete_parser() -> SilentArgumentParser:
    p = _new_parser("delete")
    p.add_argument("--where", required=True, help="WHERE clause to specify rows to delete")
    return p


def build_empty_parser() -> SilentArgumentParser:
    return _new_parser("empty")


def build_drop_parser() -> SilentArgumentParser:
    return _new_parser("drop")


def build_update_parser() -> SilentArgumentParser:
    p = _new_parser("update")
    p.add_argument("--set-clause", required=True, dest="set_clause", help="col=value pairs, comma-separated")
    p.add_argument("--where", required=True, help="WHERE clause to specify rows to update")
    return p


def build_load_parser() -> SilentArgumentParser:
    p = _new_parser("load")
    p.add_argument("--path", required=True, help="Path to CSV file to load")
    p.add_argument("--table", required=True, help="Name of the new table to create")
    p.add_argument("--overwrite", action="store_true", help="Overwrite table if it exists")
    return p


def build_embedding_parser() -> SilentArgumentParser:
    p = _new_parser("embedding")
    p.add_argument("--table", required=True, help="Name of the table to compute embeddings for")
    p.add_argument(
        "--source",
        required=True,
        help="Source column(s) to embed, comma-separated for multiple (e.g. 'title,body')",
    )
    p.add_argument(
        "--target",
        default=None,
        help=(
            "Target vector column(s), comma-separated, paired positionally with --source. "
            "Defaults to 'vector' for a single --source column, or '<source>_vector' per "
            "column when --source names multiple columns"
        ),
    )
    p.add_argument(
        "--model",
        default=None,
        help="sentence-transformers model name (default: all-MiniLM-L6-v2, or whatever's "
        "set in the Embedding Model panel)",
    )
    p.add_argument("--overwrite", action="store_true", help="Overwrite target column(s) if they already exist")
    return p


def build_index_parser() -> SilentArgumentParser:
    p = _new_parser("index")
    p.add_argument("--column", required=True, help="Text column to build a full-text index on")
    return p


def build_search_parser() -> SilentArgumentParser:
    p = _new_parser("search")
    p.add_argument("--mode", required=True, choices=["vector", "fts", "hybrid"], help="Search mode")
    p.add_argument("--query", required=True, help="Search query (embedded for vector/hybrid, keyword for fts/hybrid)")
    p.add_argument(
        "--vector-column",
        default=None,
        dest="vector_column",
        help="Vector column to search (vector/hybrid). Auto-inferred if the table has exactly one",
    )
    p.add_argument(
        "--text-column",
        default=None,
        dest="text_column",
        help="Text column to search (fts/hybrid) — required, auto-creates its FTS index on first use",
    )
    p.add_argument("--model", default=None, help="sentence-transformers model name for vector/hybrid search")
    p.add_argument("--limit", type=int, default=10, help="Number of rows to return")
    p.add_argument("--where", default=None, help="WHERE clause filter (SQL syntax)")
    p.add_argument("--select", default=None, help="Columns to select (comma-separated)")
    return p


def build_dump_parser() -> SilentArgumentParser:
    p = _new_parser("dump")
    p.add_argument("--path", required=True, help="Output CSV file path")
    p.add_argument("--overwrite", action="store_true", help="Overwrite output file if it exists")
    return p


def build_refresh_parser() -> SilentArgumentParser:
    return _new_parser("refresh")


def build_exit_parser() -> SilentArgumentParser:
    return _new_parser("exit")
