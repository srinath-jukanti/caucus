"""Configuration: one YAML file selecting the log, the backend, and the panel.

Secrets never live here — the openai backend takes the *name* of an
environment variable, not a key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from caucus.backends import Backend, ClaudeCodeBackend, OpenAICompatibleBackend
from caucus.engine import DEFAULT_PANEL, Analyst


class ConfigError(ValueError):
    """Raised when the configuration file cannot be interpreted."""


@dataclass
class Config:
    log: Path = Path("decisions.jsonl")
    backend: Backend = field(default_factory=ClaudeCodeBackend)
    panel: list[Analyst] = field(default_factory=lambda: list(DEFAULT_PANEL))

    @classmethod
    def load(cls, path: Path) -> Config:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ConfigError("config root must be a mapping")
        config = cls()
        if "log" in raw:
            config.log = Path(str(raw["log"]))
        if "backend" in raw:
            config.backend = _build_backend(raw["backend"])
        if "panel" in raw:
            config.panel = _build_panel(raw["panel"])
        return config


def _build_backend(raw: object) -> Backend:
    if not isinstance(raw, dict):
        raise ConfigError("'backend' must be a mapping")
    kind = raw.get("type", "claude")
    if kind == "claude":
        return ClaudeCodeBackend(
            mcp_config=raw.get("mcp_config"),
            allowed_tools=tuple(raw.get("allowed_tools", ())),
        )
    if kind == "openai":
        if not isinstance(raw.get("model"), str):
            raise ConfigError("openai backend requires a string 'model'")
        return OpenAICompatibleBackend(
            model=raw["model"],
            base_url=raw.get("base_url"),
            api_key_env=raw.get("api_key_env", "OPENAI_API_KEY"),
        )
    raise ConfigError(f"unknown backend type {kind!r} (expected 'claude' or 'openai')")


def _build_panel(raw: object) -> list[Analyst]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("'panel' must be a non-empty list")
    panel = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("charge"), str)
        ):
            raise ConfigError("each panel entry needs a string 'name' and 'charge'")
        panel.append(Analyst(name=item["name"], charge=item["charge"]))
    return panel
