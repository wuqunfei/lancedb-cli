"""dbx - A terminal GUI for managing LanceDB databases."""

from typing import Optional

import typer

from .tui.app import LanceDBApp

app = typer.Typer(help="dbx - A terminal GUI for managing LanceDB databases")


@app.command()
def launch(
    db_path: Optional[str] = typer.Argument(None, help="Path to a LanceDB database to open on launch"),
) -> None:
    """Launch the dbx terminal UI, optionally pre-connected to a database."""
    LanceDBApp(initial_db_path=db_path).run()


def main() -> None:
    """Entry point for the CLI."""
    app(prog_name="dbx")


if __name__ == "__main__":
    main()
