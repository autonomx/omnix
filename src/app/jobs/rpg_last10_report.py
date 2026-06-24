"""Inline RPG last-ten-turn debug report job.

The report mirrors the feature-matrix ZIP shape at a smaller scope: a bounded
summary JSON, performance JSON, transcript JSON, HTML report, and ZIP archive
under the shared test-results/report inventory root.
"""
from __future__ import annotations

import html
import json
import math
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime_paths import test_results_root

from .models import CompleteJobRequest, FailJobRequest, JobRecord

RPG_LAST10_REPORT_JOB_TYPE = "rpg.report.last10"
RPG_LAST10_REPORT_FORMAT_VERSION = "rpg_last10_turn_debug_report_v1"
DEFAULT_TURN_LIMIT = 10
MAX_TURN_LIMIT = 100


def install_rpg_last10_report_inline_job() -> None:
    """Register the last-ten-turn report as an inline local feature job."""

    from . import inline_feature_jobs as inline_jobs

    if getattr(inline_jobs, "_omnix_rpg_last10_report_installed", False):
        return

    inline_jobs.INLINE_FEATURE_JOB_TYPES.add(RPG_LAST10_REPORT_JOB_TYPE)
    inline_jobs.BACKGROUND_INLINE_FEATURE_JOB_TYPES.add(RPG_LAST10_REPORT_JOB_TYPE)
    base_execute_feature_job = inline_jobs._execute_feature_job

    def execute_feature_job_with_last10_report(job_store: Any, job: JobRecord) -> JobRecord:
        if job.type == RPG_LAST10_REPORT_JOB_TYPE:
            return execute_rpg_last10_report_job(job_store, job)
        return base_execute_feature_job(job_store, job)

    inline_jobs._execute_feature_job = execute_feature_job_with_last10_report
    inline_jobs._omnix_rpg_last10_report_installed = True


def execute_rpg_last10_report_job(job_store: Any, job: JobRecord) -> JobRecord:
    """Execute and complete a last-ten-turn report job."""

    job_store.mark_running(job.id)
    try:
        result = render_rpg_last10_report_job(job, job_store=job_store)
    except Exception as exc:  # pragma: no cover - gateway route tests cover failure handling
        failed = job_store.fail_job(
            job.id,
            FailJobRequest(
                code="rpg_last10_report_failed",
                message=str(exc) or "RPG last-ten-turn report generation failed",
                retryable=True,
                details={"job_type": job.type, "module": job.module},
            ),
        )
        return failed or job

    completed = job_store.complete_job(
        job.id,
        CompleteJobRequest(
            output_refs=[
                {
                    "type": result["artifact_type"],
                    "module": job.module,
                    "title": result["title"],
                    "content": result["content"],
                    "zip_path": result.get("zip_path"),
                    "summary_path": result.get("summary_path"),
                    "performance_path": result.get("performance_path"),
                    "html_report_path": result.get("html_report_path"),
                }
            ],
            logs=[
                {
                    "level": "info",
                    "message": result["log_message"],
                    "content": result["content"],
                }
            ],
        ),
    )
    return completed or job


