from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.jobs.inline_feature_jobs import _execute_feature_job
from app.jobs.models import JobRecord
from app.jobs.rpg_last10_report import RPG_LAST10_REPORT_JOB_TYPE, build_rpg_last10_report_payload, write_rpg_last10_report


class FakeJobStore:
    def __init__(self, jobs: list[JobRecord]) -> None:
        self._jobs = jobs

    def list_jobs(self) -> list[JobRecord]:
        return list(self._jobs)


class FakeExecutableJobStore(FakeJobStore):
    def __init__(self, jobs: list[JobRecord]) -> None:
        super().__init__(jobs)
        self.running_job_ids: list[str] = []
        self.completed_requests: list[tuple[str, Any]] = []
        self.failed_requests: list[tuple[str, Any]] = []

    def mark_running(self, job_id: str) -> None:
        self.running_job_ids.append(job_id)

    def complete_job(self, job_id: str, request: Any) -> JobRecord:
        self.completed_requests.append((job_id, request))
        return _job(job_id=job_id, kind=RPG_LAST10_REPORT_JOB_TYPE, session="session-live-1", offset=999, duration=1)

    def fail_job(self, job_id: str, request: Any) -> JobRecord:
        self.failed_requests.append((job_id, request))
        return _job(job_id=job_id, kind=RPG_LAST10_REPORT_JOB_TYPE, session="session-live-1", offset=999, duration=1)


def _iso(offset: int) -> str:
    return (datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=offset)).isoformat()


def _job(
    *,
    job_id: str,
    kind: str,
    session: str,
    offset: int,
    duration: int,
    command: str = "",
    response: str = "",
    output_refs: list[dict[str, Any]] | None = None,
    stages: list[dict[str, Any]] | None = None,
) -> JobRecord:
    refs = output_refs if output_refs is not None else ([{"type": "rpg_turn_response", "content": response}] if response else [])
    return JobRecord(
        id=job_id,
        module="rpg",
        type=kind,
        status="completed",
        resource_class="cpu",
        priority=0,
        stages=stages or [],
        progress={"current": 1, "total": 1, "message": "completed"},
        logs=[],
        input_ref={"session_id": session},
        input_payload={"command": command, "turn_limit": 10},
        output_refs=refs,
        created_at=_iso(offset),
        started_at=_iso(offset + 1),
        completed_at=_iso(offset + duration + 1),
        updated_at=_iso(offset + duration + 1),
        cancel={"requested": False},
        compat={},
    )


def test_last10_report_payload_metrics_and_zip(tmp_path: Path) -> None:
    jobs = [_job(job_id=f"job:turn-{i:02d}", kind="rpg.turn", session="session-live-1", offset=i * 10, duration=i, command=f"command {i}", response=f"response {i}") for i in range(1, 13)]
    report = _job(job_id="job:report", kind=RPG_LAST10_REPORT_JOB_TYPE, session="session-live-1", offset=999, duration=1)
    payload = build_rpg_last10_report_payload(report, job_store=FakeJobStore(jobs))

    assert payload["format_version"] == "rpg_last10_turn_debug_report_v2"
    assert payload["turn_count"] == 10
    assert payload["turns"][0]["command"] == "command 3"
    assert payload["performance"]["avg_turn_seconds"] == 7.5
    assert payload["performance"]["p95_turn_seconds"] == 12

    written = write_rpg_last10_report(payload, output_root=tmp_path)
    with zipfile.ZipFile(Path(written["summary"]["zip_path"])) as archive:
        assert "rpg-last10-turn-transcript.json" in set(archive.namelist())


def test_last10_report_includes_handoff_debug_payload(tmp_path: Path) -> None:
    raw = {
        "narration_source": "deterministic_fallback",
        "fallback_reason": "missing_dialogue_candidate",
        "interactive_cli_intent_diagnostics": {"provider_status": "valid_json", "provider_called": True, "intent_llm_used": True, "provider_total_ms": 2900},
        "dialogue_payload": {"mode": "direct_npc_question", "target_npc": "Example NPC", "npc_response_candidate": None},
        "response_selection_trace": {"selected_response_source": "deterministic_fallback", "fallback_reason": "missing_dialogue_candidate"},
    }
    turn = _job(
        job_id="job:turn-debug",
        kind="rpg.turn",
        session="session-live-1",
        offset=10,
        duration=6,
        command="ask example npc a question",
        output_refs=[{"type": "rpg_turn_response", "content": "fallback line"}, {"type": "rpg_turn_result", "content": json.dumps(raw)}],
        stages=[
            {"id": "load-session", "label": "Load", "status": "completed", "resource_class": "cpu", "started_at": _iso(11), "completed_at": _iso(12)},
            {"id": "apply-turn", "label": "Apply", "status": "completed", "resource_class": "cpu", "started_at": _iso(12), "completed_at": _iso(16)},
        ],
    )
    report = _job(job_id="job:report", kind=RPG_LAST10_REPORT_JOB_TYPE, session="session-live-1", offset=999, duration=1)
    payload = build_rpg_last10_report_payload(report, job_store=FakeJobStore([turn]))
    row = payload["turns"][0]

    assert row["raw_intent_diagnostics"]["provider_status"] == "valid_json"
    assert row["dialogue_payload"]["dialogue_payload"]["target_npc"] == "Example NPC"
    assert row["response_selection_trace"]["fallback_reason"] == "missing_dialogue_candidate"
    assert row["performance_trace"]["provider_metrics"]["provider_total_ms"] == 2900
    assert payload["performance"]["stage_seconds_totals"] == {"apply-turn": 4.0, "load-session": 1.0}

    written = write_rpg_last10_report(payload, output_root=tmp_path)
    transcript = Path(written["summary"]["transcript_path"]).read_text(encoding="utf-8")
    html = Path(written["summary"]["html_report_path"]).read_text(encoding="utf-8")
    assert "raw_intent_diagnostics" in transcript
    assert "response_selection_trace" in transcript
    assert "Turn debug payloads" in html


def test_last10_report_is_supported_by_inline_feature_dispatcher(tmp_path: Path, monkeypatch: Any) -> None:
    turn = _job(job_id="job:turn-01", kind="rpg.turn", session="session-live-1", offset=10, duration=3, command="Ask NPC", response="NPC answers")
    report = _job(job_id="job:report", kind=RPG_LAST10_REPORT_JOB_TYPE, session="session-live-1", offset=999, duration=1)
    store = FakeExecutableJobStore([turn])
    monkeypatch.setattr("app.jobs.rpg_last10_report.write_rpg_last10_report", lambda payload: write_rpg_last10_report(payload, output_root=tmp_path))

    _execute_feature_job(store, report)

    assert store.running_job_ids == ["job:report"]
    assert store.failed_requests == []
    assert store.completed_requests[0][1].output_refs[0]["type"] == "rpg_last10_turn_report"
