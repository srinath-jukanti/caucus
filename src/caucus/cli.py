import typer

from caucus import __version__

app = typer.Typer(help="Caucus — AI agents deliberating on the record.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Caucus — AI agents deliberating on the record."""


@app.command()
def version() -> None:
    """Print the installed Caucus version."""
    typer.echo(f"caucus {__version__}")
