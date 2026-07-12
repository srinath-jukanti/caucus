import json
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
def deliberate(
    subject: str,
    log: Path = Path("decisions.jsonl"),
    evidence: Path | None = None,
) -> None:
    """Convene the analyst panel on SUBJECT and append the outcome to the log.

    Agents run through the locally authenticated Claude Code CLI; EVIDENCE is
    an optional JSON file holding a list of {source, ref, ...} objects.
    """
    from caucus.backends import ClaudeCodeBackend
    from caucus.engine import Deliberation

    items = json.loads(evidence.read_text()) if evidence else []
    if not isinstance(items, list):
        typer.echo("evidence file must contain a JSON list of objects", err=True)
        raise typer.Exit(2)

    record = Deliberation(backend=ClaudeCodeBackend(), log=DecisionLog(log)).run(subject, items)
    typer.echo(f"DECISION ({record.confidence:.0%} confidence): {record.decision}")
    for position in record.dissent:
        typer.echo(f"DISSENT [{position['agent']}]: {position['summary']}")
    typer.echo(f"On the record: {log} (hash {record.hash[:12]}…)")


@app.command()
def verify(path: Path) -> None:
    """Verify the hash chain of a decision log (see SPEC.md)."""
    result = DecisionLog(path).verify()
    if result.ok:
        anchor = (
            "anchored to head checkpoint"
            if result.anchored
            else "UNANCHORED — no head checkpoint, tail truncation would not be detectable"
        )
        typer.echo(f"OK — {result.count} records, chain intact ({anchor})")
    else:
        typer.echo(
            f"TAMPERED — record {result.broken_at}: {result.reason} "
            f"({result.count} records verified before the break)",
            err=True,
        )
        raise typer.Exit(1)
