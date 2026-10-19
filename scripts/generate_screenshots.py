#!/usr/bin/env python
"""Regenerate the README screenshots under docs/screenshots/.

Drives the real Textual app headlessly (Pilot) through a handful of scenarios and
exports each as an SVG via App.save_screenshot(). Run after any visible UI change:

    python scripts/generate_screenshots.py
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from lancedb_cli import persistence
from lancedb_cli.core import db
from lancedb_cli.tui.app import LanceDBApp

REPO_ROOT = Path(__file__).parent.parent
SCREENSHOTS_DIR = REPO_ROOT / "docs" / "screenshots"
SAMPLE_CSV = REPO_ROOT / "test_data" / "sample.csv"
SIZE = (120, 40)


def make_app(tmp_path: Path, initial_db_path: str = None) -> LanceDBApp:
    return LanceDBApp(
        initial_db_path=initial_db_path,
        recent_databases=persistence.RecentDatabases(path=tmp_path / "recent.json"),
        command_history=persistence.CommandHistory(path=tmp_path / "history.json"),
    )


async def force_dark_theme(app: LanceDBApp, pilot) -> None:
    from lancedb_cli.tui.widgets.database_panel import DatabasePanel

    app.theme = "textual-dark"
    app.query_one(DatabasePanel).set_theme_icon(True)
    await pilot.pause()


async def shot(app: LanceDBApp, pilot, name: str) -> None:
    await pilot.pause(0.1)
    app.save_screenshot(filename=f"{name}.svg", path=str(SCREENSHOTS_DIR))
    print(f"saved {name}.svg")


async def scenario_launch(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await force_dark_theme(app, pilot)
        await shot(app, pilot, "01-launch")


async def scenario_browser(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await force_dark_theme(app, pilot)
        await pilot.click("#open-db-button")
        await shot(app, pilot, "02-browse-database")
        await pilot.click("#browser-cancel")


async def scenario_table_and_query(tmp_path: Path, db_path: str) -> None:
    app = make_app(tmp_path, initial_db_path=db_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await force_dark_theme(app, pilot)
        await pilot.click("#table-list ListItem")
        await shot(app, pilot, "03-table-selected")

        await pilot.click("#command-input")
        for ch in "/d":
            await pilot.press(ch)
        await shot(app, pilot, "04-slash-suggestions")
        await pilot.press("escape")

        inp = app.query_one("#command-input")
        inp.value = ""
        for ch in "/schema":
            await pilot.press(ch)
        await pilot.press("enter")
        await shot(app, pilot, "05-schema")

        inp.value = ""
        for ch in "/help":
            await pilot.press(ch)
        await pilot.press("enter")
        await shot(app, pilot, "06-help")

        inp.value = ""
        for ch in "/drop":
            await pilot.press(ch)
        await pilot.press("enter")
        await shot(app, pilot, "07-confirm-destructive")
        await pilot.click("#confirm-no")


async def scenario_pagination(tmp_path: Path) -> None:
    db_path = tmp_path / "paginated.lance"
    conn = db.connect(str(db_path))
    conn.create_table(
        "events",
        data=pd.DataFrame({"id": range(1, 251), "event": [f"event-{i}" for i in range(1, 251)]}),
    )

    app = make_app(tmp_path, initial_db_path=str(db_path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await force_dark_theme(app, pilot)
        await pilot.click("#table-list ListItem")
        await pilot.pause(0.2)
        inp = app.query_one("#command-input")
        inp.value = ""
        for ch in "/query --limit 250":
            await pilot.press(ch)
        await pilot.press("enter")
        await shot(app, pilot, "08-pagination")


async def scenario_cell_detail(tmp_path: Path) -> None:
    from lancedb_cli.tui.widgets.results_panel import ResultsDataTable

    db_path = tmp_path / "longtext.lance"
    conn = db.connect(str(db_path))
    bio = (
        "Senior staff engineer with 12 years of experience across distributed systems, "
        "developer tooling, and ML infrastructure. Previously led the platform team at "
        "a Series C startup, scaling the data pipeline from 10K to 50M events/day."
    )
    conn.create_table("people", data=pd.DataFrame({"name": ["Alice Johnson", "Bob Smith"], "bio": [bio, "N/A"]}))

    app = make_app(tmp_path, initial_db_path=str(db_path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await force_dark_theme(app, pilot)
        await pilot.click("#table-list ListItem")
        await pilot.pause(0.2)
        table = app.query_one("#results-table", ResultsDataTable)
        bio_x = table.ordered_columns[0].width + 3
        await pilot.click("#results-table", offset=(bio_x, 1), times=2)
        await shot(app, pilot, "09-cell-detail")


async def main() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        await scenario_launch(tmp_path / "s1")
        await scenario_browser(tmp_path / "s2")

        db_path = tmp_path / "s3db.lance"
        conn = db.connect(str(db_path))
        db.load_csv(conn, str(SAMPLE_CSV), "employees")
        await scenario_table_and_query(tmp_path / "s3", str(db_path))

        await scenario_pagination(tmp_path / "s4")
        await scenario_cell_detail(tmp_path / "s5")


if __name__ == "__main__":
    asyncio.run(main())
