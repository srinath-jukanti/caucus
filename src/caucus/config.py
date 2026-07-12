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
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError as err:
            raise ConfigError(f"cannot read config file: {err}") from err
        except yaml.YAMLError as err:
            raise ConfigError(f"invalid YAML: {err}") from err
        if not isinstance(raw, dict):
            raise ConfigError("config root must be a mapping")
        config = cls()
        if "log" in raw:
            if not isinstance(raw["log"], str) or not raw["log"].strip():
                raise ConfigError("'log' must be a non-empty string path")
            config.log = Path(raw["log"])
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
        mcp_config = raw.get("mcp_config")
        if mcp_config is not None and not isinstance(mcp_config, str):
            raise ConfigError("'mcp_config' must be a string path")
        allowed_tools = raw.get("allowed_tools") or []
        if not isinstance(allowed_tools, list) or not all(
            isinstance(tool, str) for tool in allowed_tools
        ):
            raise ConfigError("'allowed_tools' must be a list of strings")
        return ClaudeCodeBackend(mcp_config=mcp_config, allowed_tools=tuple(allowed_tools))
    if kind == "openai":
        if not isinstance(raw.get("model"), str):
            raise ConfigError("openai backend requires a string 'model'")
        base_url = raw.get("base_url")
        if base_url is not None and not isinstance(base_url, str):
            raise ConfigError("'base_url' must be a string")
        api_key_env = raw.get("api_key_env", "OPENAI_API_KEY")
        if not isinstance(api_key_env, str):
            raise ConfigError("'api_key_env' must be a string")
        return OpenAICompatibleBackend(
            model=raw["model"], base_url=base_url, api_key_env=api_key_env
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
