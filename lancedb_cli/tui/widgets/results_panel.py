"""Bottom-right panel: shows the most recent command's output only, never a scrollback.

Row-shaped results are paginated (default 100 rows/page) rather than all loaded into the
DataTable at once — within a page, the DataTable's native horizontal/vertical scrollbars
still kick in if a page has more columns or rows than fit on screen.
"""

from math import ceil
from typing import Optional

import pandas as pd
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import Button, DataTable, Static

from ...commands.results import CommandResult
from ...core.parsing import truncate_value
from .cell_detail_modal import CellDetailModal

DEFAULT_PAGE_SIZE = 100


class ResultsDataTable(DataTable):
    """A DataTable that reports double-clicked cells, since the public `on_click`
    convention hook runs before DataTable's own cursor-position update — we track the
    current cell via CellHighlighted instead of reading cursor_coordinate in on_click."""

    class CellDoubleClicked(Message):
        def __init__(self, coordinate: Coordinate) -> None:
            self.coordinate = coordinate
            super().__init__()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_highlighted = Coordinate(0, 0)

    def on_data_table_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        self._last_highlighted = event.coordinate

    def on_click(self, event: events.Click) -> None:
        if event.chain >= 2:
            self.post_message(self.CellDoubleClicked(self._last_highlighted))


class ResultsPanel(Vertical):
    def __init__(self, page_size: int = DEFAULT_PAGE_SIZE, **kwargs):
        super().__init__(**kwargs)
        self.border_title = "Results"
        self.page_size = page_size
        self._df: Optional[pd.DataFrame] = None
        self._page = 0

    def compose(self) -> ComposeResult:
        yield Static(id="results-static")
        yield ResultsDataTable(id="results-table")
        yield Horizontal(
            Button("< Prev", id="prev-page-button"),
            Static(id="pagination-label"),
            Button("Next >", id="next-page-button"),
            id="pagination-bar",
        )

    def on_mount(self) -> None:
        self.query_one("#results-table", ResultsDataTable).display = False
        self.query_one("#pagination-bar").display = False

    @property
    def _total_pages(self) -> int:
        if self._df is None or len(self._df) == 0:
            return 1
        return ceil(len(self._df) / self.page_size)

    def show_result(self, result: CommandResult) -> None:
        static = self.query_one("#results-static", Static)

        if result.kind == "dataframe" and result.dataframe is not None:
            self._df = result.dataframe
            self._page = 0
            static.display = False
            self._render_page()
        else:
            self._df = None
            self.query_one("#results-table", ResultsDataTable).display = False
            self.query_one("#pagination-bar").display = False
            static.display = True
            static.update(result.renderable if result.renderable is not None else "")

    def _render_page(self) -> None:
        df = self._df
        table = self.query_one("#results-table", ResultsDataTable)
        table.clear(columns=True)
        table.add_columns(*[str(c) for c in df.columns])

        start = self._page * self.page_size
        end = start + self.page_size
        for _, row in df.iloc[start:end].iterrows():
            table.add_row(*[truncate_value(v) for v in row])
        table.display = True

        total_pages = self._total_pages
        pagination_bar = self.query_one("#pagination-bar")
        pagination_bar.display = len(df) > 0
        self.query_one("#pagination-label", Static).update(
            f"Page {self._page + 1}/{total_pages} ({len(df)} rows)"
        )
        self.query_one("#prev-page-button", Button).disabled = self._page == 0
        self.query_one("#next-page-button", Button).disabled = self._page >= total_pages - 1

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prev-page-button" and self._page > 0:
            self._page -= 1
            self._render_page()
        elif event.button.id == "next-page-button" and self._page < self._total_pages - 1:
            self._page += 1
            self._render_page()

    @on(ResultsDataTable.CellDoubleClicked)
    def handle_cell_double_clicked(self, event: ResultsDataTable.CellDoubleClicked) -> None:
        if self._df is None:
            return
        row_idx = self._page * self.page_size + event.coordinate.row
        col_idx = event.coordinate.column
        if row_idx >= len(self._df) or not (0 <= col_idx < len(self._df.columns)):
            return
        column_name = str(self._df.columns[col_idx])
        value = self._df.iloc[row_idx, col_idx]
        self.app.push_screen(CellDetailModal(column_name, value))

    def clear(self) -> None:
        self._df = None
        self._page = 0
        table = self.query_one("#results-table", ResultsDataTable)
        static = self.query_one("#results-static", Static)
        table.clear(columns=True)
        table.display = False
        self.query_one("#pagination-bar").display = False
        static.update("")
        static.display = True
