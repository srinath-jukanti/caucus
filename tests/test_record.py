import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from caucus.record import (
    GENESIS_HASH,
    DecisionLog,
    DecisionRecord,
    LogIntegrityError,
    content_hash,
)


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


def rewrite_single_record(log, payload):
    """Rewrite a one-record log the way a conforming writer would — checkpoint included."""
    log.path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    log.head_path.write_text(json.dumps({"count": 1, "head_hash": payload["hash"]}))


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
    assert result.anchored


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


def test_verify_rejects_unsupported_schema_version(log):
    log.append(make_record())
    payload = json.loads(log.path.read_text())
    payload["schema_version"] = "9.0"
    payload["hash"] = content_hash(payload)
    log.path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    result = log.verify()
    assert not result.ok
    assert result.broken_at == 0
    assert result.reason == "unsupported schema version"


def test_verify_tolerates_unknown_fields(log):
    log.append(make_record())
    payload = json.loads(log.path.read_text())
    payload["future_field"] = "added by a later 0.x version"
    payload["hash"] = content_hash(payload)
    rewrite_single_record(log, payload)
    result = log.verify()
    assert result.ok
    assert result.count == 1
    assert next(iter(log)).subject == "Trim QQQ?"


def test_verify_detects_tail_truncation(log):
    for i in range(3):
        log.append(make_record(subject=f"subject {i}"))
    lines = log.path.read_text().splitlines()
    log.path.write_text("\n".join(lines[:-1]) + "\n")
    result = log.verify()
    assert not result.ok
    assert result.reason == "head checkpoint mismatch (possible truncation)"


def test_verify_without_checkpoint_is_unanchored(log):
    log.append(make_record())
    log.head_path.unlink()
    result = log.verify()
    assert result.ok
    assert not result.anchored


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"confidence": 1.5}, "invalid confidence"),
        ({"confidence": "high"}, "invalid confidence"),
        ({"timestamp": "not-a-timestamp"}, "invalid timestamp"),
        ({"timestamp": "2026-07-11T00:00:00"}, "timestamp not UTC"),
        ({"timestamp": "2026-07-11T00:00:00+05:30"}, "timestamp not UTC"),
        ({"positions": "not-a-list"}, "invalid positions structure"),
        (
            {"positions": [{"stance": "yes", "summary": "s", "confidence": 0.5}]},
            "invalid positions entry",
        ),
        (
            {"dissent": [{"agent": "a", "stance": "no", "summary": "s", "confidence": "high"}]},
            "invalid dissent entry",
        ),
        ({"evidence": [{"source": "quotes"}]}, "invalid evidence entry"),
        ({"prev_hash": "abc"}, "invalid prev_hash format"),
    ],
)
def test_verify_enforces_schema(log, mutation, reason):
    log.append(make_record())
    payload = json.loads(log.path.read_text())
    payload.update(mutation)
    payload["hash"] = content_hash(payload)
    rewrite_single_record(log, payload)
    result = log.verify()
    assert not result.ok
    assert result.broken_at == 0
    assert result.reason == reason


def test_verify_accepts_zulu_timestamp(log):
    log.append(make_record())
    payload = json.loads(log.path.read_text())
    payload["timestamp"] = "2026-07-11T00:00:00Z"
    payload["hash"] = content_hash(payload)
    rewrite_single_record(log, payload)
    assert log.verify().ok


@pytest.mark.parametrize(
    "spoil",
    [
        lambda r: setattr(r, "confidence", 2.0),
        lambda r: setattr(r, "timestamp", "2026-07-11T00:00:00"),
        lambda r: setattr(r, "schema_version", "9.0"),
        lambda r: setattr(r, "positions", [{"stance": "yes"}]),
    ],
)
def test_append_rejects_invalid_record(log, spoil):
    log.append(make_record())
    log_before = log.path.read_text()
    head_before = log.head_path.read_text()
    bad = make_record()
    spoil(bad)
    with pytest.raises(ValueError, match="invalid record"):
        log.append(bad)
    assert log.path.read_text() == log_before
    assert log.head_path.read_text() == head_before


