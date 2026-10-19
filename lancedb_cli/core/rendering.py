"""Rich renderable builders. No module-level Console — callers decide where output goes."""

from typing import Any

import pandas as pd
from rich.console import RenderableType
from rich.json import JSON
from rich.table import Table
from rich.text import Text

from .parsing import truncate_value


def dataframe_to_rich_table(df: pd.DataFrame, title: str) -> Table:
    """Build a Rich Table renderable from a DataFrame, truncating long field values."""
    table = Table(title=title)
    for col in df.columns:
        table.add_column(str(col), style="cyan")
    for _, row in df.iterrows():
        table.add_row(*[truncate_value(v) for v in row])
    return table


def dataframe_to_json(df: pd.DataFrame) -> JSON:
    """Build a Rich JSON renderable from a DataFrame."""
    return JSON(df.to_json(orient="records"))


def render_dataframe(df: pd.DataFrame, title: str = "Results", output_format: str = "table") -> RenderableType:
    """Render a DataFrame as a Rich renderable in the given format ('table' or 'json')."""
    if output_format == "json":
        return dataframe_to_json(df)
    return dataframe_to_rich_table(df, title)


def format_schema(schema: Any, table_name: str) -> RenderableType:
    """Build a Rich renderable describing a table's schema."""
    return Text.from_markup(f"[bold cyan]Schema for {table_name}:[/bold cyan]\n\n") + Text(str(schema))


def format_status(message: str, style: str = "green") -> RenderableType:
    """Build a simple styled status/message renderable."""
    return Text(message, style=style)
