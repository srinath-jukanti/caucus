# Contributing to Caucus

Thanks for your interest — contributions are welcome.

## Ground rules

- **Every PR goes through the same gate**: CI (ruff format, ruff check,
  pytest) plus an automated adversarial code review. Blocking findings must
  be fixed; non-blocking findings are auto-filed as issues. Expect the
  reviewer to be tough on anything touching record integrity or prompt
  injection — that's the product.
- **The decision record is sacred.** Changes to `record.py` or `SPEC.md`
  must preserve the format's guarantees (see SPEC.md's verification and
  trust-model sections) and pin any serialization change with golden
  vectors. Hash-affecting changes require a `schema_version` bump.
- **Deterministic core, model at the edges.** Rendering, verification,
  storage, and configuration stay deterministic and testable; model calls
  happen only inside backends and are always validated on the way out.
- **Keep dependencies boring.** New runtime dependencies need a strong
  justification; storage stays inspectable (JSONL, SQLite, Markdown).
- **Secrets never enter the repo or the config schema** — environment
  variable *names* only.

## Getting started

```bash
git clone https://github.com/srinath-jukanti/caucus.git && cd caucus
uv sync
uv run pytest -q          # 150+ tests, sub-second
uv run ruff format . && uv run ruff check .
```

Good first issues are labeled
[`good first issue`](https://github.com/srinath-jukanti/caucus/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
— many originate as non-blocking findings from the automated reviewer, so
they come with a precise description of the fix.

## PR checklist

- Tests for the change (adversarial cases welcome — this repo's tests try
  to break their own features).
- `uv run ruff format . && uv run ruff check . && uv run pytest -q` green.
- One focused change per PR.

## Maintainer

Caucus is created and maintained by Srinath Jukanti. Design questions and
larger proposals: open a GitHub Discussion or issue before building.
