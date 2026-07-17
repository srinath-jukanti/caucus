"""External anchoring: put the chain's head hash beyond the log's trust domain.

The hash chain is unkeyed — an attacker who can rewrite the whole log can
regenerate every hash and the checkpoint, and plain verification will pass.
Anchoring defeats that: each anchor records (count, head_hash) at a moment
in time, and the configured anchor_command ships it somewhere the attacker
cannot rewrite (a git remote, a timestamping service, another machine).
Verification against anchors then proves the past is still the same past.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from caucus.record import DecisionLog


class AnchorError(RuntimeError):
    """Raised when an anchor cannot be created or checked."""


@dataclass
class AnchorResult:
    ok: bool
    checked: int
    reason: str | None = None


def anchors_path_for(log: DecisionLog) -> Path:
    return log.path.with_name(log.path.name + ".anchors")


def append_anchor(log: DecisionLog, anchors_path: Path | None = None) -> dict:
    """Verify the log, then append its current head as an anchor entry.

    The whole operation holds the log's append lock: an append landing
    between verification and the hash read would otherwise produce an
    anchor whose count and head disagree — permanently invalid, and anchors
    are append-only and possibly already shipped.
    """
    with log._locked():
        result = log._verify_locked()
        if not result.ok:
            raise AnchorError(f"refusing to anchor a log that fails verification: {result.reason}")
        if result.count == 0:
            raise AnchorError("nothing to anchor: the log is empty")
        hashes = _chain_hashes(log)
        entry = {
            "anchored_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "count": len(hashes),
            "head_hash": hashes[-1],
        }
        path = anchors_path or anchors_path_for(log)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()
    return entry


def verify_anchors(log: DecisionLog, anchors_path: Path | None = None) -> AnchorResult:
    """Check every anchor against the log's current chain.

    Point anchors_path at an externally fetched copy (from your git remote,
    another machine, ...) to prove the log still contains the exact history
    that existed when each anchor was taken — a full-log rewrite regenerates
    every hash and passes plain verification, but cannot reproduce the
    anchored heads.
    """
    path = anchors_path or anchors_path_for(log)
    if not path.exists():
        raise AnchorError(f"no anchors file at {path}")
    with log._locked():
        # A proof over an unverified chain is no proof: stored hashes are only
        # trustworthy after full verification recomputes them.
        plain = log._verify_locked()
        if not plain.ok:
            return AnchorResult(
                ok=False, checked=0, reason=f"log fails verification: {plain.reason}"
            )
        hashes = _chain_hashes(log)
    checked = 0
    with path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                count, head_hash = entry["count"], entry["head_hash"]
            except (ValueError, KeyError, TypeError):
                return AnchorResult(ok=False, checked=checked, reason=f"malformed anchor {index}")
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                return AnchorResult(ok=False, checked=checked, reason=f"malformed anchor {index}")
            if count > len(hashes):
                return AnchorResult(
                    ok=False,
                    checked=checked,
                    reason=f"anchor {index} covers {count} records but the log has {len(hashes)}",
                )
            if hashes[count - 1] != head_hash:
                return AnchorResult(
                    ok=False,
                    checked=checked,
                    reason=f"anchor {index} mismatch at record {count} — history rewritten",
                )
            checked += 1
    return AnchorResult(ok=True, checked=checked)


def _chain_hashes(log: DecisionLog) -> list[str]:
    hashes = []
    for record in log:
        hashes.append(record.hash)
    return hashes