def render_rpg_last10_report_job(job: JobRecord, *, job_store: Any | None = None) -> dict[str, Any]:
    payload = build_rpg_last10_report_payload(job, job_store=job_store)
    written = write_rpg_last10_report(payload)
    summary = _dict_value(written.get("summary"))
    content = json.dumps(
        {
            "format_version": RPG_LAST10_REPORT_FORMAT_VERSION,
            "session_id": written.get("session_id"),
            "turn_count": written.get("turn_count"),
            "session_event_count": len(_list_value(written.get("session_events"))),
            "performance": written.get("performance"),
            "zip_path": summary.get("zip_path"),
            "summary_path": summary.get("summary_path"),
            "performance_path": summary.get("performance_path"),
            "html_report_path": summary.get("html_report_path"),
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return {
        "artifact_type": "rpg_last10_turn_report",
        "title": f"RPG last 10 turn debug report: {_text(written.get('session_id')) or 'session'}",
        "content": content,
        "log_message": "RPG last-ten-turn debug ZIP report generated",
        "provider_id": None,
        "model_id": None,
        "resolved_model": None,
        "zip_path": summary.get("zip_path"),
        "summary_path": summary.get("summary_path"),
        "performance_path": summary.get("performance_path"),
        "html_report_path": summary.get("html_report_path"),
    }


def build_rpg_last10_report_payload(job: JobRecord, *, job_store: Any | None = None) -> dict[str, Any]:
    input_payload = _dict_value(job.input_payload)
    session_id = _session_id_for_job(job)
    turn_limit = _turn_limit(input_payload.get("turn_limit"))
    turns = _collect_turn_jobs(job_store, session_id=session_id, limit=turn_limit)
    session_events = _collect_session_events(session_id, limit=turn_limit)
    performance = _performance_summary(turns)
    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "ok": True,
        "format_version": RPG_LAST10_REPORT_FORMAT_VERSION,
        "report_kind": "last_10_turns_debug_evaluation",
        "source": "rpg.report.last10.inline_job",
        "compatibility": {
            "style": "interactive_feature_matrix_zip_like_bundle",
            "artifacts": [
                "rpg-last10-turn-report-summary.json",
                "rpg-last10-turn-performance.json",
                "rpg-last10-turn-transcript.json",
                "rpg-last10-turn-report.html",
                "rpg-last10-turn-report.zip",
            ],
        },
        "generated_at": generated_at,
        "job_id": job.id,
        "session_id": session_id,
        "requested_turn_limit": turn_limit,
        "turn_count": len(turns),
        "turns": turns,
        "session_event_count": len(session_events),
        "session_events": session_events,
        "performance": performance,
        "diagnostics": _diagnostics(session_id, turns, session_events, performance),
    }


def write_rpg_last10_report(payload: dict[str, Any], *, output_root: Path | None = None) -> dict[str, Any]:
    payload = dict(payload)
    root = output_root or (test_results_root() / "rpg-last10-turn-report")
    session_slug = _safe_slug(_text(payload.get("session_id")) or "no-session")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / f"{timestamp}-{session_slug}"
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / "rpg-last10-turn-report-summary.json"
    performance_path = run_dir / "rpg-last10-turn-performance.json"
    transcript_path = run_dir / "rpg-last10-turn-transcript.json"
    html_path = run_dir / "rpg-last10-turn-report.html"
    zip_path = run_dir / "rpg-last10-turn-report.zip"

    summary = {
        "format_version": payload.get("format_version"),
        "report_kind": payload.get("report_kind"),
        "generated_at": payload.get("generated_at"),
        "session_id": payload.get("session_id"),
        "requested_turn_limit": payload.get("requested_turn_limit"),
        "turn_count": payload.get("turn_count"),
        "session_event_count": payload.get("session_event_count"),
        "performance": payload.get("performance"),
        "diagnostics": payload.get("diagnostics"),
        "summary_path": str(summary_path),
        "performance_path": str(performance_path),
        "transcript_path": str(transcript_path),
        "html_report_path": str(html_path),
        "zip_path": str(zip_path),
    }
    payload["summary"] = summary

    _write_json(summary_path, summary)
    _write_json(performance_path, payload.get("performance"))
    _write_json(
        transcript_path,
        {
            "format_version": payload.get("format_version"),
            "session_id": payload.get("session_id"),
            "turns": payload.get("turns"),
            "session_events": payload.get("session_events"),
        },
    )
    html_path.write_text(render_rpg_last10_report_html(payload), encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in (summary_path, performance_path, transcript_path, html_path):
            archive.write(path, arcname=path.name)
    return payload


def render_rpg_last10_report_html(payload: dict[str, Any]) -> str:
    summary = _dict_value(payload.get("summary"))
    performance = _dict_value(payload.get("performance"))
    diagnostics = _list_value(payload.get("diagnostics"))
    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head>",
            "<meta charset=\"utf-8\" />",
            "<title>RPG Last 10 Turn Debug Report</title>",
            "<style>body{font-family:system-ui,sans-serif;line-height:1.45;margin:2rem;max-width:1200px}table{border-collapse:collapse;width:100%;margin:1rem 0}td,th{border:1px solid #ccc;padding:.45rem;text-align:left;vertical-align:top}code,pre{background:#f4f4f4;padding:.2rem .35rem}pre{overflow:auto;padding:1rem}.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.75rem}.metric{border:1px solid #ddd;border-radius:8px;padding:.75rem}</style>",
            "</head>",
            "<body>",
            "<h1>RPG Last 10 Turn Debug Report</h1>",
            f"<p><strong>Session:</strong> {_escape(payload.get('session_id')) or 'No session'} · <strong>Generated:</strong> {_escape(payload.get('generated_at'))}</p>",
            "<h2>Performance metrics</h2>",
            _performance_html(performance),
            "<h2>Last turn jobs</h2>",
            _turns_html(_list_value(payload.get("turns"))),
            "<h2>Session event fallback</h2>",
            _events_html(_list_value(payload.get("session_events"))),
            "<h2>Diagnostics</h2>",
            _diagnostics_html(diagnostics),
            "<h2>Artifact paths</h2>",
            f"<pre>{_escape(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str))}</pre>",
            "</body>",
            "</html>",
        ]
    )


