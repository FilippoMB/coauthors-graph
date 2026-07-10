from __future__ import annotations

from datetime import datetime, timezone
import json

from automation.update_heartbeat import update_heartbeat


def test_update_heartbeat_writes_utc_timestamp(tmp_path) -> None:
    output = tmp_path / "heartbeat.json"

    update_heartbeat(
        output,
        datetime(2026, 7, 13, 6, 17, tzinfo=timezone.utc),
    )

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "last_scheduled_run": "2026-07-13T06:17:00Z"
    }
