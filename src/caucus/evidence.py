"""External evidence sources: commands whose JSON output becomes evidence.

This is how deterministic computation stays outside the model: a source
command computes indicators, snapshots, or state in plain code and prints a
JSON list of evidence items; the panel reasons over the numbers instead of
producing them. Sources fail closed — a broken source aborts the
deliberation rather than letting the panel proceed with silently missing
evidence.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


class EvidenceError(RuntimeError):
    """Raised when an evidence source cannot produce usable evidence."""


@dataclass
class EvidenceSource:
    """A shell command printing a JSON list of {source, ref, content, ...} objects.

    Commands come from the user's own configuration and run with the user's
    own privileges — the same trust model as a Makefile.
    """

    name: str
    command: str
    timeout_seconds: float = 120.0


def collect(sources: list[EvidenceSource]) -> list[dict]:
    """Run every source and return the combined evidence items."""
    items: list[dict] = []
    for source in sources:
        items.extend(_run(source))
    return items


def _run(source: EvidenceSource) -> list[dict]:
    try:
        result = subprocess.run(
            source.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=source.timeout_seconds,
        )
    except subprocess.TimeoutExpired as err:
        raise EvidenceError(
            f"evidence source {source.name!r} timed out after {source.timeout_seconds:g}s"
        ) from err
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-300:]
        raise EvidenceError(f"evidence source {source.name!r} exited {result.returncode}: {detail}")
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as err:
        raise EvidenceError(f"evidence source {source.name!r} did not print JSON: {err}") from err
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise EvidenceError(f"evidence source {source.name!r} must print a JSON list of objects")
    for item in parsed:
        item.setdefault("source", source.name)
        item.setdefault("ref", source.name)
    return parsed
