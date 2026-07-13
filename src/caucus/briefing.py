"""Briefing orchestration: one run, many subjects, one delivered summary.

A briefing walks the configured agenda — the standing questions every run
must answer — deliberating each subject onto the same decision log, then
renders a human-readable summary. Rendering is deterministic: templates are
authored once (by hand or by an agent during setup) and produce the same
email for the same record — the delivered briefing is a faithful rendering
of the log, never a paraphrase.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from caucus.engine import Deliberation
from caucus.record import DecisionRecord


class TemplateRenderError(RuntimeError):
    """Raised when a briefing template cannot be rendered."""


@dataclass
class Briefing:
    generated_at: str
    records: list[DecisionRecord]

    def context(self) -> dict:
        """The template/JSON context: everything a rendering may reference."""
        return {
            "generated_at": self.generated_at,
            "decisions": [
                {
                    "subject": r.subject,
                    "decision": r.decision,
                    "confidence": r.confidence,
                    "positions": r.positions,
                    "dissent": r.dissent,
                    "hash": r.hash,
                }
                for r in self.records
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.context(), indent=2)

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


def render_template(briefing: Briefing, template_path: Path) -> str:
    """Render the briefing through a user-authored Jinja2 template.

    HTML templates are autoescaped (record content is untrusted model output)
    and undefined variables fail loudly rather than rendering blanks.
    """
    import jinja2

    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path.parent)),
        # select_autoescape only matches the FINAL extension, so 'x.html.j2'
        # would silently skip escaping — use the same detection as delivery.
        autoescape=lambda name: bool(name) and template_subtype(Path(name)) == "html",
        undefined=jinja2.StrictUndefined,
    )
    try:
        template = environment.get_template(template_path.name)
        return template.render(**briefing.context())
    except jinja2.TemplateError as err:
        raise TemplateRenderError(f"template {template_path} failed: {err}") from err


def template_subtype(template_path: Path) -> str:
    """MIME subtype for an email rendered from this template."""
    return "html" if {".html", ".htm"} & set(template_path.suffixes) else "plain"


def run_agenda(
    deliberation: Deliberation, agenda: list[str], evidence: list[dict] | None = None
) -> Briefing:
    """Deliberate every agenda subject in order onto the deliberation's log."""
    records = [deliberation.run(subject, evidence) for subject in agenda]
    return Briefing(generated_at=datetime.now(UTC).isoformat(timespec="seconds"), records=records)
