import pytest

from caucus.record import GENESIS_HASH, DecisionLog, DecisionRecord


def make_record(subject="Trim QQQ?", decision="yes"):
    return DecisionRecord(
        subject=subject,
        decision=decision,
        confidence=0.8,
        positions=[{"agent": "macro", "stance": "yes", "summary": "overweight", "confidence": 0.9}],
        dissent=[
            {"agent": "momentum", "stance": "no", "summary": "trend intact", "confidence": 0.6}
        ],
        evidence=[{"source": "quotes", "ref": "QQQ@725.60"}],
        timestamp="2026-07-11T00:00:00+00:00",
    )


@pytest.fixture()
def log(tmp_path):
    return DecisionLog(tmp_path / "decisions.jsonl")


def test_chain_links_records(log):
    first = log.append(make_record())
    second = log.append(make_record(subject="Add NVDA?"))
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.hash


def test_verify_intact_log(log):
    for i in range(3):
        log.append(make_record(subject=f"subject {i}"))
    result = log.verify()
    assert result.ok
    assert result.count == 3


def test_verify_empty_log(log):
    result = log.verify()
    assert result.ok
    assert result.count == 0


def test_verify_detects_edited_record(log):
    log.append(make_record())
    log.append(make_record(subject="Add NVDA?"))
    lines = log.path.read_text().splitlines()
    lines[0] = lines[0].replace("Trim QQQ?", "Trim GLD?")
    log.path.write_text("\n".join(lines) + "\n")
    result = log.verify()
    assert not result.ok
    assert result.broken_at == 0
    assert result.reason == "content hash mismatch"


def test_verify_detects_deleted_record(log):
    for i in range(3):
        log.append(make_record(subject=f"subject {i}"))
    lines = log.path.read_text().splitlines()
    del lines[1]
    log.path.write_text("\n".join(lines) + "\n")
    result = log.verify()
    assert not result.ok
    assert result.broken_at == 1
    assert result.reason == "broken chain link"


def test_record_round_trip(log):
    record = log.append(make_record())
    parsed = DecisionRecord.from_line(record.to_line())
    assert parsed == record
    assert parsed.compute_hash() == record.hash


def test_iteration_preserves_order(log):
    subjects = [f"subject {i}" for i in range(3)]
    for subject in subjects:
        log.append(make_record(subject=subject))
    assert [r.subject for r in log] == subjects
