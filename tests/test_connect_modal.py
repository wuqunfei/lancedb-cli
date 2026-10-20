"""Headless Pilot-driven tests for the 3-way Connect modal (local / object storage /
LanceDB Cloud)."""

import json

import pytest
from textual.widgets import Collapsible, Input, Label, ListView, Select, TabbedContent

from lsql import persistence
from lsql.core.connection import ConnectionRequest
from lsql.core.exceptions import CommandError
from lsql.tui.app import LanceDBApp


def make_app(tmp_path, connection_history=None):
    return LanceDBApp(
        connection_history=connection_history or persistence.ConnectionHistory(path=tmp_path / "recent.json"),
        command_history=persistence.CommandHistory(path=tmp_path / "history.json"),
        last_embedding_model=persistence.LastEmbeddingModel(path=tmp_path / "last_model.json"),
    )


async def open_connect_modal(pilot):
    await pilot.click("#open-db-button")
    await pilot.pause(0.2)
    return pilot.app.screen_stack[-1]


async def test_object_storage_tab_defaults_to_s3_fields(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 45)) as pilot:
        modal = await open_connect_modal(pilot)
        modal.query_one("#connect-tabs", TabbedContent).active = "connect-tab-object-storage"
        await pilot.pause(0.1)
        assert modal.query_one("#connect-os-field-aws_access_key_id", Input)
        assert modal.query_one("#connect-os-field-aws_secret_access_key", Input)
        assert modal.query_one("#connect-os-field-aws_region", Input)


async def test_switching_provider_swaps_fields(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 45)) as pilot:
        modal = await open_connect_modal(pilot)
        modal.query_one("#connect-tabs", TabbedContent).active = "connect-tab-object-storage"
        await pilot.pause(0.1)

        modal.query_one("#connect-os-provider", Select).value = "azure"
        await pilot.pause(0.1)

        assert modal.query_one("#connect-os-field-account_name", Input)
        assert modal.query_one("#connect-os-field-account_key", Input)
        with pytest.raises(Exception):
            modal.query_one("#connect-os-field-aws_access_key_id", Input)


async def test_object_storage_tab_builds_correct_request(tmp_path, monkeypatch):
    from lsql.tui.widgets import connect_modal as cm

    monkeypatch.setattr(cm.db, "connect_request", lambda req: object())
    monkeypatch.setattr(cm.db, "list_tables", lambda conn: [])

    app = make_app(tmp_path)
    async with app.run_test(size=(120, 45)) as pilot:
        modal = await open_connect_modal(pilot)
        modal.query_one("#connect-tabs", TabbedContent).active = "connect-tab-object-storage"
        await pilot.pause(0.1)
        modal.query_one("#connect-os-uri", Input).value = "s3://my-bucket/db"
        modal.query_one("#connect-os-field-aws_access_key_id", Input).value = "AKIA123"
        modal.query_one("#connect-os-field-aws_secret_access_key", Input).value = "s3cr3t"
        modal.query_one("#connect-os-field-aws_region", Input).value = "us-west-2"
        await pilot.pause(0.1)

        await pilot.click("#connect-confirm")
        for _ in range(20):
            await pilot.pause(0.2)
            if len(app.screen_stack) == 1:
                break

        assert app.state.current_db_path == "s3://my-bucket/db"
        assert app.state.current_connection_kind == "object_storage"


