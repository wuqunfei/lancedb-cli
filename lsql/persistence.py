"""Hand-rolled JSON persistence for recently-opened database paths and command history."""

import json
from pathlib import Path
from typing import List, Optional


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


def _load_list(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _save_list(path: Path, items: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items))


class RecentDatabases:
    """Most-recently-used database paths, most recent first, deduplicated."""

    def __init__(self, path: Optional[Path] = None, max_items: int = 10):
        self.path = path or (default_config_dir() / "recent_databases.json")
        self.max_items = max_items

    def load(self) -> List[str]:
        return _load_list(self.path)

    def add(self, db_path: str) -> List[str]:
        items = [p for p in self.load() if p != db_path]
        items.insert(0, db_path)
        items = items[: self.max_items]
        _save_list(self.path, items)
        return items


class CommandHistory:
    """Submitted command-input lines, oldest first, capped to the most recent N."""

    def __init__(self, path: Optional[Path] = None, max_items: int = 500):
        self.path = path or (default_config_dir() / "command_history.json")
        self.max_items = max_items

    def load(self) -> List[str]:
        return _load_list(self.path)

    def add(self, command: str) -> List[str]:
        items = self.load()
        if not items or items[-1] != command:
            items.append(command)
        items = items[-self.max_items :]
        _save_list(self.path, items)
        return items
