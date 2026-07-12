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
    config: Path | None = None,
    backend: str = "claude",
    model: str | None = None,
    base_url: str | None = None,
) -> None:
    """Convene the analyst panel on SUBJECT and append the outcome to the log.

    Configuration comes from --config (or ./config.yaml when present): log
    path, backend, and panel — see config.example.yaml. Ad-hoc flags:
    --backend 'claude' (default — the locally authenticated Claude Code CLI,
    no API key) or 'openai' (any OpenAI-compatible provider via --model and
    --base-url; key read from OPENAI_API_KEY). Flags and --config are
    mutually exclusive. EVIDENCE is an optional JSON file holding a list of
    {source, ref, ...} objects.
    """
    from caucus.config import Config, ConfigError
    from caucus.backends import ClaudeCodeBackend, OpenAICompatibleBackend
    from caucus.engine import DEFAULT_PANEL, Deliberation

    items = json.loads(evidence.read_text()) if evidence else []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        typer.echo("evidence file must contain a JSON list of objects", err=True)
        raise typer.Exit(2)

    config_path = (
        config if config else Path("config.yaml") if Path("config.yaml").exists() else None
    )
    panel = list(DEFAULT_PANEL)
    if config_path is not None:
        if backend != "claude" or model or base_url:
            typer.echo(
                "--backend/--model/--base-url cannot be combined with a config file", err=True
            )
            raise typer.Exit(2)
        try:
            loaded = Config.load(config_path)
        except ConfigError as err:
            typer.echo(f"invalid config {config_path}: {err}", err=True)
            raise typer.Exit(2) from err
        agent_backend = loaded.backend
        panel = loaded.panel
        if log == Path("decisions.jsonl"):
            log = loaded.log
    elif backend == "claude":
        agent_backend = ClaudeCodeBackend()
    elif backend == "openai":
        if not model:
            typer.echo("--model is required with --backend openai", err=True)
            raise typer.Exit(2)
        agent_backend = OpenAICompatibleBackend(model=model, base_url=base_url)
    else:
        typer.echo(f"unknown backend {backend!r} (expected 'claude' or 'openai')", err=True)
        raise typer.Exit(2)

    record = Deliberation(backend=agent_backend, log=DecisionLog(log), panel=panel).run(
        subject, items
    )
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
