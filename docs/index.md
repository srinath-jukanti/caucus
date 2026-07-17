# Caucus

**Your AI agents, deliberating on the record.**

MCP-grounded multi-agent consensus with recorded dissent and an auditable,
tamper-evident decision log.

```bash
uv tool install caucus
caucus init
caucus deliberate "Adopt library X for feature Y?"
```

## Why Caucus

Multi-agent debate is a proven pattern — but every popular implementation
deliberates over *text* and throws the deliberation away. Caucus is built on
two convictions:

1. **Agents should argue over evidence, not vibes.** Analysts ground
   themselves in live state pulled through [MCP](https://modelcontextprotocol.io)
   servers, deterministic evidence commands, and your standing plans —
   before they open their mouths.
2. **The record is the product.** Every run produces a hash-chained record:
   each agent's position, the dissent that was overruled, the confidence of
   the consensus, and the evidence it rested on. You can defend a Caucus
   decision in an audit. You cannot defend a chat transcript.

Caucus is a decision layer, not another agent framework: bring your own
agents, models, tools, and domain.

## Proven in production

The reference deployment has deliberated real portfolio decisions — the
author's own money — headless, twice a day, since June 2026, with every
decision and every dissent on a verifiable chain. It ships, sanitized, as
[the trading example](examples.md).

## Where to go next

- [Quickstart](quickstart.md) — running in five minutes
- [Configuration](configuration.md) — every option in one file
- [The decision record spec](spec.md) — implement or verify it from any language
- [Security & trust model](security.md)
