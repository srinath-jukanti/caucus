"""Briefing orchestration: one run, many subjects, one delivered summary.

A briefing walks the configured agenda — the standing questions every run
must answer — deliberating each subject onto the same decision log, then
renders a human-readable summary. Delivery is a pluggable command (email
script, webhook, anything executable) so Caucus never learns SMTP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from caucus.engine import Deliberation
from caucus.record import DecisionRecord


@dataclass
class Briefing:
    generated_at: str
    records: list[DecisionRecord]

    def to_json(self) -> str:
        return json.dumps(
            {
                "generated_at": self.generated_at,
                "decisions": [
                    {
                        "subject": r.subject,
                        "decision": r.decision,
                        "confidence": r.confidence,
                        "dissent": r.dissent,
                        "hash": r.hash,
                    }
                    for r in self.records
                ],
            },
            indent=2,
        )

    def to_markdown(self) -> str:
        lines = [f"# Caucus briefing — {self.generated_at}", ""]
        for record in self.records:
            lines.append(f"## {record.subject}")
            lines.append("")
            lines.append(f"**DECISION ({record.confidence:.0%} confidence):** {record.decision}")
            for position in record.dissent:
                lines.append(f"- DISSENT [{position['agent']}]: {position['summary']}")
            lines.append(f"- record hash: `{record.hash[:16]}…`")
            lines.append("")
        return "\n".join(lines)


def run_agenda(
    deliberation: Deliberation, agenda: list[str], evidence: list[dict] | None = None
) -> Briefing:
    """Deliberate every agenda subject in order onto the deliberation's log."""
    records = [deliberation.run(subject, evidence) for subject in agenda]
    return Briefing(generated_at=datetime.now(UTC).isoformat(timespec="seconds"), records=records)