def _collect_turn_jobs(job_store: Any | None, *, session_id: str | None, limit: int) -> list[dict[str, Any]]:
    if job_store is None or not hasattr(job_store, "list_jobs"):
        return []
    try:
        jobs = list(job_store.list_jobs())
    except Exception:
        return []
    candidates: list[JobRecord] = []
    for candidate in jobs:
        if not isinstance(candidate, JobRecord) or candidate.type != "rpg.turn":
            continue
        if str(candidate.status) != "completed" and getattr(candidate.status, "value", None) != "completed":
            continue
        if session_id and _session_id_for_job(candidate) != session_id:
            continue
        candidates.append(candidate)
    candidates.sort(key=_job_sort_time)
    selected = candidates[-limit:]
    return [_turn_job_row(candidate, index + 1) for index, candidate in enumerate(selected)]


def _turn_job_row(job: JobRecord, sequence: int) -> dict[str, Any]:
    duration_seconds = _job_duration_seconds(job)
    return {
        "sequence": sequence,
        "job_id": job.id,
        "status": str(getattr(job.status, "value", job.status)),
        "session_id": _session_id_for_job(job),
        "command": _job_command(job),
        "response": _job_response(job),
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "updated_at": job.updated_at,
        "duration_seconds": duration_seconds,
        "stages": [stage.model_dump(mode="json") for stage in job.stages],
    }


def _collect_session_events(session_id: str | None, *, limit: int) -> list[dict[str, Any]]:
    if not session_id:
        return []
    try:
        from app.rpg.session.service import load_session  # type: ignore[import-untyped]

        session = load_session(session_id)
    except Exception:
        return []
    if not isinstance(session, dict):
        return []
    roots = [
        session,
        _dict_value(session.get("simulation_state")),
        _dict_value(session.get("metadata")),
        _dict_value(session.get("state")),
        _dict_value(session.get("payload")),
        _dict_value(session.get("runtime_state")),
    ]
    candidates: list[Any] = []
    for root in [item for item in roots if item]:
        journal = _dict_value(root.get("journal"))
        for key in (
            "timeline",
            "recent_events",
            "events",
            "event_log",
            "turn_history",
            "turns",
            "history",
            "dialogue_log",
            "dialogue",
            "logs",
        ):
            candidates.extend(_list_value(root.get(key)))
        candidates.extend(_list_value(journal.get("entries")))
    events = [_session_event_row(item, index + 1) for index, item in enumerate(candidates)]
    return [event for event in events if event][-limit:]


def _session_event_row(item: Any, sequence: int) -> dict[str, Any] | None:
    if isinstance(item, str) and item.strip():
        return {"sequence": sequence, "title": f"Session event {sequence}", "detail": item.strip()}
    record = _dict_value(item)
    if not record:
        return None
    return {
        "sequence": sequence,
        "turn": _number(record.get("turn") or record.get("turn_count") or record.get("index")),
        "time": _text(record.get("time") or record.get("timestamp") or record.get("created_at") or record.get("updated_at") or record.get("turn_label")),
        "title": _text(record.get("title") or record.get("label") or record.get("event") or record.get("kind") or record.get("type")) or f"Session event {sequence}",
        "command": _text(record.get("command") or record.get("action") or record.get("player_action") or record.get("input")),
        "detail": _text(record.get("narration") or record.get("response") or record.get("output") or record.get("summary") or record.get("result") or record.get("text") or record.get("message") or record.get("description")),
    }


