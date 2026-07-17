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
from caucus.evidence import EvidenceSource
from caucus.notify import CommandNotifier, EmailNotifier


class ConfigError(ValueError):
    """Raised when the configuration file cannot be interpreted."""


@dataclass
class Config:
    log: Path = Path("decisions.jsonl")
    backend: Backend = field(default_factory=ClaudeCodeBackend)
    panel: list[Analyst] = field(default_factory=lambda: list(DEFAULT_PANEL))
    intents: Path | None = None
    evidence_sources: list[EvidenceSource] = field(default_factory=list)
    agenda: list[str] = field(default_factory=list)
    notify: EmailNotifier | CommandNotifier | None = None
    anchor_command: str | None = None

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
        if "intents" in raw:
            if not isinstance(raw["intents"], str) or not raw["intents"].strip():
                raise ConfigError("'intents' must be a non-empty string path")
            config.intents = Path(raw["intents"])
        if "backend" in raw:
            config.backend = _build_backend(raw["backend"])
        if "panel" in raw:
            config.panel = _build_panel(raw["panel"])
        if "evidence_sources" in raw:
            config.evidence_sources = _build_evidence_sources(raw["evidence_sources"])
        if "agenda" in raw:
            agenda = raw["agenda"]
            if (
                not isinstance(agenda, list)
                or not agenda
                or not all(isinstance(item, str) and item.strip() for item in agenda)
            ):
                raise ConfigError("'agenda' must be a non-empty list of subject strings")
            config.agenda = agenda
        if "anchor_command" in raw:
            if not isinstance(raw["anchor_command"], str) or not raw["anchor_command"].strip():
                raise ConfigError("'anchor_command' must be a non-empty string")
            config.anchor_command = raw["anchor_command"]
        if "notify" in raw and "notify_command" in raw:
            raise ConfigError("use either 'notify' or 'notify_command', not both")
        if "notify" in raw:
            config.notify = _build_notifier(raw["notify"])
        if "notify_command" in raw:
            if not isinstance(raw["notify_command"], str) or not raw["notify_command"].strip():
                raise ConfigError("'notify_command' must be a non-empty string")
            config.notify = CommandNotifier(command=raw["notify_command"])
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


def _build_notifier(raw: object) -> EmailNotifier | CommandNotifier:
    if not isinstance(raw, dict):
        raise ConfigError("'notify' must be a mapping with a 'type'")
    kind = raw.get("type")
    if kind == "email":
        to = raw.get("to")
        if not isinstance(to, str) or not to.strip():
            raise ConfigError("email notify requires a string 'to' address")
        options = {}
        for key in ("smtp_host", "address_env", "password_env"):
            if key in raw:
                if not isinstance(raw[key], str) or not raw[key].strip():
                    raise ConfigError(f"'{key}' must be a non-empty string")
                options[key] = raw[key]
        if "smtp_port" in raw:
            port = raw["smtp_port"]
            if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
                raise ConfigError("'smtp_port' must be a valid port number")
            options["smtp_port"] = port
        if "subject_template" in raw:
            subject_template = raw["subject_template"]
            if not isinstance(subject_template, str) or not subject_template.strip():
                raise ConfigError("'subject_template' must be a non-empty string")
            try:
                subject_template.format(date="2026-01-01", count=0)
            except (KeyError, IndexError) as err:
                raise ConfigError(
                    f"'subject_template' has an unknown placeholder ({err}); "
                    "available: {date}, {count}"
                ) from err
            options["subject_template"] = subject_template
        if "template" in raw:
            if not isinstance(raw["template"], str) or not raw["template"].strip():
                raise ConfigError("'template' must be a non-empty string path")
            options["template"] = raw["template"]
        return EmailNotifier(to=to, **options)
    if kind == "command":
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ConfigError("command notify requires a string 'command'")
        return CommandNotifier(command=command)
    raise ConfigError(f"unknown notify type {kind!r} (expected 'email' or 'command')")


def _build_evidence_sources(raw: object) -> list[EvidenceSource]:
    if not isinstance(raw, list):
        raise ConfigError("'evidence_sources' must be a list")
    sources = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("command"), str)
        ):
            raise ConfigError("each evidence source needs a string 'name' and 'command'")
        timeout = item.get("timeout_seconds", 120.0)
        if isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0:
            raise ConfigError("'timeout_seconds' must be a positive number")
        sources.append(
            EvidenceSource(name=item["name"], command=item["command"], timeout_seconds=timeout)
        )
    return sources


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
