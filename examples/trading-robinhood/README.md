# Example: trading deliberations over a Robinhood MCP

This is Caucus's reference example — a distillation of the private system it
was extracted from, which has deliberated real portfolio decisions headless,
twice a day, on the author's own money since June 2026. Every decision that
system makes lands in a hash-chained log exactly like the one this example
produces.

**What it demonstrates:** a domain panel (macro, momentum, risk officer)
grounding its positions in *live broker state* through MCP tools, a chair
synthesizing a decision, and dissent going on the record.

**What it is not:** investment advice, a trading bot, or a signal service.
It never places orders — it deliberates and records. You run it on your own
machine, against your own account, at your own risk. Read
[DISCLAIMER.md](../../DISCLAIMER.md) first.

## Dry run — no brokerage, no API keys

From the repository root:

```bash
uv run caucus deliberate "Add to the ACME position this week?" \
  --evidence examples/trading-robinhood/evidence.sample.json \
  --log decisions.jsonl
uv run caucus verify decisions.jsonl
```

The sample evidence is fictional. The default backend is the locally
authenticated Claude Code CLI; add `--backend openai --model llama3.1
--base-url http://localhost:11434/v1` to run fully local via Ollama.

## Live — the full reference deployment, step by step

Everything below is configuration; no code changes are required.

1. **Install**: `uv tool install caucus` (from PyPI).
2. **Broker MCP**: copy `mcp.example.json` to `mcp.json`; run one interactive
   `claude` session with it to complete the provider's authentication.
3. **Config**: copy `config.yaml` and `news_evidence.py` from this directory
   into your working directory; set `notify.to` to your address and export
   `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` (a Gmail app password).
4. **Standing plans**: record your cadenced builds/trims and trigger rules —
   they are injected into every deliberation as evidence:

```bash
caucus intents add "ACME build" --direction build --target 5% \
  --pacing "weekly on dips" --cadence-days 7
caucus intents add "XYZ exit at breakeven" --direction trim \
  --target "exit full position" --notes "sell all at cost basis 114.94"
```

5. **Run**: `caucus briefing` — the agenda's four standing questions are
   deliberated in order, the briefing is rendered and emailed, and every
   decision (with dissent) lands in the hash-chained log.
6. **Schedule**: adapt `run-caucus.sh` (secrets from an env file) and either
   the launchd template `com.example.caucus.plist` (macOS) or the cron line
   in its comments (Linux).

Each analyst calls the allowed read-only tools — quotes, historicals,
portfolio, option chains, scans — and cites what it fetched as evidence.
Tool output is covered by Caucus's system-level data-not-instructions guard;
only **read-only** tools are allowed in this example by design.

## Guardrails carried over from the reference system

- **Deliberate and record; never execute.** No order-placing tool is ever in
  `allowed_tools`. A human reads the record and acts (or does not).
- **Ground state before opinion.** Analysts are charged to fetch current
  state rather than trust remembered positions.
- **The dissent is the point.** When the record later meets reality, the
  overruled argument is the most instructive line in it.
