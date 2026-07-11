"""Append-only, hash-chained decision records — the Caucus audit log.

Two guarantees, enforced by construction:
- nothing can be silently altered: each record's hash covers its content;
- nothing can be silently removed: each record embeds its predecessor's hash,
  so deleting a line breaks the successor's link.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = "0.1"
GENESIS_HASH = "0" * 64


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

    def canonical(self) -> str:
        """Deterministic serialization of everything except the hash itself."""
        payload = {k: v for k, v in asdict(self).items() if k != "hash"}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def compute_hash(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()

    def to_line(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_line(cls, line: str) -> DecisionRecord:
        return cls(**json.loads(line))


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
        record.prev_hash = self._last_hash()
        record.hash = record.compute_hash()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(record.to_line() + "\n")
            f.flush()
        return record

    def verify(self) -> VerifyResult:
        """Walk the log, recomputing every hash and chain link."""
        prev = GENESIS_HASH
        count = 0
        for index, line in enumerate(self._lines()):
            try:
                record = DecisionRecord.from_line(line)
            except (json.JSONDecodeError, TypeError):
                return VerifyResult(
                    ok=False, count=count, broken_at=index, reason="malformed record"
                )
            if record.prev_hash != prev:
                return VerifyResult(
                    ok=False, count=count, broken_at=index, reason="broken chain link"
                )
            if record.compute_hash() != record.hash:
                return VerifyResult(
                    ok=False, count=count, broken_at=index, reason="content hash mismatch"
                )
            prev = record.hash
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
        return DecisionRecord.from_line(last).hash
