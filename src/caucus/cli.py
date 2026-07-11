from pathlib import Path

import typer

from caucus import __version__
from caucus.record import DecisionLog

app = typer.Typer(help="Caucus — AI agents deliberating on the record.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Caucus — AI agents deliberating on the record."""


@app.command()
def version() -> None:
    """Print the installed Caucus version."""
    typer.echo(f"caucus {__version__}")


@app.command()
def verify(path: Path) -> None:
    """Verify the hash chain of a decision log (see SPEC.md)."""
    result = DecisionLog(path).verify()
    if result.ok:
        typer.echo(f"OK — {result.count} records, chain intact")
    else:
        typer.echo(
            f"TAMPERED — record {result.broken_at}: {result.reason} "
            f"({result.count} records verified before the break)",
            err=True,
        )
        raise typer.Exit(1)
