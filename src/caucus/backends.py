"""Model backends: how deliberation agents actually get their words out.

A backend is anything with `complete(prompt) -> str` — the engine is
provider-agnostic by construction. Bundled implementations:

- ClaudeCodeBackend: the zero-config default; shells out to the locally
  authenticated Claude Code CLI, so no API key is needed.
- OpenAICompatibleBackend: any provider speaking the OpenAI chat-completions
  dialect (OpenAI, Ollama, vLLM, Groq, Together, OpenRouter, ...) selected by
  base_url + model. Optional dependency: `caucus[openai]`.
- CallableBackend: tests and dry runs.
"""

from __future__ import annotations

import os
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
class OpenAICompatibleBackend:
    """Any provider speaking the OpenAI chat-completions dialect.

    The API key is read from the environment variable named by api_key_env,
    never from configuration values; local servers (e.g. Ollama) need none.
    """

    model: str
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    client: object | None = None  # injectable for tests

    def complete(self, prompt: str) -> str:
        client = self.client or self._make_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    def _make_client(self):
        try:
            from openai import OpenAI
        except ImportError as err:
            raise RuntimeError(
                "the openai backend needs the optional dependency: uv add 'caucus[openai]'"
            ) from err
        return OpenAI(base_url=self.base_url, api_key=os.environ.get(self.api_key_env, "unused"))


@dataclass
class CallableBackend:
    """Wraps any `prompt -> text` callable; used in tests and dry runs."""

    fn: Callable[[str], str]

    def complete(self, prompt: str) -> str:
        return self.fn(prompt)
