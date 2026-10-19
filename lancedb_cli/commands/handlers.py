"""Command handlers. Each returns a CommandResult and never touches a Console/terminal directly."""

import argparse

from ..core import db, rendering
from ..core.parsing import parse_set_clause
from . import results as r
from .results import AppState


def cmd_create(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    return r.ok_text(
        rendering.format_status(f"Opened database at '{args.path}'"),
        opened_db_path=args.path,
    )


def cmd_query(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    df = db.query_table(
        state.connection,
        state.current_table,
        limit=args.limit,
        where=args.where,
        select=args.select,
    )
    if len(df) == 0:
        return r.ok_text(rendering.format_status("No results", style="yellow"))
    if args.output == "json":
        return r.ok_text(rendering.dataframe_to_json(df))
    return r.ok_dataframe(df, title=f"Query results from {state.current_table}")


def cmd_schema(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    schema = db.get_schema(state.connection, state.current_table)
    return r.ok_text(rendering.format_schema(schema, state.current_table))


def cmd_sql(state: AppState, raw_sql: str) -> r.CommandResult:
    df = db.run_sql(state.connection, raw_sql)
    if len(df) == 0:
        return r.ok_text(rendering.format_status("No results", style="yellow"))
    return r.ok_dataframe(df, title="SQL Query Results")


def cmd_delete(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    deleted = db.delete_rows(state.connection, state.current_table, args.where)
    return r.ok_text(rendering.format_status(f"Deleted {deleted} row(s) from '{state.current_table}'"))


def cmd_empty(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    deleted = db.empty_table(state.connection, state.current_table)
    return r.ok_text(rendering.format_status(f"Emptied '{state.current_table}' — deleted {deleted} row(s)"))


def cmd_drop(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    table_name = state.current_table
    db.drop_table(state.connection, table_name)
    return r.ok_text(rendering.format_status(f"Dropped table '{table_name}'"), refresh_tables=True)


def cmd_update(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    values = parse_set_clause(args.set_clause)
    db.update_rows(state.connection, state.current_table, values, args.where)
    return r.ok_text(
        rendering.format_status(f"Updated rows in '{state.current_table}' where {args.where}")
    )


def cmd_load(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    df = db.load_csv(state.connection, args.path, args.table, overwrite=args.overwrite)
    return r.ok_text(
        rendering.format_status(f"Loaded {len(df)} row(s) into '{args.table}'"),
        refresh_tables=True,
    )


def cmd_dump(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    df = db.dump_csv(state.connection, state.current_table, args.path, overwrite=args.overwrite)
    return r.ok_text(rendering.format_status(f"Dumped {len(df)} row(s) from '{state.current_table}' to '{args.path}'"))


def cmd_refresh(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    db.refresh_sql_views(state.connection)
    return r.ok_text(rendering.format_status("Refreshed"), refresh_tables=True)


def cmd_exit(state: AppState, args: argparse.Namespace) -> r.CommandResult:
    return r.exit_result()
