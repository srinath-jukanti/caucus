import pytest

from caucus.config import Config, ConfigError
from caucus.evidence import EvidenceError, EvidenceSource, collect


def test_collect_runs_sources_and_fills_defaults():
    source = EvidenceSource(
        name="snapshot",
        command="""python3 -c 'import json; print(json.dumps([{"content": "spy above 200dma"}]))'""",
    )
    items = collect([source])
    assert items == [{"content": "spy above 200dma", "source": "snapshot", "ref": "snapshot"}]


def test_collect_preserves_explicit_source_and_ref():
    source = EvidenceSource(
        name="snapshot",
        command=(
            "python3 -c 'import json; "
            'print(json.dumps([{"source": "quotes", "ref": "SPY", "content": "x"}]))\''
        ),
    )
    assert collect([source])[0]["source"] == "quotes"


def test_failing_source_aborts():
    with pytest.raises(EvidenceError, match="exited 3"):
        collect([EvidenceSource(name="broken", command="echo boom >&2; exit 3")])


def test_non_json_output_aborts():
    with pytest.raises(EvidenceError, match="did not print JSON"):
        collect([EvidenceSource(name="text", command="echo not json")])


def test_non_list_output_aborts():
    with pytest.raises(EvidenceError, match="list of objects"):
        collect([EvidenceSource(name="dict", command="echo '{}'")])


def test_config_parses_evidence_sources(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
evidence_sources:
  - name: snapshot
    command: python3 build_snapshot.py
    timeout_seconds: 30
"""
    )
    config = Config.load(path)
    assert config.evidence_sources == [
        EvidenceSource(name="snapshot", command="python3 build_snapshot.py", timeout_seconds=30)
    ]


@pytest.mark.parametrize(
    "text",
    [
        "evidence_sources: notalist\n",
        "evidence_sources:\n  - name: x\n",
        "evidence_sources:\n  - command: x\n",
        "evidence_sources:\n  - name: x\n    command: y\n    timeout_seconds: -1\n",
        "evidence_sources:\n  - name: x\n    command: y\n    timeout_seconds: true\n",
    ],
)
def test_config_rejects_invalid_evidence_sources(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    with pytest.raises(ConfigError):
        Config.load(path)
