import pytest
from typer.testing import CliRunner

from caucus.anchor import AnchorError, anchors_path_for, append_anchor, verify_anchors
from caucus.cli import app
from caucus.record import DecisionLog, DecisionRecord

runner = CliRunner()


def make_record(subject="q", decision="yes"):
    return DecisionRecord(
        subject=subject,
        decision=decision,
        confidence=0.7,
        timestamp="2026-07-17T00:00:00+00:00",
    )


@pytest.fixture()
def log(tmp_path):
    return DecisionLog(tmp_path / "decisions.jsonl")


def test_anchor_and_verify_roundtrip(log):
    for i in range(3):
        log.append(make_record(subject=f"q{i}"))
    entry = append_anchor(log)
    assert entry["count"] == 3
    result = verify_anchors(log)
    assert result.ok
    assert result.checked == 1
    log.append(make_record(subject="q3"))
    assert verify_anchors(log).ok  # anchors cover prefixes; growth is fine


def test_full_rewrite_passes_plain_verify_but_fails_anchors(log):
    for i in range(3):
        log.append(make_record(subject=f"original {i}"))
    append_anchor(log)
    # Attacker rewrites the ENTIRE log — regenerating every hash and the
    # checkpoint. Plain verification cannot tell; the anchor can.
    anchors = anchors_path_for(log)
    saved_anchors = anchors.read_text()
    log.path.unlink()
    log.head_path.unlink()
    rewritten = DecisionLog(log.path)
    for i in range(3):
        rewritten.append(make_record(subject=f"forged {i}"))
    assert rewritten.verify().ok, "plain verify is expected to pass — that is the attack"
    anchors.write_text(saved_anchors)  # the externally kept copy
    result = verify_anchors(rewritten)
    assert not result.ok
    assert "history rewritten" in result.reason


def test_anchor_refuses_bad_or_empty_logs(log):
    with pytest.raises(AnchorError, match="empty"):
        append_anchor(log)
    log.append(make_record())
    lines = log.path.read_text().replace("yes", "no")
    log.path.write_text(lines)
    with pytest.raises(AnchorError, match="fails verification"):
        append_anchor(log)


def test_truncation_below_anchor_detected(log):
    for i in range(3):
        log.append(make_record(subject=f"q{i}"))
    append_anchor(log)
    kept = log.path.read_text().splitlines()[0]
    log.path.write_text(kept + "\n")
    result = verify_anchors(log)
    assert not result.ok
    # The mandatory verification pass catches this via the checkpoint before
    # the anchor-count comparison would — either reason proves the truncation.
    assert "truncation" in result.reason or "covers 3 records" in result.reason


def test_cli_anchor_and_verify(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log = DecisionLog(tmp_path / "decisions.jsonl")
    log.append(make_record())
    result = runner.invoke(app, ["anchor"])
    assert result.exit_code == 0, result.output
    assert "anchored 1 records" in result.output
    result = runner.invoke(
        app,
        ["verify", "decisions.jsonl", "--anchors", "decisions.jsonl.anchors"],
    )
    assert result.exit_code == 0, result.output
    assert "anchors OK" in result.output


def test_verify_anchors_rejects_tampered_log_with_stale_stored_hashes(log):
    log.append(make_record(subject="honest"))
    append_anchor(log)
    # Edit content but LEAVE the stored hash untouched — the stored-hash
    # comparison alone would falsely certify this.
    log.path.write_text(log.path.read_text().replace("honest", "forged"))
    result = verify_anchors(log)
    assert not result.ok
    assert "fails verification" in result.reason


def test_concurrent_appends_during_anchoring_stay_consistent(log):
    from concurrent.futures import ThreadPoolExecutor

    log.append(make_record(subject="seed"))

    def appender():
        for i in range(5):
            DecisionLog(log.path).append(make_record(subject=f"c{i}"))

    def anchorer():
        for _ in range(5):
            append_anchor(DecisionLog(log.path))

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(appender), pool.submit(anchorer)]
        for job in jobs:
            job.result()
    result = verify_anchors(log)
    assert result.ok
    assert result.checked == 5


def test_empty_anchors_file_is_not_a_proof(log):
    log.append(make_record())
    anchors = anchors_path_for(log)
    anchors.write_text("")
    result = verify_anchors(log)
    assert not result.ok
    assert "no anchors" in result.reason
    anchors.write_text("\n\n")
    result = verify_anchors(log)
    assert not result.ok
