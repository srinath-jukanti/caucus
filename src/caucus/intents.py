"""Durable intents: the standing plans deliberations must respect.

An intent is a slow-moving goal the system works toward across many runs —
"trim QQQ to 0% in weekly tranches", "migrate service X off the legacy
queue". Deliberating without them is how a panel with perfect live data
still reaches the wrong answer: the plan is evidence too.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    pacing TEXT NOT NULL DEFAULT '',
    cadence_days INTEGER,
    last_acted TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    notes TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    updated TEXT NOT NULL
)
"""

_FIELDS = (
    "id",
    "name",
    "direction",
    "target",
    "pacing",
    "cadence_days",
    "last_acted",
    "status",
    "notes",
    "created",
    "updated",
)

STATUSES = ("open", "paused", "done")


@dataclass
class Intent:
    id: int
    name: str
    direction: str
    target: str
    pacing: str
    cadence_days: int | None
    last_acted: str | None
    status: str
    notes: str
    created: str
    updated: str

    def summary(self) -> str:
        parts = [f"intent '{self.name}' [{self.status}]"]
        if self.direction:
            parts.append(f"direction={self.direction}")
        if self.target:
            parts.append(f"target={self.target}")
        if self.pacing:
            parts.append(f"pacing={self.pacing}")
        if self.cadence_days is not None:
            parts.append(f"cadence_days={self.cadence_days}")
        if self.last_acted:
            parts.append(f"last_acted={self.last_acted}")
        if self.notes:
            parts.append(f"notes={self.notes}")
        return ", ".join(parts)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class IntentStore:
    """SQLite-backed store; one file, inspectable with the sqlite3 CLI."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def add(
        self,
        name: str,
        direction: str = "",
        target: str = "",
        pacing: str = "",
        cadence_days: int | None = None,
        last_acted: str | None = None,
        status: str = "open",
        notes: str = "",
    ) -> Intent:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        now = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO intents (name, direction, target, pacing, cadence_days,"
                " last_acted, status, notes, created, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    name,
                    direction,
                    target,
                    pacing,
                    cadence_days,
                    last_acted,
                    status,
                    notes,
                    now,
                    now,
                ),
            )
            intent_id = cursor.lastrowid
        # Read back outside the insert transaction — the context manager commits
        # on exit, and get() opens its own connection.
        return self.get(intent_id)

    def get(self, intent_id: int) -> Intent:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {', '.join(_FIELDS)} FROM intents WHERE id = ?", (intent_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"no intent with id {intent_id}")
        return Intent(*row)

    def update(self, intent_id: int, **fields) -> Intent:
        allowed = set(_FIELDS) - {"id", "created", "updated"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown intent fields: {sorted(unknown)}")
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        if not fields:
            return self.get(intent_id)
        self.get(intent_id)
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE intents SET {assignments}, updated = ? WHERE id = ?",
                (*fields.values(), _now(), intent_id),
            )
        return self.get(intent_id)

    def list(self, status: str | None = None) -> list[Intent]:
        query = f"SELECT {', '.join(_FIELDS)} FROM intents"
        args: tuple = ()
        if status is not None:
            query += " WHERE status = ?"
            args = (status,)
        query += " ORDER BY id"
        with self._connect() as conn:
            return [Intent(*row) for row in conn.execute(query, args)]

    def as_evidence(self) -> list[dict]:
        """Open intents as evidence items, ready for Deliberation.run()."""
        return [
            {"source": "intents", "ref": f"intent #{intent.id}", "content": intent.summary()}
            for intent in self.list(status="open")
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)
