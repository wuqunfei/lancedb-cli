from lancedb_cli.persistence import CommandHistory, RecentDatabases


def test_recent_databases_empty_by_default(tmp_path):
    rd = RecentDatabases(path=tmp_path / "recent.json")
    assert rd.load() == []


def test_recent_databases_add_puts_most_recent_first(tmp_path):
    rd = RecentDatabases(path=tmp_path / "recent.json")
    rd.add("/db/a")
    rd.add("/db/b")
    assert rd.load() == ["/db/b", "/db/a"]


def test_recent_databases_add_dedupes_and_moves_to_front(tmp_path):
    rd = RecentDatabases(path=tmp_path / "recent.json")
    rd.add("/db/a")
    rd.add("/db/b")
    rd.add("/db/a")
    assert rd.load() == ["/db/a", "/db/b"]


def test_recent_databases_caps_to_max_items(tmp_path):
    rd = RecentDatabases(path=tmp_path / "recent.json", max_items=2)
    rd.add("/db/a")
    rd.add("/db/b")
    rd.add("/db/c")
    assert rd.load() == ["/db/c", "/db/b"]


def test_recent_databases_persists_across_instances(tmp_path):
    path = tmp_path / "recent.json"
    RecentDatabases(path=path).add("/db/a")
    assert RecentDatabases(path=path).load() == ["/db/a"]


def test_command_history_empty_by_default(tmp_path):
    ch = CommandHistory(path=tmp_path / "history.json")
    assert ch.load() == []


def test_command_history_add_appends_in_order(tmp_path):
    ch = CommandHistory(path=tmp_path / "history.json")
    ch.add("/schema")
    ch.add("/query --limit 5")
    assert ch.load() == ["/schema", "/query --limit 5"]


def test_command_history_skips_consecutive_duplicates(tmp_path):
    ch = CommandHistory(path=tmp_path / "history.json")
    ch.add("/refresh")
    ch.add("/refresh")
    assert ch.load() == ["/refresh"]


def test_command_history_caps_to_max_items(tmp_path):
    ch = CommandHistory(path=tmp_path / "history.json", max_items=2)
    ch.add("one")
    ch.add("two")
    ch.add("three")
    assert ch.load() == ["two", "three"]


def test_load_ignores_corrupt_file(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text("not json")
    assert RecentDatabases(path=path).load() == []
