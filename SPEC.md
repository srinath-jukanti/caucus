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
| `timestamp` | string | ISO 8601 with an explicit UTC offset (`Z` or `+00:00`); naive or non-UTC timestamps do not conform |
| `subject` | string | what was deliberated |
| `positions` | array of objects | one per agent: `agent`, `stance`, `summary` (strings) and `confidence` (number, 0–1) |
| `decision` | string | the consensus outcome |
| `dissent` | array of objects | positions that disagreed with the outcome — same entry shape as `positions`, recorded, never dropped |
| `confidence` | number | consensus confidence, 0–1 |
| `evidence` | array of objects | citations grounding the decision: `source` and `ref` (strings) |
| `prev_hash` | string | hex SHA-256 of the previous record; genesis is 64 zeros |
| `hash` | string | hex SHA-256 of this record's canonical form |

## Canonical form and hashing

The canonical form of a record is the JSON serialization of all fields
**except `hash`**, produced under this profile — every detail is normative,
because a single serialization difference changes the hash:

- keys sorted lexicographically by Unicode code point,
- separators `,` and `:` with no whitespace,
- non-ASCII characters escaped as `\uXXXX` with lowercase hex digits (the
  canonical form is pure ASCII),
- strings escaped per RFC 8259, using the short escapes (`\n`, `\"`, `\\`)
  where they exist,
- numbers written in shortest-round-trip IEEE-754 double form, keeping a
  trailing `.0` for integral floats (`0.8`, `1.0` — not `1`); non-finite
  numbers (NaN, Infinity) are not permitted anywhere in a record,
- the SHA-256 input is the UTF-8 (equivalently ASCII) encoding of that
  string.

This matches Python's `json.dumps(payload, sort_keys=True,
separators=(",", ":"))` for conforming records; implementations in languages
whose default JSON serializers differ (e.g. JavaScript emits `1` and literal
Unicode) must implement this profile explicitly — as with any
canonicalization scheme. Migration to RFC 8785 (JCS) is under consideration
for a future schema version; it would change hashes and therefore requires a
`schema_version` bump.

### Test vector

The record below (shown pretty-printed for readability) with
`prev_hash = "0" * 64`:

```json
{
  "subject": "Ship v0.1? — héllo",
  "decision": "yes",
  "confidence": 0.8,
  "positions": [{"agent": "a1", "stance": "yes", "summary": "ready", "confidence": 1.0}],
  "dissent": [],
  "evidence": [{"source": "spec", "ref": "SPEC.md"}],
  "timestamp": "2026-07-11T00:00:00+00:00",
  "schema_version": "0.1"
}
```

has the canonical form:

```
{"confidence":0.8,"decision":"yes","dissent":[],"evidence":[{"ref":"SPEC.md","source":"spec"}],"positions":[{"agent":"a1","confidence":1.0,"stance":"yes","summary":"ready"}],"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","schema_version":"0.1","subject":"Ship v0.1? \u2014 h\u00e9llo","timestamp":"2026-07-11T00:00:00+00:00"}
```

and the hash:

```
06624a603d2f031db60ad142d28addd8f3483d08ebfc2be16e140753d9bc221d
```

An implementation that reproduces this hash conforms to the profile; the
reference test suite pins it (`test_spec_golden_vector`).

```
hash = SHA-256(canonical_form)          # lowercase hex
prev_hash = hash of the preceding record, or "0" * 64 for the first record
```

Because `prev_hash` is inside the hashed content, editing record *N*
invalidates *N*'s own hash, and deleting record *N* breaks record *N+1*'s
chain link. That is the entire tamper-evidence argument.

## Verification

A verifier walks the file in order and, for each record, checks:

1. the line decodes as UTF-8 (else: **invalid encoding**) and parses as a
   JSON object containing every field in the table above
   (else: **malformed record**),
2. `schema_version` is a version this verifier supports
   (else: **unsupported schema version** — a verifier must not certify a
   record it cannot interpret),
3. every field conforms to its declared type and constraints — strings are
   strings, `positions`/`dissent` entries carry string `agent`/`stance`/
   `summary` and a 0–1 `confidence`, `evidence` entries carry string
   `source`/`ref`, `confidence` is a number in 0–1, hashes are 64 lowercase
   hex characters, and `timestamp` parses as ISO 8601 with a UTC offset
   (else: a specific violation reason),
4. `prev_hash` equals the previous record's `hash` — genesis hash for the
   first record (else: **broken chain link**),
5. recomputing the canonical-form hash reproduces `hash`
   (else: **content hash mismatch**),
6. if a head checkpoint is present, the record count and terminal hash match
   it (else: **head checkpoint mismatch (possible truncation)**).

Verification fails at the first violation, reporting the zero-based record
index and the reason. An empty or missing file verifies as intact with zero
records.

## Head checkpoint and trust model

The chain alone cannot detect **tail truncation**: deleting the final record
(or replacing the log with any earlier prefix) leaves a chain that is
internally valid. Conforming writers therefore maintain a sidecar checkpoint,
`<log>.head`, a JSON object `{"count": N, "head_hash": "..."}` updated
atomically after every append. A verification that confirmed the checkpoint
is reported as **anchored**; without a checkpoint it is **unanchored** and
truncation is not detectable.

Writers must **verify before appending** and refuse to extend a log that
fails verification — otherwise an append after truncation would rewrite the
checkpoint and launder the failure. Recovery from a legitimately damaged log
(e.g. an interrupted append leaving a stale checkpoint) is a deliberate
manual act: investigate, then remove the checkpoint; the next append
re-anchors the log as it stands.

Be honest about the trust model: the checkpoint lives in the same directory
as the log, so an attacker who can rewrite both can still truncate silently.
The checkpoint defends against accidental truncation and unsophisticated
tampering; for a hard guarantee, anchor the head hash *outside* the log's
trust domain — commit it to version control, publish it, or send it to an
external timestamping service. Anchoring cadence and transport are
deliberately out of scope for `0.1`.

```bash
uv run caucus verify path/to/decisions.jsonl
```

## Stability

Fields may be added in future minor versions; existing fields will not be
renamed or removed within `0.x`. Verifiers must operate on the raw JSON
object so unknown fields participate in canonical hashing exactly as
written; readers may ignore unknown fields when materializing records.
