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
import os
import signal
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
    # A new session/process group per source: on timeout the WHOLE tree is
    # killed — killing only the shell would leave children holding the output
    # pipes open, hanging the read and defeating the timeout entirely.
    process = subprocess.Popen(
        source.command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=hasattr(os, "setsid"),
    )
    try:
        stdout, stderr = process.communicate(timeout=source.timeout_seconds)
    except subprocess.TimeoutExpired as err:
        _kill_tree(process)
        raise EvidenceError(
            f"evidence source {source.name!r} timed out after {source.timeout_seconds:g}s"
        ) from err
    if process.returncode != 0:
        detail = (stderr or stdout).strip()[-300:]
        raise EvidenceError(
            f"evidence source {source.name!r} exited {process.returncode}: {detail}"
        )
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as err:
        raise EvidenceError(f"evidence source {source.name!r} did not print JSON: {err}") from err
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise EvidenceError(f"evidence source {source.name!r} must print a JSON list of objects")
    for item in parsed:
        item.setdefault("source", source.name)
        item.setdefault("ref", source.name)
    return parsed


def _kill_tree(process: subprocess.Popen) -> None:
    if hasattr(os, "killpg"):
        # start_new_session made the child the group leader, so pgid == pid.
        # Kill the group directly: looking it up via getpgid() races with the
        # leader exiting while children still hold the pipes, and a swallowed
        # lookup error would leave the reap below waiting on those children.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    else:  # Windows: no setsid process groups; kill the direct child
        try:
            process.kill()
        except OSError:
            pass
    try:
        # Bounded reap as the last line of defense — never hang here.
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass
