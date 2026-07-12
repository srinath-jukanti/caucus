"""Import a reference-deployment campaigns.db into a Caucus intent store.

Usage: uv run python import_campaigns.py /path/to/campaigns.db [intents.db]
"""

import sqlite3
import sys

from caucus.intents import IntentStore

STATUS_MAP = {"open": "open", "paused": "paused", "done": "done"}


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    source = sys.argv[1]
    destination = sys.argv[2] if len(sys.argv) > 2 else "intents.db"

    store = IntentStore(destination)
    rows = sqlite3.connect(source).execute(
        "SELECT ticker, direction, target_pct, pacing, cadence_days,"
        " last_filled, status, notes FROM campaigns"
    )
    count = 0
    for ticker, direction, target, pacing, cadence_days, last_filled, status, notes in rows:
        store.add(
            name=f"{ticker} {direction}",
            direction=direction or "",
            target=f"{target}%" if target is not None else "",
            pacing=pacing or "",
            cadence_days=cadence_days,
            last_acted=last_filled,
            status=STATUS_MAP.get(status, "paused"),
            notes=(notes or "")[:500],
        )
        count += 1
    print(f"imported {count} campaigns into {destination}")


if __name__ == "__main__":
    main()
