from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.rpg.session import build_100_turn_readiness_result
from tests.rpg.manual.artifact_discovery import read_json_artifact_group
from tests.rpg.manual.certification_artifacts import emit_saved_100_turn_certification_artifacts

SOURCE = "deterministic_phase7_real_autoplay_progress_metrics_gate"
TRANSCRIPT_FILENAMES = (
    "autoplay_transcript.json",
    "manual_transcript.json",
    "turn_rows.json",
    "transcript_rows.json",
)
REPORT_FILENAMES = (
    "campaign_report.json",
    "autoplay_report.json",
    "manual_report.json",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _source_entry(kind: str, **fields: Any) -> Dict[str, Any]:
    entry = {"kind": kind, "source": SOURCE}
    entry.update(fields)
    return entry


def _rows_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [_safe_dict(row) for row in payload]
    payload_dict = _safe_dict(payload)
    for key in ("turns", "turn_rows", "transcript_rows", "rows"):
        rows = payload_dict.get(key)
        if isinstance(rows, list):
            return [_safe_dict(row) for row in rows]
    transcript = _safe_dict(payload_dict.get("transcript"))
    for key in ("turns", "turn_rows", "transcript_rows", "rows"):
        rows = transcript.get(key)
        if isinstance(rows, list):
            return [_safe_dict(row) for row in rows]
    return []


def _report_bytes(report_payload: Any, output_dir: Path) -> int:
    report = _safe_dict(report_payload)
    for key in ("report_bytes", "html_report_bytes", "bytes"):
        if key in report:
            return _safe_int(report.get(key))
    for key in ("campaign_report_html", "report_html", "html", "body"):
        if report.get(key) is not None:
            return len(str(report.get(key)).encode("utf-8"))
    for html_candidate in ("campaign_report.html", "reports/campaign_report.html", "html/campaign_report.html"):
        html_path = output_dir / html_candidate
        if html_path.is_file():
            return len(html_path.read_text(encoding="utf-8").encode("utf-8"))
    return 0


def _transcript_bytes(payload: Any, path: Path | None) -> int:
    payload_dict = _safe_dict(payload)
    for key in ("transcript_debug_bytes", "transcript_bytes", "debug_bytes", "bytes"):
        if key in payload_dict:
            return _safe_int(payload_dict.get(key))
    if path is not None and path.is_file():
        return path.stat().st_size
    return 0


def build_real_autoplay_progress_metrics_artifact(
    saved_artifacts: Dict[str, Any],
    *,
    output_dir: Path,
    expected_turns: int = 100,
) -> Dict[str, Any]:
    """Attach source-backed real saved output progress/loop metrics to certification artifacts."""

    output_dir = Path(output_dir)
    saved = dict(_safe_dict(saved_artifacts))
    transcript = read_json_artifact_group(
        output_dir=output_dir,
        group="transcript_artifact",
        names=TRANSCRIPT_FILENAMES,
        required=False,
        source=SOURCE,
    )
    report = read_json_artifact_group(
        output_dir=output_dir,
        group="report_json",
        names=REPORT_FILENAMES,
        required=False,
        source=SOURCE,
    )
    transcript_path = transcript.get("path") if isinstance(transcript.get("path"), Path) else None
    transcript_payload = transcript.get("payload")
    report_payload = report.get("payload")
    rows = _rows_from_payload(transcript_payload)
    if not rows:
        rows = _rows_from_payload(report_payload)

    blockers: List[Dict[str, Any]] = []
    metadata: List[Dict[str, Any]] = []
    metadata.extend(transcript["diagnostics"])
    metadata.extend(report["diagnostics"])
    if not rows:
        blockers.append(_source_entry("missing_real_autoplay_progress_rows", output_dir=str(output_dir)))
    else:
        saved["turns"] = rows
        metadata.append(
            _source_entry(
                "real_autoplay_progress_rows",
                path=str(transcript.get("relative_path") or report.get("relative_path")),
                rows=len(rows),
            )
        )

    report_bytes = _report_bytes(report_payload, output_dir)
    transcript_debug_bytes = _transcript_bytes(transcript_payload, transcript_path)
    if report_bytes:
        saved["report_bytes"] = report_bytes
    if transcript_debug_bytes:
        saved["transcript_debug_bytes"] = transcript_debug_bytes

    readiness = build_100_turn_readiness_result(
        rows,
        expected_turns=expected_turns,
        report_bytes=report_bytes,
        transcript_debug_bytes=transcript_debug_bytes,
    )
    saved["progress_metrics_source"] = SOURCE
    saved["progress_metrics_metadata"] = metadata
    saved["progress_metrics_readiness"] = readiness
    saved["artifact_source"] = _safe_str(saved.get("artifact_source") or SOURCE)
    return {
        "ok": not blockers,
        "reason": "phase7_real_autoplay_progress_metrics_ready"
        if not blockers
        else "phase7_real_autoplay_progress_metrics_blocked",
        "saved_artifacts": saved,
        "readiness_result": readiness,
        "metadata": metadata,
        "blockers": blockers,
        "source": SOURCE,
    }


def emit_real_autoplay_progress_metrics_certification_artifacts(
    saved_artifacts: Dict[str, Any],
    *,
    output_dir: Path,
    report_html_path: Path | None = None,
    expected_turns: int = 100,
) -> Dict[str, Any]:
    artifact = build_real_autoplay_progress_metrics_artifact(
        saved_artifacts,
        output_dir=output_dir,
        expected_turns=expected_turns,
    )
    emitted = emit_saved_100_turn_certification_artifacts(
        artifact["saved_artifacts"],
        output_dir=output_dir,
        report_html_path=report_html_path,
        expected_turns=expected_turns,
    )
    emitted = dict(emitted)
    emitted["progress_metrics_source"] = SOURCE
    emitted["progress_metrics_metadata"] = artifact["metadata"]
    emitted["progress_metrics_blockers"] = artifact["blockers"]
    emitted["progress_metrics_readiness"] = artifact["readiness_result"]
    emitted["ok"] = emitted.get("ok") is True and artifact.get("ok") is True
    if artifact.get("ok") is not True:
        emitted["reason"] = "phase7_real_autoplay_progress_metrics_emitted_with_blockers"
    return emitted


def assert_phase7_real_autoplay_progress_metrics_ready() -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    if "autoplay_transcript.json" not in TRANSCRIPT_FILENAMES:
        blockers.append(_source_entry("missing_autoplay_transcript_candidate"))
    if "campaign_report.json" not in REPORT_FILENAMES:
        blockers.append(_source_entry("missing_campaign_report_candidate"))
    return {
        "ok": not blockers,
        "reason": "phase7_real_autoplay_progress_metrics_ready"
        if not blockers
        else "phase7_real_autoplay_progress_metrics_not_ready",
        "blockers": blockers,
        "source": SOURCE,
    }
