"""Left panel (below the database panel): tables in the current database."""

from typing import List

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView


class TableListPanel(Vertical):
    """Lists the tables in the currently-open database."""

    class TableSelected(Message):
        def __init__(self, name: str) -> None:
            self.name = name
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.border_title = "Tables"

    def compose(self) -> ComposeResult:
        yield ListView(id="table-list")

    @staticmethod
    def _make_item(name: str) -> ListItem:
        item = ListItem(Label(name))
        item.table_name = name
        return item

    def set_tables(self, names: List[str]) -> None:
        list_view = self.query_one("#table-list", ListView)
        list_view.clear()
        for name in names:
            list_view.append(self._make_item(name))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.post_message(self.TableSelected(event.item.table_name))
