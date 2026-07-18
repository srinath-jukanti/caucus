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


@app.command()
def init(directory: Path = Path("."), force: bool = False) -> None:
    """Interactive setup — configure backend, panel, agenda, and delivery once.

    Describe your use case and the configured backend drafts an analyst panel
    and standing agenda for you (previewed before anything is written); every
    answer lands in an editable config.yaml.
    """
    import shutil

    from caucus.wizard import WizardError, draft_panel_and_agenda, render_config

    config_path = directory / "config.yaml"
    if config_path.exists() and not force:
        typer.echo(f"{config_path} already exists — rerun with --force to overwrite", err=True)
        raise typer.Exit(2)

    typer.echo("Caucus setup — answers become config.yaml; everything is editable later.\n")

    backend_kind = typer.prompt(
        "Backend: 'claude' (local Claude Code CLI, no API key) or 'openai' "
        "(any OpenAI-compatible provider)",
        default="claude",
    )
    if backend_kind not in ("claude", "openai"):
        typer.echo("backend must be 'claude' or 'openai'", err=True)
        raise typer.Exit(2)

    model = base_url = api_key_env = mcp_config = None
    allowed_tools: list[str] = []
    if backend_kind == "openai":
        model = typer.prompt("Model (e.g. gpt-4o, llama3.1)")
        base_url = (
            typer.prompt(
                "Base URL (blank for api.openai.com; e.g. http://localhost:11434/v1 for Ollama)",
                default="",
                show_default=False,
            )
            or None
        )
        api_key_env = typer.prompt("Env var holding the API key", default="OPENAI_API_KEY")
    else:
        if shutil.which("claude") is None:
            typer.echo(
                "note: 'claude' not found on PATH — install Claude Code before deliberating."
            )
        mcp_config = (
            typer.prompt(
                "MCP config path to ground analysts in live tools (blank = none)",
                default="",
                show_default=False,
            )
            or None
        )
        if mcp_config:
            tools = typer.prompt(
                "Comma-separated allowed tool names (read-only tools recommended)",
                default="",
                show_default=False,
            )
            allowed_tools = [tool.strip() for tool in tools.split(",") if tool.strip()]

    panel = agenda = None
    description = typer.prompt(
        "Describe what you'll deliberate about and your backend will draft a "
        "panel + agenda (blank = generic defaults)",
        default="",
        show_default=False,
    ).strip()
    if description:
        if backend_kind == "claude":
            from caucus.backends import ClaudeCodeBackend

            draft_backend = ClaudeCodeBackend()
        else:
            from caucus.backends import OpenAICompatibleBackend

            draft_backend = OpenAICompatibleBackend(
                model=model, base_url=base_url, api_key_env=api_key_env or "OPENAI_API_KEY"
            )
        typer.echo("drafting panel + agenda…")
        try:
            panel, agenda = draft_panel_and_agenda(draft_backend, description)
        except Exception as err:  # any backend/engine failure degrades to defaults
            typer.echo(
                f"drafting failed ({err}); using generic defaults — edit config.yaml later.",
                err=True,
            )
        else:
            typer.echo("\nProposed panel:")
            for analyst in panel:
                typer.echo(f"  - {analyst.name}: {analyst.charge}")
            typer.echo("Proposed agenda:")
            for subject in agenda:
                typer.echo(f"  - {subject}")
            if not typer.confirm("Accept this draft?", default=True):
                panel = agenda = None
                typer.echo("using generic defaults — edit config.yaml later.")

    intents = typer.confirm(
        "Track standing plans (intents) that inform every deliberation?", default=True
    )
    notify_email = None
    if typer.confirm("Email each briefing?", default=False):
        notify_email = typer.prompt("Send to")
        typer.echo(
            "  → set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the environment "
            "(Gmail: myaccount.google.com/apppasswords)."
        )

    try:
        text = render_config(
            backend_kind=backend_kind,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            mcp_config=mcp_config,
            allowed_tools=allowed_tools,
            panel=panel,
            agenda=agenda,
            intents=intents,
            notify_email=notify_email,
        )
    except WizardError as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(2) from err

    directory.mkdir(parents=True, exist_ok=True)
    config_path.write_text(text, encoding="utf-8")
    typer.echo(f"\nwrote {config_path}")
    if intents:
        typer.echo('next: record standing plans —  caucus intents add "..." --target ...')
    if agenda:
        typer.echo("run the full agenda:          caucus briefing")
    typer.echo('or a one-off deliberation:    caucus deliberate "Your question?"')


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
    paused_until: str | None = None,
    notes: str = "",
) -> None:
    """Record a new standing intent (--paused-until pauses it until that date)."""
    try:
        intent = _intents_store(db).add(
            name=name,
            direction=direction,
            target=target,
            pacing=pacing,
            cadence_days=cadence_days,
            last_acted=last_acted,
            paused_until=paused_until,
            notes=notes,
        )
    except ValueError as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(2) from err
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
    paused_until: str | None = None,
    target: str | None = None,
    pacing: str | None = None,
    cadence_days: int | None = None,
    notes: str | None = None,
) -> None:
    """Update fields on an intent (e.g. --status done, --paused-until 2026-07-16)."""
    fields = {
        key: value
        for key, value in {
            "status": status,
            "last_acted": last_acted,
            "paused_until": paused_until,
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


@intents_app.command("apply")
def intents_apply(source: Path = Path("briefing.json"), db: Path | None = None) -> None:
    """Apply a briefing's proposed intent updates, confirming each one."""
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        typer.echo(f"cannot read {source}: {err}", err=True)
        raise typer.Exit(2) from err
    proposals = payload.get("intent_proposals") or []
    if not proposals:
        typer.echo("(no proposals in this briefing)")
        return
    store = _intents_store(db)
    applied = 0
    for proposal in proposals:
        line = f"intent #{proposal['id']}: {proposal['fields']} — {proposal.get('reason', '')}"
        if not typer.confirm(f"apply {line}?", default=False):
            continue
        try:
            store.update(proposal["id"], **proposal["fields"])
            applied += 1
        except (KeyError, ValueError, TypeError) as err:
            typer.echo(f"  skipped: {err}", err=True)
    typer.echo(f"applied {applied}/{len(proposals)}")


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

    if loaded.intents is not None:
        from caucus.briefing import propose_intent_updates
        from caucus.engine import EngineError
        from caucus.intents import IntentStore

        current = IntentStore(loaded.intents).list()
        if current:
            try:
                # Proposals only — 'caucus intents apply' applies them with
                # per-item confirmation. The store stays operator-controlled.
                result.intent_proposals = propose_intent_updates(loaded.backend, current, result)
            except EngineError as err:
                typer.echo(f"intent-proposal step failed ({err}) — continuing", err=True)

    out.write_text(result.to_markdown(), encoding="utf-8")
    out.with_suffix(".json").write_text(result.to_json(), encoding="utf-8")
    typer.echo(f"briefing written: {out} ({len(result.records)} decisions)")
    for record in result.records:
        typer.echo(f"- {record.subject[:70]} → {record.decision[:90]} ({record.confidence:.0%})")
    for proposal in result.intent_proposals or []:
        typer.echo(
            f"- proposed: intent #{proposal['id']} {proposal['fields']} — {proposal['reason']}"
        )

    if loaded.notify is not None:
        from caucus.briefing import TemplateRenderError, render_template, template_subtype
        from caucus.notify import EmailNotifier

        body = result.to_markdown()
        subtype = "plain"
        subject = f"[Caucus] briefing {result.generated_at[:10]} — {len(result.records)} decisions"
        if isinstance(loaded.notify, EmailNotifier):
            subject = loaded.notify.subject_template.format(
                date=result.generated_at[:10], count=len(result.records)
            )
            if loaded.notify.template:
                template_path = Path(loaded.notify.template)
                if not template_path.exists():
                    typer.echo(f"notify template {template_path} does not exist", err=True)
                    raise typer.Exit(2)
                try:
                    body = render_template(result, template_path)
                except TemplateRenderError as err:
                    typer.echo(str(err), err=True)
                    raise typer.Exit(2) from err
                subtype = template_subtype(template_path)
        try:
            loaded.notify.send(subject, body, attachment_path=out, subtype=subtype)
        except NotifyError as err:
            typer.echo(str(err), err=True)
            raise typer.Exit(1) from err
        typer.echo("notified")


@app.command()
def anchor(log: Path = Path("decisions.jsonl"), config: Path | None = None) -> None:
    """Record the log's head hash as an anchor and ship it out of the trust domain.

    Appends {anchored_at, count, head_hash} to <log>.anchors, then runs the
    configured anchor_command with that path (git commit+push, curl to a
    timestamping service, scp — anything that puts it where a local attacker
    cannot rewrite it). Verify against a fetched copy with
    'caucus verify <log> --anchors <copy>'.
    """
    import shlex
    import subprocess

    from caucus.anchor import AnchorError, anchors_path_for, append_anchor
    from caucus.config import Config, ConfigError

    anchor_command = None
    config_path = (
        config if config else Path("config.yaml") if Path("config.yaml").exists() else None
    )
    if config_path is not None:
        try:
            loaded = Config.load(config_path)
        except ConfigError as err:
            typer.echo(f"invalid config {config_path}: {err}", err=True)
            raise typer.Exit(2) from err
        anchor_command = loaded.anchor_command
        if log == Path("decisions.jsonl"):
            log = loaded.log

    decision_log = DecisionLog(log)
    try:
        entry = append_anchor(decision_log)
    except AnchorError as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(1) from err
    anchors = anchors_path_for(decision_log)
    typer.echo(f"anchored {entry['count']} records, head {entry['head_hash'][:16]}… → {anchors}")
    if anchor_command:
        quoted = shlex.quote(str(anchors))
        # {path} substitution supports compound commands (git add {path} && ...);
        # appending the path to the whole string would hand it to the LAST
        # command (e.g. git push) instead.
        if "{path}" in anchor_command:
            command = anchor_command.replace("{path}", quoted)
        else:
            command = f"{anchor_command} {quoted}"
        completed = subprocess.run(command, shell=True)
        if completed.returncode != 0:
            typer.echo(f"anchor command exited {completed.returncode}", err=True)
            raise typer.Exit(1)
        typer.echo("anchor shipped")


@app.command()
def verify(path: Path, anchors: Path | None = None) -> None:
    """Verify the hash chain of a decision log (see SPEC.md).

    With --anchors, additionally prove the log still matches previously
    anchored heads — a full-log rewrite passes plain verification but cannot
    reproduce the anchors.
    """
    result = DecisionLog(path).verify()
    if result.ok and anchors is not None:
        from caucus.anchor import AnchorError, verify_anchors

        try:
            anchored = verify_anchors(DecisionLog(path), anchors)
        except AnchorError as err:
            typer.echo(str(err), err=True)
            raise typer.Exit(2) from err
        if not anchored.ok:
            typer.echo(f"ANCHOR FAILURE — {anchored.reason}", err=True)
            raise typer.Exit(1)
        typer.echo(f"anchors OK — {anchored.checked} anchors match the chain")
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