def _performance_summary(turns: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [float(row["duration_seconds"]) for row in turns if isinstance(row.get("duration_seconds"), (int, float))]
    return {
        "metrics_included": True,
        "metrics_source": "gateway_job_created_started_completed_timestamps",
        "turn_count": len(turns),
        "measured_turn_count": len(durations),
        "total_turn_seconds": _round(sum(durations)) if durations else None,
        "avg_turn_seconds": _round(sum(durations) / len(durations)) if durations else None,
        "p95_turn_seconds": _round(_percentile(durations, 0.95)) if durations else None,
        "min_turn_seconds": _round(min(durations)) if durations else None,
        "max_turn_seconds": _round(max(durations)) if durations else None,
        "per_turn_seconds": durations,
    }


def _diagnostics(session_id: str | None, turns: list[dict[str, Any]], session_events: list[dict[str, Any]], performance: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    if not session_id:
        diagnostics.append({"kind": "missing_session_id", "severity": "warning", "message": "No live RPG session id was attached to the report request."})
    if not turns:
        diagnostics.append({"kind": "missing_completed_turn_jobs", "severity": "warning", "message": "No completed rpg.turn jobs were found for the selected session; session events are included as fallback evidence."})
    if not session_events:
        diagnostics.append({"kind": "missing_session_events", "severity": "info", "message": "No session timeline/events were available as fallback evidence."})
    if not performance.get("measured_turn_count"):
        diagnostics.append({"kind": "missing_duration_metrics", "severity": "warning", "message": "Turn duration metrics could not be derived from job timestamps."})
    return diagnostics


def _session_id_for_job(job: JobRecord) -> str | None:
    input_ref = _dict_value(job.input_ref)
    return _text(input_ref.get("session_id"))


def _turn_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_TURN_LIMIT
    return max(1, min(MAX_TURN_LIMIT, parsed))


def _job_command(job: JobRecord) -> str:
    payload = _dict_value(job.input_payload)
    return _text(payload.get("command") or payload.get("player_input") or payload.get("content")) or ""


def _job_response(job: JobRecord) -> str:
    for ref in _list_value(job.output_refs):
        record = _dict_value(ref)
        if _text(record.get("type")) == "rpg_turn_response":
            text = _text(record.get("content") or record.get("text"))
            if text:
                return text
    for ref in _list_value(job.output_refs):
        record = _dict_value(ref)
        text = _text(record.get("content") or record.get("text"))
        if text:
            return text
    for log in _list_value(job.logs):
        record = _dict_value(log)
        text = _text(record.get("content") or record.get("message"))
        if text:
            return text
    return ""


def _job_sort_time(job: JobRecord) -> float:
    return _timestamp(job.completed_at or job.updated_at or job.created_at)


def _job_duration_seconds(job: JobRecord) -> float | None:
    completed = _timestamp(job.completed_at or job.updated_at)
    started = _timestamp(job.started_at or job.created_at)
    if completed <= 0 or started <= 0 or completed < started:
        return None
    return _round(completed - started)


def _timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percentile) - 1))
    return ordered[index]


def _round(value: float) -> float:
    return round(float(value), 3)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _performance_html(performance: dict[str, Any]) -> str:
    keys = [
        "turn_count",
        "measured_turn_count",
        "total_turn_seconds",
        "avg_turn_seconds",
        "p95_turn_seconds",
        "min_turn_seconds",
        "max_turn_seconds",
    ]
    cards = [f"<div class=\"metric\"><strong>{_escape(key)}</strong><br />{_escape(performance.get(key))}</div>" for key in keys]
    return f"<div class=\"metric-grid\">{''.join(cards)}</div>"


def _turns_html(turns: list[Any]) -> str:
    if not turns:
        return "<p>No completed turn jobs were found for this session.</p>"
    rows = []
    for raw in turns:
        row = _dict_value(raw)
        rows.append(
            "<tr>"
            f"<td>{_escape(row.get('sequence'))}</td>"
            f"<td>{_escape(row.get('command'))}</td>"
            f"<td>{_escape(row.get('response'))}</td>"
            f"<td>{_escape(row.get('duration_seconds'))}</td>"
            f"<td>{_escape(row.get('job_id'))}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>#</th><th>Command</th><th>Response</th><th>Seconds</th><th>Job</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _events_html(events: list[Any]) -> str:
    if not events:
        return "<p>No session event fallback rows were found.</p>"
    rows = []
    for raw in events:
        row = _dict_value(raw)
        rows.append(
            "<tr>"
            f"<td>{_escape(row.get('sequence'))}</td>"
            f"<td>{_escape(row.get('title'))}</td>"
            f"<td>{_escape(row.get('command'))}</td>"
            f"<td>{_escape(row.get('detail'))}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>#</th><th>Title</th><th>Command</th><th>Detail</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _diagnostics_html(diagnostics: list[Any]) -> str:
    if not diagnostics:
        return "<p>No diagnostics were emitted.</p>"
    items = []
    for raw in diagnostics:
        row = _dict_value(raw)
        items.append(f"<li><strong>{_escape(row.get('kind'))}</strong>: {_escape(row.get('message'))}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug[:80] or "session"


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _number(value: Any) -> int | float | None:
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None
    return None
