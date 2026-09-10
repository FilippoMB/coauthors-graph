"""Update the scheduled-workflow heartbeat using only the Python standard library."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path


def update_heartbeat(
    path: str | Path, timestamp: datetime | None = None, *, run_id: str | None = None
) -> Path:
    destination = Path(path)
    if run_id is not None:
        if not run_id.isdigit():
            raise ValueError("Workflow run ID must be numeric")
        if destination.exists():
            previous = json.loads(destination.read_text(encoding="utf-8"))
            previous_id = previous.get("workflow_run_id")
            if previous_id and int(previous_id) >= int(run_id):
                return destination
    current = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = {
        "last_scheduled_run": current.isoformat().replace("+00:00", "Z"),
    }
    if run_id is not None:
        payload["workflow_run_id"] = run_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a scheduled workflow heartbeat."
    )
    parser.add_argument("path", help="Heartbeat JSON file to update")
    args = parser.parse_args()
    destination = update_heartbeat(args.path, run_id=os.environ.get("GITHUB_RUN_ID"))
    print(f"Updated workflow heartbeat at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
