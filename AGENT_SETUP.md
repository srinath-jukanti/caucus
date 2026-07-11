# Agent Setup

Caucus is designed to be **agent-installable**: instead of following a setup
guide yourself, paste the prompt below into any capable coding agent —
Claude Code, Codex CLI, Cursor, etc. — and it will install, verify, and
configure Caucus for you.

---

## The prompt

```text
Set up the Caucus multi-agent deliberation framework for me on this machine.

1. Verify prerequisites, installing anything missing:
   - `uv` (install via `curl -LsSf https://astral.sh/uv/install.sh | sh` if absent)
   - `git`
2. Clone https://github.com/srinath-jukanti/caucus.git into a sensible projects
   directory (ask me if unsure), then run `uv sync` inside it.
3. Verify the install: `uv run caucus version` must print a version, and
   `uv run pytest -q` must pass. If either fails, diagnose and fix before
   continuing — do not report success until both are green.
4. Read the repository README.md and tell me, in a few sentences, what Caucus
   does and what the current release supports.
5. If a `config.example.yaml` exists, copy it to `config.yaml` and walk me
   through each setting interactively; otherwise note that configuration
   lands in a future release and skip this step.
6. Finish with a short report: what was installed, what was verified, and the
   exact command I run next.

Rules: never write secrets into tracked files; anything sensitive goes in
`.env` (gitignored). Do not modify files outside the cloned repository other
than installing the prerequisites above.
```

---

## Notes

- The prompt is written defensively: it verifies rather than assumes, and it
  fails loudly instead of reporting phantom success.
- As Caucus grows (deliberation runs, MCP evidence sources, the decision
  record), this prompt will grow with it — it is versioned alongside the code
  on purpose, so the prompt you paste always matches the commit you cloned.