async def test_cloud_tab_builds_correct_request_and_defaults_region(tmp_path, monkeypatch):
    from lsql.tui.widgets import connect_modal as cm

    monkeypatch.setattr(cm.db, "connect_request", lambda req: object())
    monkeypatch.setattr(cm.db, "list_tables", lambda conn: [])

    app = make_app(tmp_path)
    async with app.run_test(size=(120, 45)) as pilot:
        modal = await open_connect_modal(pilot)
        modal.query_one("#connect-tabs", TabbedContent).active = "connect-tab-cloud"
        await pilot.pause(0.1)
        modal.query_one("#connect-cloud-uri", Input).value = "db://mydb"
        modal.query_one("#connect-cloud-api-key", Input).value = "ldb_test"
        modal.query_one("#connect-cloud-advanced", Collapsible).collapsed = False
        modal.query_one("#connect-cloud-host-override", Input).value = "https://custom.example.com"
        await pilot.pause(0.1)

        await pilot.click("#connect-confirm")
        for _ in range(20):
            await pilot.pause(0.2)
            if len(app.screen_stack) == 1:
                break

        assert app.state.current_db_path == "db://mydb"
        assert app.state.current_connection_kind == "cloud"


async def test_connect_error_shows_inline_and_keeps_modal_open(tmp_path, monkeypatch):
    from lsql.tui.widgets import connect_modal as cm

    def fail(req):
        raise CommandError("bad credentials")

    monkeypatch.setattr(cm.db, "connect_request", fail)

    app = make_app(tmp_path)
    async with app.run_test(size=(120, 45)) as pilot:
        modal = await open_connect_modal(pilot)
        modal.query_one("#connect-tabs", TabbedContent).active = "connect-tab-cloud"
        await pilot.pause(0.1)
        modal.query_one("#connect-cloud-uri", Input).value = "db://mydb"
        modal.query_one("#connect-cloud-api-key", Input).value = "bad-key"
        await pilot.pause(0.1)

        await pilot.click("#connect-confirm")
        for _ in range(20):
            await pilot.pause(0.2)
            if not modal._connecting:
                break

        assert len(app.screen_stack) == 2
        assert "bad credentials" in str(modal.query_one("#connect-error", Label).render())
        assert app.state.current_db_path is None


async def test_recent_connections_list_prefills_nonsecret_fields_only(tmp_path):
    history = persistence.ConnectionHistory(path=tmp_path / "recent.json")
    history.add(
        ConnectionRequest(
            kind="object_storage",
            uri="s3://bucket/path",
            provider="s3",
            storage_options={"aws_access_key_id": "AKIA123", "aws_secret_access_key": "topsecret"},
        )
    )

    app = make_app(tmp_path, connection_history=history)
    async with app.run_test(size=(120, 45)) as pilot:
        modal = await open_connect_modal(pilot)
        list_view = modal.query_one("#connect-recent-list", ListView)
        assert len(list_view.children) == 1

        await pilot.click(list_view.children[0])
        await pilot.pause(0.2)

        assert modal.query_one("#connect-tabs", TabbedContent).active == "connect-tab-object-storage"
        assert modal.query_one("#connect-os-uri", Input).value == "s3://bucket/path"
        # Secrets must never be prefilled, even though they were part of the original request.
        assert modal.query_one("#connect-os-field-aws_access_key_id", Input).value == ""
        assert modal.query_one("#connect-os-field-aws_secret_access_key", Input).value == ""


async def test_old_bare_string_recent_format_still_loads(tmp_path):
    recent_path = tmp_path / "recent.json"
    recent_path.write_text(json.dumps(["/some/old/local/path"]))
    history = persistence.ConnectionHistory(path=recent_path)

    app = make_app(tmp_path, connection_history=history)
    async with app.run_test(size=(120, 45)) as pilot:
        modal = await open_connect_modal(pilot)
        list_view = modal.query_one("#connect-recent-list", ListView)
        assert len(list_view.children) == 1
        assert list_view.children[0].entry.kind == "local"
        assert list_view.children[0].entry.uri == "/some/old/local/path"


def test_connection_history_never_persists_secrets(tmp_path):
    history = persistence.ConnectionHistory(path=tmp_path / "recent.json")
    history.add(
        ConnectionRequest(
            kind="cloud", uri="db://mydb", api_key="ldb_super_secret", region="us-east-1", host_override=None
        )
    )
    raw = (tmp_path / "recent.json").read_text()
    assert "ldb_super_secret" not in raw
    assert "db://mydb" in raw
    assert "us-east-1" in raw
