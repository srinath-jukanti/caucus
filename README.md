# Caucus

**Your AI agents, deliberating on the record.**

MCP-grounded multi-agent consensus with recorded dissent and an auditable, tamper-evident decision log.

> Convene agents. Reach consensus. Keep the receipts.

## Why

Multi-agent debate is a proven pattern — but every existing implementation deliberates over *text* and throws the deliberation away. Caucus is built on two convictions:

1. **Agents should argue over evidence, not vibes.** Every analyst agent grounds itself in live state pulled through [MCP](https://modelcontextprotocol.io) servers — your broker, your issue tracker, your observability stack — before it opens its mouth.
2. **The record is the product.** Each run produces a hash-chained decision record: every agent's position, the dissent that was overruled, the confidence of the final consensus, and the evidence it rested on. You can defend a Caucus decision in an audit. You cannot defend a chat transcript.

Caucus is a decision layer, not another agent framework. It orchestrates deliberation and guarantees the record; bring your own agents, tools, and domain.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and [Claude Code](https://claude.com/claude-code).

```bash
git clone https://github.com/srinath-jukanti/caucus.git && cd caucus
uv sync
uv run caucus version
```

**Or let your AI agent set it up for you** — paste the prompt in [AGENT_SETUP.md](AGENT_SETUP.md) into Claude Code, Codex, or Cursor and it will install, configure, and verify Caucus end to end.

## Architecture

| Layer | What it does | Storage |
|---|---|---|
| Deliberation engine | N analyst agents in parallel → synthesis → adversarial review → consensus with confidence | — |
| Evidence layer | MCP servers declared in config; agents ground every claim in live tool state | — |
| Decision record | Append-only, hash-chained log of positions, dissent, and evidence | JSONL |
| Intents | Slow-moving goals the engine works toward across runs | SQLite |
| Memory | Layered notes with decay half-lives; reflection scores past decisions against outcomes | Markdown |

Everything is inspectable with `cat` and `sqlite3`. No vector database, no hosted service, no telemetry.

## The decision record

The record format is a versioned, open specification — see [SPEC.md](SPEC.md). Each record embeds its predecessor's SHA-256, so editing a record invalidates its own hash and deleting one breaks its successor's link:

```python
from caucus.record import DecisionLog, DecisionRecord

log = DecisionLog("decisions.jsonl")
log.append(DecisionRecord(
    subject="Trim QQQ this week?",
    decision="yes — one weekly tranche",
    confidence=0.8,
    positions=[{"agent": "macro", "stance": "yes", "summary": "overweight vs target", "confidence": 0.9}],
    dissent=[{"agent": "momentum", "stance": "no", "summary": "trend still intact", "confidence": 0.6}],
    evidence=[{"source": "quotes", "ref": "QQQ@725.60"}],
))
```

```bash
$ uv run caucus verify decisions.jsonl
OK — 1 records, chain intact
```

Tamper with any byte of the file and `verify` fails, naming the record and the reason. Both properties are enforced by tests, not by promises.

## Status

Early and moving fast. The engine is being extracted, vertical slice by vertical slice, from a private trading agent that has run headless twice a day on real money since June 2026 — that system is the reference implementation and will ship (sanitized) as `examples/trading-robinhood/`.

## License

[MIT](LICENSE). The trading example is a demonstration of the framework, not investment advice — see [DISCLAIMER.md](DISCLAIMER.md).
