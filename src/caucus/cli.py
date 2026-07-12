import json
from pathlib import Path

import typer

from caucus import __version__
from caucus.record import DecisionLog

app = typer.Typer(help="Caucus — AI agents deliberating on the record.", no_args_is_help=True)
intents_app = typer.Typer(
    help="Manage durable intents — standing plans deliberations must respect."
)
app.add_typer(intents_app, name="intents", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Caucus — AI agents deliberating on the record."""


def _configured_evidence(loaded) -> list[dict]:
    """Collect configured evidence (external sources + open intents), fail-closed."""
    items: list[dict] = []
    if loaded.evidence_sources:
        from caucus.evidence import EvidenceError, collect

        try:
            # Deterministic computation stays outside the model: sources print
            # JSON evidence, and a broken source aborts the run rather than
            # deliberating on silently missing data.
            items += collect(loaded.evidence_sources)
        except EvidenceError as err:
            typer.echo(str(err), err=True)
            raise typer.Exit(2) from err
    if loaded.intents is not None:
        from caucus.intents import IntentStore

        # A mistyped path must not silently become an empty store — a panel
        # missing its standing plans is confidently wrong, which is the exact
        # failure this feature exists to prevent.
        if not loaded.intents.exists():
            typer.echo(
                f"configured intents store {loaded.intents} does not exist — "
                "create it with 'caucus intents add'",
                err=True,
            )
            raise typer.Exit(2)
        items += IntentStore(loaded.intents).as_evidence()
    return items


def _intents_store(db: Path | None):
    """Resolve the intent store: --db flag, else config.yaml's 'intents', else ./intents.db."""
    from caucus.config import Config
    from caucus.intents import IntentStore

    if db is None and Path("config.yaml").exists():
        db = Config.load(Path("config.yaml")).intents
    return IntentStore(db or Path("intents.db"))


@intents_app.command("add")
def intents_add(
    name: str,
    db: Path | None = None,
    direction: str = "",
    target: str = "",
    pacing: str = "",
    cadence_days: int | None = None,
    last_acted: str | None = None,
    notes: str = "",
) -> None:
    """Record a new standing intent."""
    intent = _intents_store(db).add(
        name=name,
        direction=direction,
        target=target,
        pacing=pacing,
        cadence_days=cadence_days,
        last_acted=last_acted,
        notes=notes,
    )
    typer.echo(f"#{intent.id} {intent.summary()}")


@intents_app.command("list")
def intents_list(db: Path | None = None, status: str | None = None) -> None:
    """List intents, optionally filtered by status (open/paused/done)."""
    intents = _intents_store(db).list(status=status)
    if not intents:
        typer.echo("(no intents)")
    for intent in intents:
        typer.echo(f"#{intent.id} {intent.summary()}")


@intents_app.command("update")
def intents_update(
    intent_id: int,
    db: Path | None = None,
    status: str | None = None,
    last_acted: str | None = None,
    target: str | None = None,
    pacing: str | None = None,
    cadence_days: int | None = None,
    notes: str | None = None,
) -> None:
    """Update fields on an intent (e.g. --status done, --last-acted 2026-07-10)."""
    fields = {
        key: value
        for key, value in {
            "status": status,
            "last_acted": last_acted,
            "target": target,
            "pacing": pacing,
            "cadence_days": cadence_days,
            "notes": notes,
        }.items()
        if value is not None
    }
    try:
        intent = _intents_store(db).update(intent_id, **fields)
    except (KeyError, ValueError) as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(2) from err
    typer.echo(f"#{intent.id} {intent.summary()}")


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
        items = items + _configured_evidence(loaded)
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
def briefing(
    config: Path | None = None,
    out: Path = Path("briefing.md"),
) -> None:
    """Deliberate every agenda subject from the config and render one briefing.

    Writes OUT (markdown) and its .json sibling, then delivers it via the
    configured notifier — 'email' (SMTP, Gmail-friendly, credentials from
    env vars) or 'command' (any executable, briefing path as argument).
    """
    from caucus.briefing import run_agenda
    from caucus.config import Config, ConfigError
    from caucus.engine import Deliberation
    from caucus.notify import NotifyError

    config_path = (
        config if config else Path("config.yaml") if Path("config.yaml").exists() else None
    )
    if config_path is None:
        typer.echo("briefing requires a config file with an 'agenda'", err=True)
        raise typer.Exit(2)
    try:
        loaded = Config.load(config_path)
    except ConfigError as err:
        typer.echo(f"invalid config {config_path}: {err}", err=True)
        raise typer.Exit(2) from err
    if not loaded.agenda:
        typer.echo(
            f"{config_path} has no 'agenda' — list the standing subjects to deliberate", err=True
        )
        raise typer.Exit(2)

    items = _configured_evidence(loaded)
    deliberation = Deliberation(
        backend=loaded.backend, log=DecisionLog(loaded.log), panel=loaded.panel
    )
    result = run_agenda(deliberation, loaded.agenda, items)

    out.write_text(result.to_markdown(), encoding="utf-8")
    out.with_suffix(".json").write_text(result.to_json(), encoding="utf-8")
    typer.echo(f"briefing written: {out} ({len(result.records)} decisions)")
    for record in result.records:
        typer.echo(f"- {record.subject[:70]} → {record.decision[:90]} ({record.confidence:.0%})")

    if loaded.notify is not None:
        subject = f"[Caucus] briefing {result.generated_at[:10]} — {len(result.records)} decisions"
        try:
            loaded.notify.send(subject, result.to_markdown(), attachment_path=out)
        except NotifyError as err:
            typer.echo(str(err), err=True)
            raise typer.Exit(1) from err
        typer.echo("notified")


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
