"""Model backends: how deliberation agents actually get their words out.

A backend is anything with `complete(prompt) -> str`. The reference backend
shells out to the locally authenticated Claude Code CLI, so Caucus needs no
API key of its own; tests and dry runs use CallableBackend.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class Backend(Protocol):
    def complete(self, prompt: str) -> str: ...


@dataclass
class ClaudeCodeBackend:
    """Runs each prompt through `claude -p` using the user's existing login."""

    executable: str = "claude"
    timeout_seconds: float = 600.0

    def complete(self, prompt: str) -> str:
        result = subprocess.run(
            [self.executable, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=True,
        )
        return result.stdout


@dataclass
class CallableBackend:
    """Wraps any `prompt -> text` callable; used in tests and dry runs."""

    fn: Callable[[str], str]

    def complete(self, prompt: str) -> str:
        return self.fn(prompt)
