from typer.testing import CliRunner

from caucus import __version__
from caucus.cli import app
from caucus.record import DecisionLog, DecisionRecord

runner = CliRunner()


def test_version_command_prints_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_verify_command_reports_intact_log(tmp_path):
    log = DecisionLog(tmp_path / "decisions.jsonl")
    log.append(DecisionRecord(subject="subject", decision="yes", confidence=1.0))
    result = runner.invoke(app, ["verify", str(log.path)])
    assert result.exit_code == 0
    assert "chain intact" in result.output


def test_deliberate_rejects_non_object_evidence(tmp_path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text('["just a string"]')
    result = runner.invoke(
        app,
        ["deliberate", "subject", "--evidence", str(evidence), "--log", str(tmp_path / "d.jsonl")],
    )
    assert result.exit_code == 2


def test_deliberate_requires_model_for_openai_backend(tmp_path):
    result = runner.invoke(
        app,
        ["deliberate", "subject", "--backend", "openai", "--log", str(tmp_path / "d.jsonl")],
    )
    assert result.exit_code == 2


def test_deliberate_rejects_config_combined_with_backend_flags(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("log: decisions.jsonl\n")
    result = runner.invoke(
        app,
        [
            "deliberate",
            "subject",
            "--config",
            str(config),
            "--backend",
            "openai",
            "--model",
            "m",
        ],
    )
    assert result.exit_code == 2


def test_deliberate_reports_invalid_config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("backend:\n  type: gemini\n")
    result = runner.invoke(app, ["deliberate", "subject", "--config", str(config)])
    assert result.exit_code == 2


def test_verify_command_fails_on_tampered_log(tmp_path):
    log = DecisionLog(tmp_path / "decisions.jsonl")
    log.append(DecisionRecord(subject="subject", decision="yes", confidence=1.0))
    log.path.write_text(log.path.read_text().replace("subject", "tampered"))
    result = runner.invoke(app, ["verify", str(log.path)])
    assert result.exit_code == 1
