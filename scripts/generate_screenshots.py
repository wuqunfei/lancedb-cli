#!/usr/bin/env python
"""Regenerate the single README screenshot under docs/screenshots/.

Drives the real Textual app headlessly (Pilot) through opening the tcph test database,
selecting the customer table, and running a query, then exports the result as an SVG via
App.save_screenshot(). Run after any visible UI change:

    python scripts/generate_screenshots.py
"""

import asyncio
import tempfile
from pathlib import Path

from generate_tcph_db import generate as generate_tcph_db

from lsql import persistence
from lsql.tui.app import LanceDBApp

REPO_ROOT = Path(__file__).parent.parent
SCREENSHOTS_DIR = REPO_ROOT / "docs" / "screenshots"
SIZE = (120, 40)


def make_app(tmp_path: Path, initial_db_path: str = None) -> LanceDBApp:
    return LanceDBApp(
        initial_db_path=initial_db_path,
        connection_history=persistence.ConnectionHistory(path=tmp_path / "recent.json"),
        command_history=persistence.CommandHistory(path=tmp_path / "history.json"),
        last_embedding_model=persistence.LastEmbeddingModel(path=tmp_path / "last_model.json"),
    )


async def force_dark_theme(app: LanceDBApp, pilot) -> None:
    from lsql.tui.widgets.database_panel import DatabasePanel

    app.theme = "textual-dark"
    app.query_one(DatabasePanel).set_theme_icon(True)
    await pilot.pause()


async def shot(app: LanceDBApp, pilot, name: str) -> None:
    await pilot.pause(0.1)
    app.save_screenshot(filename=f"{name}.svg", path=str(SCREENSHOTS_DIR))
    print(f"saved {name}.svg")


async def scenario_tcph_customer_query(tmp_path: Path, db_path: str) -> None:
    app = make_app(tmp_path, initial_db_path=db_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await force_dark_theme(app, pilot)
        await pilot.click("#table-list ListItem")  # "customer" sorts first alphabetically
        await pilot.pause(0.2)

        await pilot.click("#command-input")
        inp = app.query_one("#command-input")
        inp.value = ""
        for ch in '/query --where "c_mktsegment = \'BUILDING\'" --select "c_custkey,c_name,c_acctbal,c_mktsegment" --limit 10':
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.3)
        await shot(app, pilot, "01-tcph-customer-query")


async def main() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "tcph.lance"
        generate_tcph_db(str(db_path), rows=50, scale_factor=0.01, overwrite=False)
        await scenario_tcph_customer_query(tmp_path / "s1", str(db_path))


if __name__ == "__main__":
    asyncio.run(main())
