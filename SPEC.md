# Caucus Decision Record — Specification

**Versions 0.1 and 0.2** (the `schema_version` field). 0.2 adds one
optional field: `rounds` — an array of position-arrays recording each
deliberation round when more than one occurred. **The version marks feature
use**: writers label a record 0.2 only when `rounds` is present; records
without it are written as 0.1 and therefore remain byte- and hash-identical
to pre-0.2 records. Verifiers reject `rounds` in a record labeled 0.1, and
validate each rounds entry against the `positions` entry shape in 0.2. This document is the normative
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
| `schema_version` | string | `"0.1"`, or `"0.2"` when (and only when) `rounds` is present |
| `timestamp` | string | ISO 8601 with an explicit UTC offset (`Z` or `+00:00`); naive or non-UTC timestamps do not conform |
| `subject` | string | what was deliberated |
| `positions` | array of objects | one per agent: `agent`, `stance`, `summary` (strings) and `confidence` (number, 0–1) |
| `decision` | string | the consensus outcome |
| `dissent` | array of objects | positions that disagreed with the outcome — same entry shape as `positions`, recorded, never dropped |
| `confidence` | number | consensus confidence, 0–1 |
| `evidence` | array of objects | citations grounding the decision: `source` and `ref` (strings) |
| `rounds` | array of arrays (0.2 only, optional) | each deliberation round's positions, oldest first, entries shaped exactly like `positions` entries; omitted entirely when absent |
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
- floats spelled exactly as CPython's `repr`/`json.dumps` algorithm emits
  them: the shortest decimal string that round-trips the IEEE-754 double,
  rendered with Python's notation rules — exponent form only when the
  decimal exponent is ≥ 16 or ≤ −5, written with an explicit sign and
  two-digit zero-padded exponent (`1e+20`, `1e-07` — never `1e-7`); a
  trailing `.0` for integral floats in decimal form (`1.0` — not `1`);
  negative zero preserved (`-0.0`). **This exact spelling is normative**
  (a bare "shortest form" rule would be ambiguous for exponent-form
  values); the float vectors below pin it,
- non-finite numbers (NaN, Infinity) are not permitted anywhere in a
  record, and integers must lie within the IEEE-754 exactly-representable
  range (|n| ≤ 2^53) — larger integers hash non-portably across
  implementations and do not conform, in known fields or unknown ones,
- the SHA-256 input is the UTF-8 (equivalently ASCII) encoding of that
  string.

The profile is, by construction, exactly the output of Python's
`json.dumps(payload, sort_keys=True, separators=(",", ":"))`;
implementations in languages whose serializers differ (e.g. JavaScript
emits `1` for integral floats, literal Unicode, and `1e-7`-style
exponents) must implement this profile explicitly — as with any
canonicalization scheme. Migration to RFC 8785 (JCS) is under
consideration for a future schema version; it would change hashes and
therefore requires a `schema_version` bump.

#### Float spelling vectors

| double value | canonical spelling |
|---|---|
| 0.8 | `0.8` |
| 1.0 | `1.0` |
| 10⁻⁷ | `1e-07` |
| 10²⁰ | `1e+20` |
| −0.0 | `-0.0` |
| 0.0001 | `0.0001` |
| 0.00001 | `1e-05` |
| 10¹⁵ | `1000000000000000.0` |

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
   (else: **malformed record**); no object at any level may contain
   duplicate keys — JSON parsers disagree on duplicate-key resolution, so a
   duplicate would give one hashed record multiple readings
   (else: **duplicate key**),
2. `schema_version` is a version this verifier supports
   (else: **unsupported schema version** — a verifier must not certify a
   record it cannot interpret),
3. every field conforms to its declared type and constraints — strings are
   strings, `positions`/`dissent` entries carry string `agent`/`stance`/
   `summary` and a 0–1 `confidence`, `evidence` entries carry string
   `source`/`ref`, `confidence` is a number in 0–1, hashes are 64 lowercase
   hex characters, `timestamp` parses as ISO 8601 with a UTC offset, and
   every number anywhere in the record — known fields or not — is finite
   and within the IEEE-754 safe-integer range
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
atomically after every append — `count` is a non-negative integer within
the safe-integer range (a JSON boolean does not conform) and `head_hash`
is 64 lowercase hex characters; verifiers must validate both types before
comparing, or malformed checkpoint data could earn the stronger anchored
result. A verification that confirmed the checkpoint is reported as
**anchored**; without a checkpoint it is **unanchored** and truncation is
not detectable.

Writers must **verify before appending** and refuse to extend a log that
fails verification — otherwise an append after truncation would rewrite the
checkpoint and launder the failure. Recovery from a legitimately damaged log
(e.g. an interrupted append leaving a stale checkpoint) is a deliberate
manual act: investigate, then remove the checkpoint; the next append
re-anchors the log as it stands.

## External anchoring

The chain is unkeyed: an attacker who can rewrite the whole log can
regenerate every hash and the checkpoint, and plain verification passes.
Anchoring defeats this. An **anchors file** (`<log>.anchors`) is append-only
JSONL of `{"anchored_at": <ISO-8601 UTC>, "count": N, "head_hash": "..."}`
entries, each recording the chain's head at a moment in time. What makes an
anchor binding is shipping it **outside the log's trust domain** — a git
remote, a timestamping service, another machine — via the configured
`anchor_command` (which receives the anchors-file path).

Anchor verification recomputes the chain and requires, for every anchor,
that the hash of record `count` equals `head_hash`. A rewritten history
cannot reproduce previously anchored heads; a log shorter than an anchor's
`count` fails likewise. Writers refuse to anchor a log that fails plain
verification.

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
