"""Append-only, hash-chained decision records — the Caucus audit log.

Two guarantees, enforced by construction:
- nothing can be silently altered: each record's hash covers its content;
- nothing can be silently removed: each record embeds its predecessor's hash,
  so deleting a line breaks the successor's link.

Appends are serialized with an advisory file lock so concurrent writers
cannot fork the chain.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path

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


def canonical_form(payload: dict) -> str:
    """Deterministic serialization of a record payload, excluding the hash itself.

    Operates on the raw JSON object so unknown fields added by future minor
    versions participate in hashing, as SPEC.md requires.
    """
    return json.dumps(
        {k: v for k, v in payload.items() if k != "hash"},
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_form(payload).encode()).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

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


class DecisionLog:
    """One JSONL file; every line is a DecisionRecord chained to its predecessor."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def append(self, record: DecisionRecord) -> DecisionRecord:
        """Append a record, holding an exclusive lock across read-chain-tip + write.

        Without the lock, two writers could read the same predecessor hash and
        fork the chain; the lock serializes the whole read-modify-append.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                record.prev_hash = self._last_hash()
                record.hash = record.compute_hash()
                f.write(record.to_line() + "\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return record

    def verify(self) -> VerifyResult:
        """Walk the log, checking schema, every content hash, and every chain link.

        Verification works on the raw JSON objects (not the dataclass) so that
        records carrying unknown future fields still hash exactly as written.
        """
        prev = GENESIS_HASH
        count = 0
        for index, line in enumerate(self._lines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                return VerifyResult(
                    ok=False, count=count, broken_at=index, reason="malformed record"
                )
            if not isinstance(payload, dict) or not REQUIRED_FIELDS <= payload.keys():
                return VerifyResult(
                    ok=False, count=count, broken_at=index, reason="malformed record"
                )
            if payload["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
                return VerifyResult(
                    ok=False, count=count, broken_at=index, reason="unsupported schema version"
                )
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
        return VerifyResult(ok=True, count=count)

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

    def _last_hash(self) -> str:
        last = None
        for line in self._lines():
            last = line
        if last is None:
            return GENESIS_HASH
        return json.loads(last)["hash"]
