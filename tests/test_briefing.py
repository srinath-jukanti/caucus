import json

import pytest
from typer.testing import CliRunner

from caucus.backends import CallableBackend
from caucus.briefing import run_agenda
from caucus.cli import app
from caucus.config import Config, ConfigError
from caucus.engine import Deliberation
from caucus.record import DecisionLog

runner = CliRunner()

POSITION = {"stance": "for", "summary": "solid", "confidence": 0.7}
VERDICT = {"stance": "for", "decision": "Proceed.", "confidence": 0.8}


def backend():
    def fn(prompt):
        payload = VERDICT if "PANEL POSITIONS" in prompt else POSITION
        return json.dumps(payload)

    return CallableBackend(fn)


@pytest.fixture()
def log(tmp_path):
    return DecisionLog(tmp_path / "decisions.jsonl")


def test_run_agenda_deliberates_every_subject_in_order(log):
    deliberation = Deliberation(backend=backend(), log=log)
    result = run_agenda(deliberation, ["First question?", "Second question?"])
    assert [r.subject for r in result.records] == ["First question?", "Second question?"]
    verified = log.verify()
    assert verified.ok
    assert verified.count == 2


def test_briefing_renders_markdown_and_json(log):
    deliberation = Deliberation(backend=backend(), log=log)
    result = run_agenda(deliberation, ["First question?"])
    markdown = result.to_markdown()
    assert "# Caucus briefing" in markdown
    assert "## First question?" in markdown
    assert "DECISION (80% confidence)" in markdown
    payload = json.loads(result.to_json())
    assert payload["decisions"][0]["subject"] == "First question?"
    assert payload["decisions"][0]["hash"]


def test_config_parses_agenda_and_notify(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
agenda:
  - "Question one?"
  - "Question two?"
notify_command: bash send_briefing.sh
"""
    )
    config = Config.load(path)
    assert config.agenda == ["Question one?", "Question two?"]
    from caucus.notify import CommandNotifier

    assert config.notify == CommandNotifier(command="bash send_briefing.sh")


@pytest.mark.parametrize(
    "text",
    [
        "agenda: []\n",
        "agenda: notalist\n",
        "agenda:\n  - ''\n",
        "agenda:\n  - 42\n",
        "notify_command: ''\n",
        "notify_command: [a]\n",
    ],
)
def test_config_rejects_invalid_agenda_and_notify(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    with pytest.raises(ConfigError):
        Config.load(path)


def test_briefing_cli_requires_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["briefing"])
    assert result.exit_code == 2
    assert "requires a config" in result.output


def test_briefing_cli_requires_agenda(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("log: decisions.jsonl\n")
    result = runner.invoke(app, ["briefing"])
    assert result.exit_code == 2
    assert "agenda" in result.output
