"""Append-only, hash-chained decision records — the Caucus audit log.

Integrity model (see SPEC.md):
- nothing can be silently altered: each record's hash covers its content;
- nothing can be silently removed from the interior: each record embeds its
  predecessor's hash, so deleting a line breaks the successor's link;
- truncation of the tail is detected via a head checkpoint file maintained
  alongside the log. The checkpoint shares the log's trust domain — for a
  stronger guarantee, anchor the head hash externally (commit it, publish it).

Appends are serialized with a cross-platform lock on a sidecar lock file so
concurrent writers cannot fork the chain.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

try:  # POSIX
    import fcntl

    def _lock_file(handle) -> None:
        fcntl.flock(handle, fcntl.LOCK_EX)

    def _unlock_file(handle) -> None:
        fcntl.flock(handle, fcntl.LOCK_UN)

except ImportError:  # Windows
    import msvcrt

    def _lock_file(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock_file(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


SCHEMA_VERSION = "0.1"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"0.1"})
GENESIS_HASH = "0" * 64
REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "timestamp",
        "subject",
        "positions",
        "decision",
        "dissent",
        "confidence",
        "evidence",
        "prev_hash",
        "hash",
    }
)
_HEX_HASH = re.compile(r"[0-9a-f]{64}")


class LogIntegrityError(RuntimeError):
    """Raised when appending to a log whose existing content fails verification."""


def canonical_form(payload: dict) -> str:
    """Deterministic serialization of a record payload, excluding the hash itself.

    Operates on the raw JSON object so unknown fields added by future minor
    versions participate in hashing, as SPEC.md requires.
    """
    return json.dumps(
        {k: v for k, v in payload.items() if k != "hash"},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_form(payload).encode()).hexdigest()


def _has_non_finite(value) -> bool:
    """SPEC forbids NaN/Infinity anywhere — they are not valid JSON and hash non-portably."""
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_has_non_finite(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_non_finite(v) for v in value)
    return False


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _schema_violation(payload: dict) -> str | None:
    """Return the first schema-0.1 violation, or None if the payload conforms."""
    for key in ("subject", "decision", "timestamp", "schema_version"):
        if not isinstance(payload[key], str):
            return f"invalid {key} type"
    for key in ("positions", "dissent", "evidence"):
        if not isinstance(payload[key], list) or not all(
            isinstance(item, dict) for item in payload[key]
        ):
            return f"invalid {key} structure"
    for key in ("positions", "dissent"):
        for entry in payload[key]:
            if any(not isinstance(entry.get(k), str) for k in ("agent", "stance", "summary")):
                return f"invalid {key} entry"
            if not _valid_confidence(entry.get("confidence")):
                return f"invalid {key} entry"
    for entry in payload["evidence"]:
        if not isinstance(entry.get("source"), str) or not isinstance(entry.get("ref"), str):
            return "invalid evidence entry"
    if not _valid_confidence(payload["confidence"]):
        return "invalid confidence"
    for key in ("hash", "prev_hash"):
        if not isinstance(payload[key], str) or not _HEX_HASH.fullmatch(payload[key]):
            return f"invalid {key} format"
    try:
        parsed = datetime.fromisoformat(payload["timestamp"])
    except ValueError:
        return "invalid timestamp"
    if parsed.utcoffset() != timedelta(0):
        return "timestamp not UTC"
    return None


def _valid_confidence(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float) and 0 <= value <= 1


def _record_violation(payload: dict) -> str | None:
    """Full record validation, shared by the writer and the verifier."""
    if not REQUIRED_FIELDS <= payload.keys():
        return "malformed record"
    if _has_non_finite(payload):
        return "non-finite number"
    if not isinstance(payload["schema_version"], str):
        return "invalid schema_version type"
    if payload["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
        return "unsupported schema version"
    return _schema_violation(payload)


@dataclass
class DecisionRecord:
    """One deliberation outcome. See SPEC.md for the canonical schema."""

    subject: str
    decision: str
    confidence: float
    positions: list[dict] = field(default_factory=list)
    dissent: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=_utc_now)
    schema_version: str = SCHEMA_VERSION
    prev_hash: str = GENESIS_HASH
    hash: str = ""

    def compute_hash(self) -> str:
        return content_hash(asdict(self))

    def to_line(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_line(cls, line: str) -> DecisionRecord:
        """Parse a record line, tolerating unknown fields from future minor versions."""
        data = json.loads(line)
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class VerifyResult:
    ok: bool
    count: int
    broken_at: int | None = None
    reason: str | None = None
    anchored: bool = False


class DecisionLog:
    """One JSONL file; every line is a DecisionRecord chained to its predecessor."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    @property
    def head_path(self) -> Path:
        """Checkpoint recording the expected record count and terminal hash."""
        return self.path.with_name(self.path.name + ".head")

    def append(self, record: DecisionRecord) -> DecisionRecord:
        """Append a record, holding an exclusive lock across read-chain-tip + write.

        Without the lock, two writers could read the same predecessor hash and
        fork the chain; the lock serializes the whole read-modify-append. The
        existing log (including its checkpoint) is verified first — appending
        to a truncated or tampered log would overwrite the checkpoint and
        launder the integrity failure, so it is refused instead. The head
        checkpoint is updated atomically after the record lands.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked():
            existing = self.verify()
            if not existing.ok:
                raise LogIntegrityError(
                    f"refusing to append: existing log fails verification "
                    f"({existing.reason}"
                    + (f", record {existing.broken_at}" if existing.broken_at is not None else "")
                    + ")"
                )
            record.prev_hash, count = self._chain_tip()
            if _has_non_finite(asdict(record)):
                # Checked before hashing — canonical_form would refuse to serialize it.
                raise ValueError("invalid record: non-finite number")
            record.hash = record.compute_hash()
            violation = _record_violation(asdict(record))
            if violation is not None:
                raise ValueError(f"invalid record: {violation}")
            with self.path.open("a", encoding="utf-8") as f:
                f.write(record.to_line() + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._write_head(count + 1, record.hash)
        return record

    def verify(self) -> VerifyResult:
        """Walk the log, checking schema, every content hash, and every chain link.

        Works on the raw JSON objects (not the dataclass) so records carrying
        unknown future fields hash exactly as written. When the head checkpoint
        is present the terminal hash and count are checked against it, which
        detects tail truncation; without it the result is reported unanchored.
        """
        prev = GENESIS_HASH
        count = 0
        try:
            for index, line in enumerate(self._lines()):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    return VerifyResult(
                        ok=False, count=count, broken_at=index, reason="malformed record"
                    )
                if not isinstance(payload, dict):
                    return VerifyResult(
                        ok=False, count=count, broken_at=index, reason="malformed record"
                    )
                violation = _record_violation(payload)
                if violation is not None:
                    return VerifyResult(ok=False, count=count, broken_at=index, reason=violation)
                if payload["prev_hash"] != prev:
                    return VerifyResult(
                        ok=False, count=count, broken_at=index, reason="broken chain link"
                    )
                if content_hash(payload) != payload["hash"]:
                    return VerifyResult(
                        ok=False, count=count, broken_at=index, reason="content hash mismatch"
                    )
                prev = payload["hash"]
                count += 1
        except UnicodeDecodeError:
            # Damaged/tampered bytes must yield a structured failure, not a crash.
            return VerifyResult(ok=False, count=count, broken_at=count, reason="invalid encoding")

        if not self.head_path.exists():
            return VerifyResult(ok=True, count=count, anchored=False)
        try:
            head = json.loads(self.head_path.read_text(encoding="utf-8"))
            expected_count, expected_hash = head["count"], head["head_hash"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return VerifyResult(ok=False, count=count, reason="malformed head checkpoint")
        if expected_count != count or expected_hash != prev:
            return VerifyResult(
                ok=False,
                count=count,
                reason="head checkpoint mismatch (possible truncation)",
            )
        return VerifyResult(ok=True, count=count, anchored=True)

    def __iter__(self) -> Iterator[DecisionRecord]:
        for line in self._lines():
            yield DecisionRecord.from_line(line)

    def _lines(self) -> Iterator[str]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield line

    def _chain_tip(self) -> tuple[str, int]:
        last = None
        count = 0
        for line in self._lines():
            last = line
            count += 1
        if last is None:
            return GENESIS_HASH, 0
        return json.loads(last)["hash"], count

    def _write_head(self, count: int, head_hash: str) -> None:
        tmp = self.head_path.with_name(self.head_path.name + ".tmp")
        tmp.write_text(
            json.dumps({"count": count, "head_hash": head_hash}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.head_path)

    @contextmanager
    def _locked(self):
        lock_path = self.path.with_name(self.path.name + ".lock")
        with lock_path.open("a+") as lock:
            _lock_file(lock)
            try:
                yield
            finally:
                _unlock_file(lock)
