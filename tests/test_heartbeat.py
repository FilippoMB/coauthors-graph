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


def test_same_or_older_workflow_run_does_not_change_heartbeat(tmp_path):
    output = tmp_path / "heartbeat.json"
    update_heartbeat(output, datetime(2026, 9, 7, tzinfo=timezone.utc), run_id="1234")
    original = output.read_bytes()
    update_heartbeat(output, datetime(2026, 9, 8, tzinfo=timezone.utc), run_id="1234")
    assert output.read_bytes() == original
    update_heartbeat(output, datetime(2026, 9, 9, tzinfo=timezone.utc), run_id="1233")
    assert output.read_bytes() == original
    update_heartbeat(output, datetime(2026, 9, 14, tzinfo=timezone.utc), run_id="1235")
    assert json.loads(output.read_text())["workflow_run_id"] == "1235"
