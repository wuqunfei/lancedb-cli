"""Modal for connecting to a database: a local folder, a direct object-storage URI
(s3://, gs://, az://), or a LanceDB Cloud/Enterprise db:// URI. Tests the connection in a
worker thread before dismissing, so a bad URI/credential shows an inline error instead of
silently handing back a request that will fail later."""

from pathlib import Path
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Collapsible,
    DirectoryTree,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    Select,
    TabbedContent,
    TabPane,
)

from ...core import db
from ...core.connection import PROVIDER_FIELDS, SECRET_FIELD_KEYS, ConnectionRequest
from ...core.exceptions import CommandError
from ...persistence import ConnectionEntry, ConnectionHistory
from .directory_browser_modal import FolderOnlyDirectoryTree

PROVIDER_OPTIONS = [("S3", "s3"), ("Azure", "azure"), ("GCS", "gcs")]
DEFAULT_PROVIDER = "s3"


def _recent_label(entry: ConnectionEntry) -> str:
    if entry.kind == "local":
        return f"[Local] {entry.uri}"
    if entry.kind == "object_storage":
        return f"[Object Storage] {entry.uri} ({entry.provider})"
    return f"[LanceDB Cloud] {entry.uri} ({entry.region or 'us-east-1'})"


class ConnectModal(ModalScreen[Optional[ConnectionRequest]]):
    """Lets the user build a ConnectionRequest for any of the 3 kinds of connection."""

    BINDINGS = [("escape", "cancel_", "Cancel")]

    def __init__(self, recent: ConnectionHistory, initial_path: str = ".") -> None:
        super().__init__()
        self._recent = recent
        self._local_selected_path = str(Path(initial_path).resolve())
        self._current_provider = DEFAULT_PROVIDER
        self._connecting = False

    def compose(self) -> ComposeResult:
        with Vertical(id="connect-dialog"):
            with TabbedContent(id="connect-tabs", initial="connect-tab-local"):
                with TabPane("Local Folder", id="connect-tab-local"):
                    yield Horizontal(
                        Button("Up", id="connect-local-up"),
                        Label("Select a database folder", id="connect-local-title"),
                        id="connect-local-header",
                    )
                    yield FolderOnlyDirectoryTree(self._local_selected_path, id="connect-local-tree")
                    yield Label(self._local_selected_path, id="connect-local-selected-path")
                with TabPane("Object Storage", id="connect-tab-object-storage"):
                    yield Input(placeholder="s3://bucket/path", id="connect-os-uri")
                    yield Select(
                        PROVIDER_OPTIONS,
                        id="connect-os-provider",
                        value=DEFAULT_PROVIDER,
                        allow_blank=False,
                    )
                    yield Vertical(id="connect-os-fields")
                with TabPane("LanceDB Cloud", id="connect-tab-cloud"):
                    yield Input(placeholder="db://my_database", id="connect-cloud-uri")
                    yield Input(placeholder="API key", password=True, id="connect-cloud-api-key")
                    yield Input(value="us-east-1", placeholder="Region", id="connect-cloud-region")
                    with Collapsible(title="Advanced", id="connect-cloud-advanced"):
                        yield Input(placeholder="Host override (optional)", id="connect-cloud-host-override")
            with Vertical(id="connect-recents"):
                yield Label("Recent connections")
                yield ListView(id="connect-recent-list")
            yield Label("", id="connect-error")
            with Horizontal(id="connect-buttons"):
                yield LoadingIndicator(id="connect-spinner")
                yield Button("Connect", id="connect-confirm", variant="primary")
                yield Button("Cancel", id="connect-cancel")

    async def on_mount(self) -> None:
        self.query_one("#connect-spinner", LoadingIndicator).display = False
        await self._rebuild_os_fields(DEFAULT_PROVIDER)
        self._load_recents()

    # -- Local Folder tab --------------------------------------------------

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self._local_selected_path = str(event.path)
        self.query_one("#connect-local-selected-path", Label).update(self._local_selected_path)

    def _go_up_local(self) -> None:
        tree = self.query_one("#connect-local-tree", FolderOnlyDirectoryTree)
        parent = str(Path(tree.path).resolve().parent)
        tree.path = parent
        self._local_selected_path = parent
        self.query_one("#connect-local-selected-path", Label).update(parent)

    # -- Object Storage tab --------------------------------------------------

    async def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "connect-os-provider":
            return
        await self._rebuild_os_fields(event.value)

    async def _rebuild_os_fields(self, provider: Optional[str]) -> None:
        self._current_provider = provider if provider in PROVIDER_FIELDS else None
        container = self.query_one("#connect-os-fields", Vertical)
        await container.remove_children()
        for label, key in PROVIDER_FIELDS.get(self._current_provider, []):
            await container.mount(Label(label))
            await container.mount(
                Input(placeholder=label, password=key in SECRET_FIELD_KEYS, id=f"connect-os-field-{key}")
            )

    # -- Recent connections --------------------------------------------------

    def _load_recents(self) -> None:
        list_view = self.query_one("#connect-recent-list", ListView)
        for entry in self._recent.load():
            item = ListItem(Label(_recent_label(entry)))
            item.entry = entry
            list_view.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        entry: ConnectionEntry = event.item.entry
        tabs = self.query_one("#connect-tabs", TabbedContent)
        if entry.kind == "local":
            tabs.active = "connect-tab-local"
            self._local_selected_path = entry.uri
            self.query_one("#connect-local-tree", FolderOnlyDirectoryTree).path = entry.uri
            self.query_one("#connect-local-selected-path", Label).update(entry.uri)
        elif entry.kind == "object_storage":
            tabs.active = "connect-tab-object-storage"
            self.query_one("#connect-os-uri", Input).value = entry.uri
            # Setting .value fires Select.Changed -> on_select_changed, which rebuilds
            # the provider-specific fields; no need to do it again here.
            self.query_one("#connect-os-provider", Select).value = entry.provider or DEFAULT_PROVIDER
        else:
            tabs.active = "connect-tab-cloud"
            self.query_one("#connect-cloud-uri", Input).value = entry.uri
            self.query_one("#connect-cloud-region", Input).value = entry.region or "us-east-1"
            if entry.host_override:
                self.query_one("#connect-cloud-advanced", Collapsible).collapsed = False
                self.query_one("#connect-cloud-host-override", Input).value = entry.host_override

    # -- Building the request, connecting --------------------------------------------------

    def _build_request(self) -> Optional[ConnectionRequest]:
        active = self.query_one("#connect-tabs", TabbedContent).active
        if active == "connect-tab-local":
            if not self._local_selected_path:
                self._set_error("Select a folder")
                return None
            return ConnectionRequest.local(self._local_selected_path)

        if active == "connect-tab-object-storage":
            uri = self.query_one("#connect-os-uri", Input).value.strip()
            if not uri:
                self._set_error("Enter a storage URI")
                return None
            storage_options = {}
            for _label, key in PROVIDER_FIELDS.get(self._current_provider, []):
                value = self.query_one(f"#connect-os-field-{key}", Input).value.strip()
                if value:
                    storage_options[key] = value
            return ConnectionRequest(
                kind="object_storage", uri=uri, provider=self._current_provider, storage_options=storage_options
            )

        if active == "connect-tab-cloud":
            uri = self.query_one("#connect-cloud-uri", Input).value.strip()
            api_key = self.query_one("#connect-cloud-api-key", Input).value.strip()
            if not uri or not api_key:
                self._set_error("Enter a database URI and API key")
                return None
            region = self.query_one("#connect-cloud-region", Input).value.strip() or "us-east-1"
            host_override = self.query_one("#connect-cloud-host-override", Input).value.strip() or None
            return ConnectionRequest(kind="cloud", uri=uri, api_key=api_key, region=region, host_override=host_override)

        return None

    def _attempt_connect(self) -> None:
        if self._connecting:
            return
        self._set_error("")
        request = self._build_request()
        if request is None:
            return
        self._connecting = True
        self.query_one("#connect-confirm", Button).disabled = True
        self.query_one("#connect-cancel", Button).disabled = True
        self.query_one("#connect-spinner", LoadingIndicator).display = True
        self._try_connect(request)

    @work(thread=True)
    def _try_connect(self, request: ConnectionRequest) -> None:
        try:
            conn = db.connect_request(request)
            db.list_tables(conn)  # connect() alone doesn't validate object-storage/cloud
            # credentials — only a real round-trip call does — so exercise one here.
        except CommandError as e:
            self.app.call_from_thread(self._show_error, str(e))
            return
        self.app.call_from_thread(self.dismiss, request)

    def _show_error(self, message: str) -> None:
        self._connecting = False
        self.query_one("#connect-confirm", Button).disabled = False
        self.query_one("#connect-cancel", Button).disabled = False
        self.query_one("#connect-spinner", LoadingIndicator).display = False
        self._set_error(message)

    def _set_error(self, message: str) -> None:
        self.query_one("#connect-error", Label).update(message)

    # -- Buttons / escape --------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect-local-up":
            self._go_up_local()
        elif event.button.id == "connect-confirm":
            self._attempt_connect()
        elif event.button.id == "connect-cancel":
            self.dismiss(None)

    def action_cancel_(self) -> None:
        if not self._connecting:
            self.dismiss(None)
