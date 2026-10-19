"""Data types shared between command handlers, the dispatcher, and the TUI."""

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
from rich.console import RenderableType
from rich.text import Text


@dataclass
class AppState:
    """The bits of UI state command handlers need: the live connection and current selections."""

    connection: Any = None
    current_db_path: Optional[str] = None
    current_table: Optional[str] = None
    current_embedding_model: Optional[str] = None


@dataclass
class CommandResult:
    kind: str  # "dataframe" | "text" | "error" | "cancelled" | "exit"
    dataframe: Optional[pd.DataFrame] = None
    title: str = "Results"
    renderable: Optional[RenderableType] = None
    refresh_tables: bool = False
    opened_db_path: Optional[str] = None  # set by /create — tells the TUI to switch databases


def ok_dataframe(df: pd.DataFrame, title: str = "Results", refresh_tables: bool = False) -> CommandResult:
    return CommandResult(kind="dataframe", dataframe=df, title=title, refresh_tables=refresh_tables)


def ok_text(
    renderable: RenderableType, refresh_tables: bool = False, opened_db_path: Optional[str] = None
) -> CommandResult:
    return CommandResult(
        kind="text", renderable=renderable, refresh_tables=refresh_tables, opened_db_path=opened_db_path
    )


def error(message: str) -> CommandResult:
    return CommandResult(kind="error", renderable=Text(message, style="red"))


def cancelled(message: str = "Operation cancelled") -> CommandResult:
    return CommandResult(kind="cancelled", renderable=Text(message, style="yellow"))


def exit_result() -> CommandResult:
    return CommandResult(kind="exit")


@dataclass
class PreparedCommand:
    """A parsed, validated command ready to run. `confirm_message` is set only for
    destructive commands — the caller must get confirmation before calling execute()."""

    name: str
    run: Any  # zero-arg callable returning a CommandResult
    confirm_message: Optional[str] = None
