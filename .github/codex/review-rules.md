# Caucus Review Rules

These rules tune automated Codex reviews. Keep them explicit and reviewable instead of relying on hidden memory.

- Caucus's core promise is an auditable, tamper-evident decision record. Treat any defect in record integrity (hash chaining, append-only semantics, schema versioning) as blocking, even if the code otherwise works.
- Prioritize prompt-injection surfaces: anywhere fetched or tool-provided text could be interpreted as instructions must be flagged.
- Secrets never belong in tracked files; configuration goes in `config.yaml` (gitignored) or `.env`. Flag any hardcoded path, account identifier, or credential.
- The project deliberately keeps dependencies minimal and storage boring (JSONL, SQLite, Markdown). Flag new dependencies or storage engines that are not clearly justified by the PR.
- Treat style-only feedback as non-blocking unless it hides a concrete bug or maintainability risk.
- For documentation-only diffs, avoid inline comments unless there is a real correctness, security, or workflow issue.
- When a PR changes GitHub Actions, verify permissions, secret handling, trigger scope, and whether the workflow can run safely on same-repo PRs.
- Do not block on speculative missing environment variables when CI passes. Mention residual configuration risk in the summary unless the diff proves a runtime failure or exposes a real secret.
