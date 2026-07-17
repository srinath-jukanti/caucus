# Example: the decision memo that argues back

The fastest way to try Caucus on something real: any decision you're
actually weighing — a library migration, a job offer, a roadmap bet. Three
analysts argue it, a chair decides, and the overruled dissent stays on the
record — so when you revisit the decision later, you can see exactly which
argument won and which one you'll wish you'd listened to.

## Five minutes, no API keys

```bash
uv tool install caucus
cd examples/decision-memo
caucus deliberate "Should we migrate our primary datastore from Postgres to DynamoDB?" \
  --config config.yaml --evidence evidence.sample.json
caucus verify decisions.jsonl
```

The default backend is the locally authenticated Claude Code CLI. Fully
local instead: add `--backend openai --model llama3.1 --base-url
http://localhost:11434/v1` (Ollama) — but then drop `--config`, or edit the
config's backend block, since config and backend flags are mutually
exclusive.

## Using your own decision

Evidence is just a JSON list of notes — paste in whatever you'd put in a
decision doc:

```json
[
  {"source": "metrics", "ref": "current load", "content": "p99 8ms at 2k QPS, single writer at 60% CPU"},
  {"source": "team", "ref": "experience", "content": "nobody on the team has run DynamoDB in production"},
  {"source": "finance", "ref": "estimate", "content": "provisioned-capacity quote ~2.1x current RDS spend at projected scale"}
]
```

Then: `caucus deliberate "Your question?" --config config.yaml --evidence notes.json`

Every claim the panel makes is fenced as *data, never instructions*, and
each record chains to the previous one — your decision history becomes a
tamper-evident log you can audit later with `caucus verify`.

## The panel

- **proponent** — the strongest honest case *for*, grounded in the evidence
- **red-team** — the strongest case *against*: failure modes, hidden costs, what breaks at 3am
- **base-rate-realist** — the outside view: how decisions like this usually go, reversibility, and what you'd need to believe for this to be the exception

Run `caucus init` in an empty directory to have your backend draft a panel
tuned to your own domain instead.
