"""Hand-rolled JSON persistence for recently-opened connections and command history."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Union

from .core.connection import ConnectionRequest


def default_config_dir() -> Path:
    new_dir = Path.home() / ".config" / "lsql"
    old_dirs = [Path.home() / ".config" / "lancedbx", Path.home() / ".config" / "lancedb-cli"]
    if not new_dir.exists():
        # One-time migration from the project's old names — preserves existing
        # recent-databases/command-history data instead of silently orphaning it.
        for old_dir in old_dirs:
            if old_dir.exists():
                try:
                    old_dir.rename(new_dir)
                except OSError:
                    pass
                break
    return new_dir


def _load_json_list(path: Path) -> List[Any]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _save_json_list(path: Path, items: List[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items))


@dataclass
class ConnectionEntry:
    """The non-secret parts of a connection, persisted for MRU recall. Never carries
    api_key/storage_options — those must always be re-typed."""

    kind: str  # "local" | "object_storage" | "cloud"
    uri: str
    provider: Optional[str] = None  # object_storage only
    region: Optional[str] = None  # cloud only
    host_override: Optional[str] = None  # cloud only

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "uri": self.uri}
        if self.provider is not None:
            d["provider"] = self.provider
        if self.region is not None:
            d["region"] = self.region
        if self.host_override is not None:
            d["host_override"] = self.host_override
        return d

    @staticmethod
    def from_json(item: Any) -> "ConnectionEntry":
        if isinstance(item, str):  # old bare-string format — every entry was a local path
            return ConnectionEntry(kind="local", uri=item)
        return ConnectionEntry(
            kind=item.get("kind", "local"),
            uri=item["uri"],
            provider=item.get("provider"),
            region=item.get("region"),
            host_override=item.get("host_override"),
        )

    @staticmethod
    def from_request(req: ConnectionRequest) -> "ConnectionEntry":
        return ConnectionEntry(
            kind=req.kind, uri=req.uri, provider=req.provider, region=req.region, host_override=req.host_override
        )


class ConnectionHistory:
    """Most-recently-used connections, most recent first, deduplicated by (kind, uri).
    Never stores secrets (api_key/storage_options) — only kind/uri/provider/region/
    host_override. Reads old bare-string recent_databases.json transparently (each string
    becomes a kind='local' entry) and writes the new object-array format from then on."""

    def __init__(self, path: Optional[Path] = None, max_items: int = 10):
        self.path = path or (default_config_dir() / "recent_databases.json")
        self.max_items = max_items

    def load(self) -> List[ConnectionEntry]:
        return [ConnectionEntry.from_json(item) for item in _load_json_list(self.path)]

    def add(self, request: Union[ConnectionEntry, ConnectionRequest, str]) -> List[ConnectionEntry]:
        if isinstance(request, ConnectionEntry):
            entry = request
        elif isinstance(request, str):
            entry = ConnectionEntry(kind="local", uri=request)
        else:
            entry = ConnectionEntry.from_request(request)
        items = [e for e in self.load() if not (e.kind == entry.kind and e.uri == entry.uri)]
        items.insert(0, entry)
        items = items[: self.max_items]
        _save_json_list(self.path, [e.to_dict() for e in items])
        return items


class LastEmbeddingModel:
    """The most recently 'Set' embedding model name, if any — stored as a 1-item list
    via the same _load_json_list/_save_json_list helpers ConnectionHistory/CommandHistory use."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or (default_config_dir() / "last_embedding_model.json")

    def load(self) -> Optional[str]:
        items = _load_json_list(self.path)
        return items[0] if items else None

    def set(self, model_name: str) -> None:
        _save_json_list(self.path, [model_name])


class CommandHistory:
    """Submitted command-input lines, oldest first, capped to the most recent N."""

    def __init__(self, path: Optional[Path] = None, max_items: int = 500):
        self.path = path or (default_config_dir() / "command_history.json")
        self.max_items = max_items

    def load(self) -> List[str]:
        return _load_json_list(self.path)

    def add(self, command: str) -> List[str]:
        items = self.load()
        if not items or items[-1] != command:
            items.append(command)
        items = items[-self.max_items :]
        _save_json_list(self.path, items)
        return items
