# Caucus Decision Record — Specification

**Version 0.1** (the `schema_version` field). This document is the normative
definition of the record format. Any tool may emit or verify Caucus decision
records by conforming to it; the reference implementation is
[`src/caucus/record.py`](src/caucus/record.py).

## Container

A decision log is a UTF-8 [JSON Lines](https://jsonlines.org) file. Each
non-empty line is one decision record. The file is **append-only**: conforming
writers never rewrite, reorder, or delete lines, and must serialize appends
(the reference implementation holds an exclusive advisory file lock across
read-chain-tip + write, so concurrent writers cannot fork the chain).

## Record fields

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | `"0.1"` |
| `timestamp` | string | ISO 8601, UTC |
| `subject` | string | what was deliberated |
| `positions` | array of objects | one per agent: `{agent, stance, summary, confidence}` |
| `decision` | string | the consensus outcome |
| `dissent` | array of objects | positions that disagreed with the outcome — recorded, never dropped |
| `confidence` | number | consensus confidence, 0–1 |
| `evidence` | array of objects | `{source, ref}` citations grounding the decision |
| `prev_hash` | string | hex SHA-256 of the previous record; genesis is 64 zeros |
| `hash` | string | hex SHA-256 of this record's canonical form |

## Canonical form and hashing

The canonical form of a record is the JSON serialization of all fields
**except `hash`**, with keys sorted lexicographically and no whitespace
(separators `,` and `:`).

```
hash = SHA-256(canonical_form)          # lowercase hex
prev_hash = hash of the preceding record, or "0" * 64 for the first record
```

Because `prev_hash` is inside the hashed content, editing record *N*
invalidates *N*'s own hash, and deleting record *N* breaks record *N+1*'s
chain link. That is the entire tamper-evidence argument.

## Verification

A verifier walks the file in order and, for each record, checks:

1. the line parses as a JSON object containing every field in the table above
   (else: **malformed record**),
2. `schema_version` is a version this verifier supports
   (else: **unsupported schema version** — a verifier must not certify a
   record it cannot interpret),
3. `prev_hash` equals the previous record's `hash` — genesis hash for the
   first record (else: **broken chain link**),
4. recomputing the canonical-form hash reproduces `hash`
   (else: **content hash mismatch**).

Verification fails at the first violation, reporting the zero-based record
index and the reason. An empty or missing file verifies as intact with zero
records.

```bash
uv run caucus verify path/to/decisions.jsonl
```

## Stability

Fields may be added in future minor versions; existing fields will not be
renamed or removed within `0.x`. Verifiers must operate on the raw JSON
object so unknown fields participate in canonical hashing exactly as
written; readers may ignore unknown fields when materializing records.
