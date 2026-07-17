# Security Policy

Caucus's core claim is an auditable, tamper-evident decision record — so
integrity and injection findings are treated as security issues, not bugs.

## Reporting

Please report vulnerabilities privately via
[GitHub Security Advisories](https://github.com/srinath-jukanti/caucus/security/advisories/new)
rather than public issues. You can expect an acknowledgment within a few
days. Coordinated disclosure is appreciated; credit is given unless you
prefer otherwise.

## In scope

- **Record integrity**: any way to alter, remove, reorder, truncate, or
  forge decision records (or their checkpoints) that `caucus verify`
  certifies as intact — including canonicalization ambiguities that let two
  conforming implementations disagree about the same record.
- **Prompt injection**: any path by which subject text, evidence, tool
  output, or panel positions can escape their data fences and change an
  agent's role, task, or output format.
- **Secret exposure**: any way configuration or logs can capture credential
  values (the design permits environment-variable names only).
- Command execution beyond what the user's own configuration explicitly
  declares (evidence sources and notify commands run with the user's
  privileges by design — see the trust notes in `config.example.yaml`).

## Out of scope

- The quality of model-generated *content* (bad arguments are not
  vulnerabilities; unfaithful records are).
- Vulnerabilities in the model backends themselves (Claude Code, provider
  SDKs) — report those upstream.
