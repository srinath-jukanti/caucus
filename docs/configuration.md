# Configuration

One file — `config.yaml`, auto-loaded from the working directory (or
`--config path`). Every section below is optional; strict validation
rejects anything malformed with a specific reason. **Secrets never appear
in config** — only the *names* of environment variables.

## Log and intents

```yaml
log: decisions.jsonl     # the hash-chained decision log
intents: intents.db      # standing plans, injected into every deliberation
```

Intents are the slow-moving goals deliberations must respect — cadenced
builds, trigger rules, migrations. Manage them with `caucus intents
add/list/update`; open intents are automatically part of the evidence. A
configured-but-missing store fails the run rather than silently
deliberating without your plans.

## Backend

```yaml
backend:
  type: claude               # local Claude Code CLI; no API key
  mcp_config: mcp.json       # optional: ground analysts in live MCP tools
  allowed_tools:
    - mcp__my-server__get_quotes
```

```yaml
backend:
  type: openai               # any OpenAI-compatible provider
  model: llama3.1
  base_url: http://localhost:11434/v1
  api_key_env: OPENAI_API_KEY   # the NAME of the env var
```

With MCP enabled, analysts fetch what they cite during their turn; tool
output is covered by a system-level data-not-instructions guard. Allow
read-only tools unless you have thought hard about the alternative.

## Evidence sources

```yaml
evidence_sources:
  - name: quant-snapshot
    command: python3 snapshot_evidence.py
    timeout_seconds: 30
```

Each command prints a JSON list of `{source, ref, content}` items —
deterministic computation (indicators, snapshots, state) stays in plain
code and the panel reasons over numbers it did not produce. Sources fail
closed: a broken source aborts the run. Commands come from your own config
and run with your privileges — the same trust model as a Makefile.

## Panel and agenda

```yaml
panel:
  - name: advocate
    charge: Make the strongest evidence-grounded case FOR the proposal.
  - name: skeptic
    charge: Try to refute the proposal.
  - name: risk-officer
    charge: Argue the downside; oppose imprudent sizing.

agenda:
  - "Which standing plan, if any, is due for action today?"
  - "Do conditions warrant deviating from the standing plans?"
```

The panel deliberates in parallel; a chair weighs arguments (votes are not
counted); dissent from the adopted stance is recorded verbatim. The agenda
is the list of standing questions `caucus briefing` answers every run.

## Notification

```yaml
notify:
  type: email                        # Gmail-friendly SMTP defaults
  to: you@example.com
  subject_template: "[Caucus] {date} — {count} decisions"
  template: briefing_email.html.j2   # Jinja2; .html delivered as HTML
```

Credentials come from `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` (names
configurable). Templates render deterministically — same record, same
email; HTML output autoescapes record content. Or run anything executable:

```yaml
notify:
  type: command
  command: bash send_briefing.sh     # receives the briefing path as argument
```
