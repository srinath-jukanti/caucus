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
uv tool install caucus
caucus init          # interactive setup: backend, panel, agenda, delivery
caucus deliberate "Adopt library X for feature Y?"
```

Describe your use case during `caucus init` and your configured backend drafts the analyst panel and standing agenda for you — previewed, validated, and written to an editable `config.yaml`. (From source: `git clone … && uv sync && uv run caucus …`.)

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

## Deliberate

```bash
uv run caucus deliberate "Adopt library X for feature Y?" --evidence evidence.json
```

Three analysts — an advocate, a skeptic, and an assessor — argue over your evidence in parallel. A chair weighs the arguments — votes are not counted — and the verdict, every position, and the overruled dissent land in the hash-chained log:

```
DECISION (75% confidence): Adopt it, with guardrails.
DISSENT [skeptic]: hidden costs in the integration surface
On the record: decisions.jsonl (hash 3f9c2a81d0b4…)
```

**Provider-agnostic by construction:** a backend is anything with `complete(prompt) -> str`. The default is the locally authenticated Claude Code CLI (zero API keys); `--backend openai --model <m> --base-url <url>` reaches any OpenAI-compatible provider — OpenAI, Ollama, vLLM, Groq, Together, OpenRouter — via the optional `caucus[openai]` extra:

```bash
uv run caucus deliberate "Adopt library X?" --backend openai --model llama3.1 --base-url http://localhost:11434/v1
```

The subject, the evidence, and the panel's own positions are all fenced behind unforgeable random-token delimiters and framed as *data, never instructions* — prompt-injection resistance is a design rule, not an afterthought.

Persistent setup lives in one file — copy [config.example.yaml](config.example.yaml) to `config.yaml` (picked up automatically) to choose the log path, the backend, and your own panel of analysts. With the Claude backend, `mcp_config` + `allowed_tools` turn on the **MCP evidence layer**: analysts ground their positions in live tool state — your broker, your issue tracker, your observability stack — during deliberation.

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

Change any recorded value — a decision, a dissent, a confidence, the presence or order of records — and `verify` fails, naming the record and the reason. (Hashes cover each record's canonical form, so semantically equivalent re-serializations are normalized rather than flagged.) Both properties are enforced by tests, not by promises.

## Examples

**Start here — [`examples/decision-memo/`](examples/decision-memo/):** deliberate any real decision you're weighing (a migration, a job offer, a roadmap bet) in five minutes with no API keys. The overruled dissent stays on the record — the decision memo that argues back.

[`examples/trading-robinhood/`](examples/trading-robinhood/) is the reference example — a sanitized distillation of the private system Caucus was extracted from, which has deliberated real portfolio decisions headless, twice a day, on the author's own money since June 2026. It includes a fictional-evidence dry run that needs no brokerage and no API keys, and a live configuration that grounds a macro/momentum/risk panel in read-only Robinhood MCP tools. It deliberates and records; it never trades.

## Benchmarks

Does deliberation beat a single agent, and what does it cost? [`evals/`](evals/) benchmarks the real engine on ARC-Challenge, MMLU-Pro, and GPQA-Diamond against a single-agent baseline — accuracy with bootstrap CIs, calibration (Brier/ECE), whether recorded dissent predicts errors, and honest token costs. Raw per-question records are committed and every deliberation lands in a decision log both reference verifiers certify. Results: [`evals/results/RESULTS.md`](evals/results/RESULTS.md).

## Status

The v1 core is complete: the hash-chained decision record ([SPEC.md](SPEC.md)), the deliberation engine, provider-agnostic backends, configuration, and the MCP evidence layer — extracted vertical slice by vertical slice from the reference system, every PR adversarially reviewed in public.

## License

[MIT](LICENSE). The trading example is a demonstration of the framework, not investment advice — see [DISCLAIMER.md](DISCLAIMER.md).