def test_verify_reports_unhashable_schema_version(log):
    log.append(make_record())
    payload = json.loads(log.path.read_text())
    payload["schema_version"] = ["0.1"]
    payload["hash"] = content_hash(payload)
    rewrite_single_record(log, payload)
    result = log.verify()
    assert not result.ok
    assert result.broken_at == 0
    assert result.reason == "invalid schema_version type"


def test_append_refuses_truncated_log(log):
    for i in range(3):
        log.append(make_record(subject=f"subject {i}"))
    head_before = log.head_path.read_text()
    lines = log.path.read_text().splitlines()
    log.path.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(LogIntegrityError):
        log.append(make_record(subject="laundered"))
    assert log.head_path.read_text() == head_before


def test_verify_rejects_duplicate_keys(log):
    log.append(make_record())
    line = log.path.read_text().rstrip("\n")
    # Smuggle an earlier duplicate: last-wins parsers keep the original value,
    # so the hash still matches — only duplicate-key rejection catches this.
    log.path.write_text('{"decision":"altered",' + line[1:] + "\n")
    result = log.verify()
    assert not result.ok
    assert result.broken_at == 0
    assert result.reason == "duplicate key"


def test_verify_rejects_nested_duplicate_keys(log):
    log.append(make_record())
    line = log.path.read_text().rstrip("\n")
    smuggled = line.replace('{"agent":"macro"', '{"agent":"smuggled","agent":"macro"', 1)
    assert smuggled != line
    log.path.write_text(smuggled + "\n")
    result = log.verify()
    assert not result.ok
    assert result.reason == "duplicate key"


def test_verify_reports_checkpoint_with_invalid_encoding(log):
    log.append(make_record())
    log.head_path.write_bytes(b"\xff\xfe")
    result = log.verify()
    assert not result.ok
    assert result.reason == "malformed head checkpoint"


def test_append_rejects_non_finite_numbers(log):
    log.append(make_record())
    log_before = log.path.read_text()
    bad = make_record()
    bad.evidence = [{"source": "quotes", "ref": "x", "weight": float("nan")}]
    with pytest.raises(ValueError, match="non-finite number"):
        log.append(bad)
    assert log.path.read_text() == log_before


def test_verify_rejects_non_finite_numbers(log):
    log.append(make_record())
    payload = json.loads(log.path.read_text())
    payload["future_field"] = float("inf")
    # Simulates a hostile writer: stdlib dumps emits the non-standard Infinity token.
    log.path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    result = log.verify()
    assert not result.ok
    assert result.broken_at == 0
    assert result.reason == "non-finite number"


def test_spec_golden_vector():
    """Pins the SPEC.md test vector — a serialization change here breaks all hashes."""
    record = DecisionRecord(
        subject="Ship v0.1? — héllo",
        decision="yes",
        confidence=0.8,
        positions=[{"agent": "a1", "stance": "yes", "summary": "ready", "confidence": 1.0}],
        dissent=[],
        evidence=[{"source": "spec", "ref": "SPEC.md"}],
        timestamp="2026-07-11T00:00:00+00:00",
    )
    assert (
        record.compute_hash() == "06624a603d2f031db60ad142d28addd8f3483d08ebfc2be16e140753d9bc221d"
    )


def test_verify_reports_invalid_encoding(log):
    log.append(make_record())
    with log.path.open("ab") as f:
        f.write(b'{"subject": "\xff\xfe"}\n')
    result = log.verify()
    assert not result.ok
    # Buffered decoding may surface the error before the damaged line is
    # yielded, so the reason is pinned but the exact index is not.
    assert result.reason == "invalid encoding"


def test_concurrent_appends_keep_chain_intact(log):
    def worker(i):
        # Each append opens its own handle, so the file lock is what serializes them.
        DecisionLog(log.path).append(make_record(subject=f"subject {i}"))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, range(20)))
    result = log.verify()
    assert result.ok
    assert result.count == 20
