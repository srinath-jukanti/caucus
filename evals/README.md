# Caucus evaluation harness

Does deliberation actually beat a single agent — and what does it cost?
This harness benchmarks the real engine (the same `Deliberation` class
users run, prompt fencing and JSON discipline included) against a
single-agent baseline on public decision benchmarks, and publishes token
costs alongside accuracy. No cherry-picking: raw per-question records are
committed under `results/raw/`, every summary number is recomputable from
them, and each deliberation lands in a hash-chained decision log
(`*.decisions.jsonl`) that `caucus verify` certifies.

## Benchmarks

| dataset | source | access | options |
|---|---|---|---|
| `arc_challenge` | `allenai/ai2_arc` (ARC-Challenge, test) | public | 4 |
| `mmlu_pro` | `TIGER-Lab/MMLU-Pro` (test) | public | up to 10 |
| `gpqa_diamond` | `Idavidrein/gpqa` (gpqa_diamond) | gated (HF token + license) | 4 |

Questions are sampled deterministically (`--seed`, default 0), so the
sample is reproducible; the sampled question ids appear in the raw records.

## Conditions

- **single** — one agent, one call, same fenced prompt style, answers
  `{"answer": <letter>, "confidence": <0-1>}`.
- **panel** — 3-analyst deliberation + chair (`max_rounds=1`), stances set
  to the option letters. Panel charges are tuned for closed-form questions
  (solve / attack the obvious answer / eliminate options).
- **debate** — the same panel with `max_rounds=3` and adaptive stopping, so
  rebuttal rounds are spent only on live disagreement.

## Metrics

- **Accuracy** with a 95% percentile bootstrap CI (10,000 resamples, seeded).
- **Brier score** and **ECE** (10 bins) of stated confidence against
  correctness — does the system know when it might be wrong?
- **Dissent vs errors** — accuracy on questions where the record shows
  dissent vs unanimous ones. If dissent predicts errors, the audit trail is
  a usable signal, not decoration.
- **Token cost per question** (input/output), from the backend's own usage
  accounting — `claude -p --output-format json` usage for the CLI backend,
  `response.usage` for OpenAI-compatible APIs. Cache reads and cache
  creation count as input.

## Running

```sh
# smoke test (few questions, prints per-question results)
uv run --group evals evals/run.py --dataset arc_challenge --n 5

# full run + report; resumes if interrupted (finished questions are skipped)
uv run --group evals evals/run.py --dataset mmlu_pro --n 150 --model claude-sonnet-4-6

# aggregate committed raw records into RESULTS.md / summary.json
uv run --group evals evals/run.py --report

# project full-run token cost from a smoke sample
uv run --group evals evals/run.py --report --project-n 150
```

`--backend openai --base-url ... --api-key-env ...` runs the same harness
against any OpenAI-compatible provider (Ollama, vLLM, OpenRouter, ...).

## Honest-numbers caveats

- The `claude` backend runs through the Claude Code CLI, which adds its own
  system prompt; reported input tokens include that overhead. API-backend
  runs measure the prompts alone.
- Results are model- and date-stamped in the raw records; numbers from
  different models or harness versions are not comparable rows.
- Deliberation costs a multiple of the single-agent condition by
  construction (panel + chair). The question the numbers answer is whether
  accuracy and calibration gains justify that multiple — not whether it is
  free.
