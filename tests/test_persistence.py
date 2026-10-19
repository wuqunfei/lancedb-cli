from unittest.mock import patch

from lsql.persistence import CommandHistory, RecentDatabases, default_config_dir


def test_default_config_dir_migrates_old_directory(tmp_path):
    home = tmp_path / "home"
    old_dir = home / ".config" / "lancedb-cli"
    old_dir.mkdir(parents=True)
    (old_dir / "recent_databases.json").write_text('["/db/a"]')

    with patch("lsql.persistence.Path.home", return_value=home):
        config_dir = default_config_dir()

    assert config_dir == home / ".config" / "lsql"
    assert config_dir.exists()
    assert not old_dir.exists()
    assert (config_dir / "recent_databases.json").read_text() == '["/db/a"]'


def test_default_config_dir_migrates_from_lancedbx_directory(tmp_path):
    home = tmp_path / "home"
    old_dir = home / ".config" / "lancedbx"
    old_dir.mkdir(parents=True)
    (old_dir / "recent_databases.json").write_text('["/db/a"]')

    with patch("lsql.persistence.Path.home", return_value=home):
        config_dir = default_config_dir()

    assert config_dir == home / ".config" / "lsql"
    assert config_dir.exists()
    assert not old_dir.exists()
    assert (config_dir / "recent_databases.json").read_text() == '["/db/a"]'


def test_default_config_dir_prefers_existing_new_dir_over_migrating(tmp_path):
    home = tmp_path / "home"
    old_dir = home / ".config" / "lancedb-cli"
    old_dir.mkdir(parents=True)
    (old_dir / "recent_databases.json").write_text('["/old"]')
    new_dir = home / ".config" / "lsql"
    new_dir.mkdir(parents=True)
    (new_dir / "recent_databases.json").write_text('["/new"]')

    with patch("lsql.persistence.Path.home", return_value=home):
        config_dir = default_config_dir()

    assert (config_dir / "recent_databases.json").read_text() == '["/new"]'
    assert old_dir.exists()  # untouched, not merged or deleted


def test_default_config_dir_with_no_old_dir(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    with patch("lsql.persistence.Path.home", return_value=home):
        config_dir = default_config_dir()
    assert config_dir == home / ".config" / "lsql"


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
