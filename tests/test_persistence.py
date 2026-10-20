import json
from unittest.mock import patch

from lsql.core.connection import ConnectionRequest
from lsql.persistence import CommandHistory, ConnectionEntry, ConnectionHistory, LastEmbeddingModel, default_config_dir


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


def test_connection_history_empty_by_default(tmp_path):
    ch = ConnectionHistory(path=tmp_path / "recent.json")
    assert ch.load() == []


def test_connection_history_add_puts_most_recent_first(tmp_path):
    ch = ConnectionHistory(path=tmp_path / "recent.json")
    ch.add("/db/a")
    ch.add("/db/b")
    assert ch.load() == [
        ConnectionEntry(kind="local", uri="/db/b"),
        ConnectionEntry(kind="local", uri="/db/a"),
    ]


def test_connection_history_add_dedupes_and_moves_to_front(tmp_path):
    ch = ConnectionHistory(path=tmp_path / "recent.json")
    ch.add("/db/a")
    ch.add("/db/b")
    ch.add("/db/a")
    assert ch.load() == [
        ConnectionEntry(kind="local", uri="/db/a"),
        ConnectionEntry(kind="local", uri="/db/b"),
    ]


def test_connection_history_caps_to_max_items(tmp_path):
    ch = ConnectionHistory(path=tmp_path / "recent.json", max_items=2)
    ch.add("/db/a")
    ch.add("/db/b")
    ch.add("/db/c")
    assert ch.load() == [
        ConnectionEntry(kind="local", uri="/db/c"),
        ConnectionEntry(kind="local", uri="/db/b"),
    ]


def test_connection_history_persists_across_instances(tmp_path):
    path = tmp_path / "recent.json"
    ConnectionHistory(path=path).add("/db/a")
    assert ConnectionHistory(path=path).load() == [ConnectionEntry(kind="local", uri="/db/a")]


def test_connection_history_loads_old_bare_string_format(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text(json.dumps(["/db/a"]))
    assert ConnectionHistory(path=path).load() == [ConnectionEntry(kind="local", uri="/db/a")]


def test_connection_history_add_object_storage_entry_roundtrips_without_secrets(tmp_path):
    path = tmp_path / "recent.json"
    ch = ConnectionHistory(path=path)
    ch.add(
        ConnectionRequest(
            kind="object_storage",
            uri="s3://bucket/path",
            provider="s3",
            storage_options={"aws_access_key_id": "AKIA123", "aws_secret_access_key": "s3cr3t"},
        )
    )
    raw = path.read_text()
    assert "AKIA123" not in raw
    assert "s3cr3t" not in raw
    assert ch.load() == [ConnectionEntry(kind="object_storage", uri="s3://bucket/path", provider="s3")]


def test_connection_history_add_cloud_entry_persists_region_and_host_override_not_api_key(tmp_path):
    path = tmp_path / "recent.json"
    ch = ConnectionHistory(path=path)
    ch.add(
        ConnectionRequest(
            kind="cloud",
            uri="db://mydb",
            api_key="ldb_super_secret",
            region="us-west-2",
            host_override="https://custom.example.com",
        )
    )
    raw = path.read_text()
    assert "ldb_super_secret" not in raw
    assert ch.load() == [
        ConnectionEntry(
            kind="cloud", uri="db://mydb", region="us-west-2", host_override="https://custom.example.com"
        )
    ]


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
    assert ConnectionHistory(path=path).load() == []


def test_last_embedding_model_empty_by_default(tmp_path):
    lem = LastEmbeddingModel(path=tmp_path / "last_model.json")
    assert lem.load() is None


def test_last_embedding_model_set_then_load(tmp_path):
    lem = LastEmbeddingModel(path=tmp_path / "last_model.json")
    lem.set("org/model-a")
    assert lem.load() == "org/model-a"


def test_last_embedding_model_set_overwrites_previous(tmp_path):
    lem = LastEmbeddingModel(path=tmp_path / "last_model.json")
    lem.set("org/model-a")
    lem.set("org/model-b")
    assert lem.load() == "org/model-b"


def test_last_embedding_model_persists_across_instances(tmp_path):
    path = tmp_path / "last_model.json"
    LastEmbeddingModel(path=path).set("org/model-a")
    assert LastEmbeddingModel(path=path).load() == "org/model-a"
