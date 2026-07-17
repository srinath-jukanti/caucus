# Quickstart

## Install

```bash
uv tool install caucus        # or: pip install caucus
```

The default backend is the locally authenticated
[Claude Code](https://claude.com/claude-code) CLI — no API key needed. Any
OpenAI-compatible provider (OpenAI, Ollama, vLLM, Groq, OpenRouter) works
via the `openai` backend and the `caucus[openai]` extra.

## Set up once

```bash
caucus init
```

The wizard collects your backend, optional MCP grounding, standing-plan
tracking, and email delivery — and if you describe your use case in plain
English, your configured backend drafts an analyst panel and standing
agenda for you, previewed and validated before anything is written. The
result is an editable `config.yaml`.

## Deliberate

```bash
caucus deliberate "Should we migrate the datastore?" --evidence notes.json
```

```
DECISION (72% confidence): Defer the migration until after the compliance launch…
DISSENT [proponent]: The single-writer ceiling arrives before the launch window closes…
On the record: decisions.jsonl (hash 3f9c2a81d0b4…)
```

Evidence is a JSON list of `{source, ref, content}` notes — whatever you
would put in a decision doc.

## Run a standing agenda

```bash
caucus briefing
```

Every subject in your config's `agenda` is deliberated onto the same log,
rendered (Markdown, or HTML via a template), and delivered through the
configured notifier.

## Verify the record

```bash
caucus verify decisions.jsonl
# OK — 12 records, chain intact (anchored to head checkpoint)
```

Change any recorded value, delete a record, or truncate the log — and
verification fails, naming the record and the reason.

## Let your agent do all of this

The repository ships an [agent setup prompt](https://github.com/srinath-jukanti/caucus/blob/main/AGENT_SETUP.md)
you can paste into Claude Code, Codex, or Cursor to have it install,
configure, and verify Caucus for you end to end.
