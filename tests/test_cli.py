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


def test_verify_command_fails_on_tampered_log(tmp_path):
    log = DecisionLog(tmp_path / "decisions.jsonl")
    log.append(DecisionRecord(subject="subject", decision="yes", confidence=1.0))
    log.path.write_text(log.path.read_text().replace("subject", "tampered"))
    result = runner.invoke(app, ["verify", str(log.path)])
    assert result.exit_code == 1
