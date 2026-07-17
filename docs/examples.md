# Examples

## Decision memo — start here

Deliberate any real decision you're weighing — a migration, a job offer, a
roadmap bet — in five minutes with no API keys. A proponent / red-team /
base-rate-realist panel argues over your notes, and the overruled dissent
stays on the record for the day you revisit the decision.

[`examples/decision-memo/`](https://github.com/srinath-jukanti/caucus/tree/main/examples/decision-memo)

## Trading over a broker MCP — the reference deployment

A sanitized copy of the system Caucus was extracted from, which deliberates
the author's real portfolio twice a day: a macro/momentum/risk-officer
panel grounded in read-only broker tools (quotes, historicals, positions,
option chains), standing campaigns as intents, deterministic indicator
snapshots and keyless news feeds as evidence sources, HTML briefings by
email, and scheduling templates.

It deliberates and records; it **never trades** — no order-placing tool is
ever in the allowlist, and nothing it produces is investment advice.

[`examples/trading-robinhood/`](https://github.com/srinath-jukanti/caucus/tree/main/examples/trading-robinhood)
