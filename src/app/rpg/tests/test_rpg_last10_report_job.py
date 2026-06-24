from __future__ import annotations

import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.jobs.models import JobRecord
from app.jobs.rpg_last10_report import (
    RPG_LAST10_REPORT_JOB_TYPE,
    build_rpg_last10_report_payload,
    write_rpg_last10_report,
)


class FakeJobStore:
    def __init__(self, jobs: list[JobRecord]) -> None:
        self._jobs = jobs

    def list_jobs(self) -> list[JobRecord]:
        return list(self._jobs)


def _iso(offset_seconds: int) -> str:
    base = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def _job_record(
    *,
    job_id: str,
    job_type: str,
    session_id: str,
    created_offset: int,
    duration: int,
    command: str | None = None,
    response: str | None = None,
    input_payload: dict[str, Any] | None = None,
) -> JobRecord:
    created_at = _iso(created_offset)
    started_at = _iso(created_offset + 1)
    completed_at = _iso(created_offset + duration + 1)
    return JobRecord(
        id=job_id,
        module="rpg",
        type=job_type,
        status="completed",
        resource_class="cpu",
        priority=0,
        stages=[],
        progress={"current": 1, "total": 1, "message": "completed"},
        logs=[],
        input_ref={"session_id": session_id},
        input_payload=input_payload if input_payload is not None else {"command": command or ""},
        output_refs=[{"type": "rpg_turn_response", "content": response or ""}] if response is not None else [],
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        updated_at=completed_at,
        cancel={"requested": False},
        compat={},
    )


def test_last10_report_payload_uses_completed_turn_jobs_and_performance_metrics(tmp_path: Path) -> None:
    turn_jobs = [
        _job_record(
            job_id=f"job:turn-{index:02d}",
            job_type="rpg.turn",
            session_id="session-live-1",
            created_offset=index * 10,
            duration=index,
            command=f"command {index}",
            response=f"response {index}",
        )
        for index in range(1, 13)
    ]
    report_job = _job_record(
        job_id="job:report",
        job_type=RPG_LAST10_REPORT_JOB_TYPE,
        session_id="session-live-1",
        created_offset=999,
        duration=1,
        input_payload={"turn_limit": 10},
    )

    payload = build_rpg_last10_report_payload(report_job, job_store=FakeJobStore(turn_jobs))

    assert payload["format_version"] == "rpg_last10_turn_debug_report_v1"
    assert payload["session_id"] == "session-live-1"
    assert payload["turn_count"] == 10
    assert [row["command"] for row in payload["turns"]][0] == "command 3"
    assert [row["command"] for row in payload["turns"]][-1] == "command 12"
    assert payload["performance"]["metrics_included"] is True
    assert payload["performance"]["measured_turn_count"] == 10
    assert payload["performance"]["avg_turn_seconds"] == 7.5
    assert payload["performance"]["p95_turn_seconds"] == 12

    written = write_rpg_last10_report(payload, output_root=tmp_path)
    summary = written["summary"]
    zip_path = Path(summary["zip_path"])
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as archive:
        assert set(archive.namelist()) == {
            "rpg-last10-turn-report-summary.json",
            "rpg-last10-turn-performance.json",
            "rpg-last10-turn-transcript.json",
            "rpg-last10-turn-report.html",
        }
