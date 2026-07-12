import pytest
from typer.testing import CliRunner

from caucus.cli import app
from caucus.intents import IntentStore

runner = CliRunner()


@pytest.fixture()
def store(tmp_path):
    return IntentStore(tmp_path / "intents.db")


def test_add_and_get_roundtrip(store):
    intent = store.add(
        name="QQQ trim",
        direction="trim",
        target="0%",
        pacing="weekly tranches",
        cadence_days=7,
        last_acted="2026-07-10",
        notes="full exit",
    )
    fetched = store.get(intent.id)
    assert fetched == intent
    assert fetched.status == "open"
    assert "cadence_days=7" in fetched.summary()


def test_update_fields_and_timestamps(store):
    intent = store.add(name="NVDA build")
    updated = store.update(intent.id, status="paused", last_acted="2026-07-11")
    assert updated.status == "paused"
    assert updated.last_acted == "2026-07-11"
    assert updated.created == intent.created


def test_update_rejects_unknown_fields_and_bad_status(store):
    intent = store.add(name="x")
    with pytest.raises(ValueError, match="unknown intent fields"):
        store.update(intent.id, ticker="QQQ")
    with pytest.raises(ValueError, match="status"):
        store.update(intent.id, status="abandoned")
    with pytest.raises(KeyError):
        store.update(999, status="done")


def test_list_filters_by_status(store):
    store.add(name="a")
    b = store.add(name="b")
    store.update(b.id, status="done")
    assert [i.name for i in store.list()] == ["a", "b"]
    assert [i.name for i in store.list(status="open")] == ["a"]


def test_as_evidence_only_includes_open_intents(store):
    store.add(name="QQQ trim", direction="trim", target="0%", cadence_days=7)
    paused = store.add(name="ASML build")
    store.update(paused.id, status="paused")
    evidence = store.as_evidence()
    assert len(evidence) == 1
    item = evidence[0]
    assert item["source"] == "intents"
    assert "QQQ trim" in item["content"]
    assert isinstance(item["ref"], str)


def test_cli_add_list_update(tmp_path):
    db = str(tmp_path / "intents.db")
    result = runner.invoke(
        app,
        ["intents", "add", "QQQ trim", "--db", db, "--target", "0%", "--cadence-days", "7"],
    )
    assert result.exit_code == 0
    assert "QQQ trim" in result.output

    result = runner.invoke(app, ["intents", "list", "--db", db])
    assert result.exit_code == 0
    assert "target=0%" in result.output

    result = runner.invoke(app, ["intents", "update", "1", "--db", db, "--status", "done"])
    assert result.exit_code == 0
    assert "[done]" in result.output

    result = runner.invoke(app, ["intents", "list", "--db", db, "--status", "open"])
    assert "(no intents)" in result.output


def test_deliberate_refuses_missing_configured_intents_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("intents: missing-intents.db\n")
    result = runner.invoke(app, ["deliberate", "subject"])
    assert result.exit_code == 2
    assert "does not exist" in result.output


def test_cli_update_reports_missing_intent(tmp_path):
    db = str(tmp_path / "intents.db")
    result = runner.invoke(app, ["intents", "update", "42", "--db", db, "--status", "done"])
    assert result.exit_code == 2
