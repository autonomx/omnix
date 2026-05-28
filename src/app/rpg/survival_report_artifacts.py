"""Bundle BH/BW/BX/BY/BZ — survival metrics artifact writer helpers.

BG introduced aggregation and HTML rendering primitives.  BH turns those
primitives into concrete artifact files that autoplay/report pipelines can write
or bundle into ZIP outputs without duplicating survival logic.  BW adds compact
summary artifacts beside the detailed metrics files.  BX attaches compact
long-run readiness projection for 100/1000-turn reporting without requiring huge
transcripts.  BY writes readiness JSON/HTML as first-class artifacts.  BZ adds a
navigation index so report ZIPs have one obvious survival entry point.
"""
from __future__ import annotations

import json
import zipfile
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from app.rpg.survival_readiness import (
    build_survival_readiness_projection,
    render_survival_readiness_html,
)
from app.rpg.survival_report_metrics import (
    build_survival_report_metrics,
    render_survival_report_html,
)
from app.rpg.survival_report_polish import (
    build_compact_survival_summary,
    render_compact_survival_summary_html,
)

SURVIVAL_ARTIFACT_SOURCE = "runtime_survival_report_artifacts"
SURVIVAL_METRICS_JSON_NAME = "survival-report-metrics.json"
SURVIVAL_METRICS_HTML_NAME = "survival-report-metrics.html"
SURVIVAL_SUMMARY_JSON_NAME = "survival-summary.json"
SURVIVAL_SUMMARY_HTML_NAME = "survival-summary.html"
SURVIVAL_READINESS_JSON_NAME = "survival-readiness.json"
SURVIVAL_READINESS_HTML_NAME = "survival-readiness.html"
SURVIVAL_INDEX_HTML_NAME = "survival-index.html"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def render_survival_artifact_index_html(
    *,
    metrics: Mapping[str, Any],
    compact_summary: Mapping[str, Any],
    survival_readiness: Mapping[str, Any],
    metrics_html_name: str = SURVIVAL_METRICS_HTML_NAME,
    summary_html_name: str = SURVIVAL_SUMMARY_HTML_NAME,
    readiness_html_name: str = SURVIVAL_READINESS_HTML_NAME,
    metrics_json_name: str = SURVIVAL_METRICS_JSON_NAME,
    summary_json_name: str = SURVIVAL_SUMMARY_JSON_NAME,
    readiness_json_name: str = SURVIVAL_READINESS_JSON_NAME,
) -> str:
    metrics = _safe_dict(metrics)
    compact_summary = _safe_dict(compact_summary)
    survival_readiness = _safe_dict(survival_readiness)
    summary = _safe_dict(metrics.get("summary"))
    readiness_status = _safe_str(survival_readiness.get("status") or "unknown")
    summary_status = _safe_str(compact_summary.get("status") or "unknown")
    failed = survival_readiness.get("failed_advisory_gates") or []
    warnings = survival_readiness.get("warnings") or []
    failed_html = "".join(f"<li>{escape(_safe_str(item))}</li>" for item in failed) or "<li>none</li>"
    warnings_html = "".join(f"<li>{escape(_safe_str(item))}</li>" for item in warnings) or "<li>none</li>"
    return "\n".join([
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Survival Report Index</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:24px;line-height:1.45} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.card{border:1px solid #ddd;border-radius:12px;padding:14px}.status{font-weight:800;text-transform:uppercase}.links a{display:block;margin:4px 0}</style>",
        "</head><body>",
        "<h1>Survival Report Index</h1>",
        "<div class='grid'>",
        f"<div class='card'><strong>Readiness</strong><p class='status'>{escape(readiness_status)}</p><p>advisory only: {str(bool(survival_readiness.get('advisory_only'))).lower()}</p></div>",
        f"<div class='card'><strong>Summary</strong><p class='status'>{escape(summary_status)}</p><p>turns observed: {_safe_int(summary.get('turns_observed'))}</p></div>",
        f"<div class='card'><strong>Actions</strong><p>direct: {_safe_int(summary.get('direct_survival_action_count'))}</p><p>blocked: {_safe_int(summary.get('blocked_survival_action_count'))}</p></div>",
        f"<div class='card'><strong>Ticks</strong><p>passive: {_safe_int(summary.get('passive_tick_count'))}</p></div>",
        "</div>",
        "<h2>Open Reports</h2>",
        "<div class='links'>",
        f"<a href='{escape(summary_html_name)}'>Compact Survival Summary</a>",
        f"<a href='{escape(readiness_html_name)}'>Survival Readiness</a>",
        f"<a href='{escape(metrics_html_name)}'>Detailed Survival Metrics</a>",
        "</div>",
        "<h2>JSON Artifacts</h2>",
        "<div class='links'>",
        f"<a href='{escape(summary_json_name)}'>{escape(summary_json_name)}</a>",
        f"<a href='{escape(readiness_json_name)}'>{escape(readiness_json_name)}</a>",
        f"<a href='{escape(metrics_json_name)}'>{escape(metrics_json_name)}</a>",
        "</div>",
        "<h2>Warnings</h2>",
        f"<ul>{warnings_html}</ul>",
        "<h2>Failed Advisory Gates</h2>",
        f"<ul>{failed_html}</ul>",
        "</body></html>",
    ])


def survival_metrics_artifact_payload(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    metrics = build_survival_report_metrics(rows)
    compact_summary = build_compact_survival_summary(metrics)
    survival_readiness = build_survival_readiness_projection(metrics, compact_summary)
    html = render_survival_report_html(metrics)
    summary_html = render_compact_survival_summary_html(metrics)
    readiness_html = render_survival_readiness_html(survival_readiness)
    index_html = render_survival_artifact_index_html(
        metrics=metrics,
        compact_summary=compact_summary,
        survival_readiness=survival_readiness,
    )
    return {
        "metrics": metrics,
        "compact_summary": compact_summary,
        "survival_readiness": survival_readiness,
        "json_filename": SURVIVAL_METRICS_JSON_NAME,
        "html_filename": SURVIVAL_METRICS_HTML_NAME,
        "summary_json_filename": SURVIVAL_SUMMARY_JSON_NAME,
        "summary_html_filename": SURVIVAL_SUMMARY_HTML_NAME,
        "readiness_json_filename": SURVIVAL_READINESS_JSON_NAME,
        "readiness_html_filename": SURVIVAL_READINESS_HTML_NAME,
        "index_html_filename": SURVIVAL_INDEX_HTML_NAME,
        "json_text": _json_dumps(metrics),
        "html_text": html,
        "summary_json_text": _json_dumps(compact_summary),
        "summary_html_text": summary_html,
        "readiness_json_text": _json_dumps(survival_readiness),
        "readiness_html_text": readiness_html,
        "index_html_text": index_html,
        "source": SURVIVAL_ARTIFACT_SOURCE,
    }


def write_survival_report_artifacts(
    output_dir: str | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    json_name: str = SURVIVAL_METRICS_JSON_NAME,
    html_name: str = SURVIVAL_METRICS_HTML_NAME,
    summary_json_name: str = SURVIVAL_SUMMARY_JSON_NAME,
    summary_html_name: str = SURVIVAL_SUMMARY_HTML_NAME,
    readiness_json_name: str = SURVIVAL_READINESS_JSON_NAME,
    readiness_html_name: str = SURVIVAL_READINESS_HTML_NAME,
    index_html_name: str = SURVIVAL_INDEX_HTML_NAME,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    payload = survival_metrics_artifact_payload(rows)
    json_path = _write_text(output_dir / json_name, _safe_str(payload.get("json_text")))
    html_path = _write_text(output_dir / html_name, _safe_str(payload.get("html_text")))
    summary_json_path = _write_text(output_dir / summary_json_name, _safe_str(payload.get("summary_json_text")))
    summary_html_path = _write_text(output_dir / summary_html_name, _safe_str(payload.get("summary_html_text")))
    readiness_json_path = _write_text(output_dir / readiness_json_name, _safe_str(payload.get("readiness_json_text")))
    readiness_html_path = _write_text(output_dir / readiness_html_name, _safe_str(payload.get("readiness_html_text")))
    index_html_path = _write_text(output_dir / index_html_name, _safe_str(payload.get("index_html_text")))
    return {
        "ok": True,
        "metrics": _safe_dict(payload.get("metrics")),
        "compact_summary": _safe_dict(payload.get("compact_summary")),
        "survival_readiness": _safe_dict(payload.get("survival_readiness")),
        "json_path": str(json_path),
        "html_path": str(html_path),
        "summary_json_path": str(summary_json_path),
        "summary_html_path": str(summary_html_path),
        "readiness_json_path": str(readiness_json_path),
        "readiness_html_path": str(readiness_html_path),
        "index_html_path": str(index_html_path),
        "json_filename": json_name,
        "html_filename": html_name,
        "summary_json_filename": summary_json_name,
        "summary_html_filename": summary_html_name,
        "readiness_json_filename": readiness_json_name,
        "readiness_html_filename": readiness_html_name,
        "index_html_filename": index_html_name,
        "source": SURVIVAL_ARTIFACT_SOURCE,
    }


def append_survival_report_artifacts_to_zip(
    zip_path: str | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    prefix: str = "",
    json_name: str = SURVIVAL_METRICS_JSON_NAME,
    html_name: str = SURVIVAL_METRICS_HTML_NAME,
    summary_json_name: str = SURVIVAL_SUMMARY_JSON_NAME,
    summary_html_name: str = SURVIVAL_SUMMARY_HTML_NAME,
    readiness_json_name: str = SURVIVAL_READINESS_JSON_NAME,
    readiness_html_name: str = SURVIVAL_READINESS_HTML_NAME,
    index_html_name: str = SURVIVAL_INDEX_HTML_NAME,
) -> Dict[str, Any]:
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    payload = survival_metrics_artifact_payload(rows)
    normalized_prefix = _safe_str(prefix).strip().strip("/")
    json_arcname = f"{normalized_prefix}/{json_name}" if normalized_prefix else json_name
    html_arcname = f"{normalized_prefix}/{html_name}" if normalized_prefix else html_name
    summary_json_arcname = f"{normalized_prefix}/{summary_json_name}" if normalized_prefix else summary_json_name
    summary_html_arcname = f"{normalized_prefix}/{summary_html_name}" if normalized_prefix else summary_html_name
    readiness_json_arcname = f"{normalized_prefix}/{readiness_json_name}" if normalized_prefix else readiness_json_name
    readiness_html_arcname = f"{normalized_prefix}/{readiness_html_name}" if normalized_prefix else readiness_html_name
    index_html_arcname = f"{normalized_prefix}/{index_html_name}" if normalized_prefix else index_html_name
    mode = "a" if zip_path.exists() else "w"
    with zipfile.ZipFile(zip_path, mode, compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(json_arcname, _safe_str(payload.get("json_text")))
        zf.writestr(html_arcname, _safe_str(payload.get("html_text")))
        zf.writestr(summary_json_arcname, _safe_str(payload.get("summary_json_text")))
        zf.writestr(summary_html_arcname, _safe_str(payload.get("summary_html_text")))
        zf.writestr(readiness_json_arcname, _safe_str(payload.get("readiness_json_text")))
        zf.writestr(readiness_html_arcname, _safe_str(payload.get("readiness_html_text")))
        zf.writestr(index_html_arcname, _safe_str(payload.get("index_html_text")))
    return {
        "ok": True,
        "metrics": _safe_dict(payload.get("metrics")),
        "compact_summary": _safe_dict(payload.get("compact_summary")),
        "survival_readiness": _safe_dict(payload.get("survival_readiness")),
        "zip_path": str(zip_path),
        "zip_members": [
            index_html_arcname,
            json_arcname,
            html_arcname,
            summary_json_arcname,
            summary_html_arcname,
            readiness_json_arcname,
            readiness_html_arcname,
        ],
        "source": SURVIVAL_ARTIFACT_SOURCE,
    }


def attach_survival_artifact_manifest(report_manifest: Optional[Mapping[str, Any]], artifact_result: Mapping[str, Any]) -> Dict[str, Any]:
    manifest = dict(_safe_dict(report_manifest))
    artifacts = list(manifest.get("artifacts") or [])
    artifact_result = _safe_dict(artifact_result)
    if artifact_result.get("index_html_path"):
        artifacts.append({
            "kind": "survival_index_html",
            "path": _safe_str(artifact_result.get("index_html_path")),
            "source": SURVIVAL_ARTIFACT_SOURCE,
        })
    if artifact_result.get("json_path"):
        artifacts.append({
            "kind": "survival_metrics_json",
            "path": _safe_str(artifact_result.get("json_path")),
            "source": SURVIVAL_ARTIFACT_SOURCE,
        })
    if artifact_result.get("html_path"):
        artifacts.append({
            "kind": "survival_metrics_html",
            "path": _safe_str(artifact_result.get("html_path")),
            "source": SURVIVAL_ARTIFACT_SOURCE,
        })
    if artifact_result.get("summary_json_path"):
        artifacts.append({
            "kind": "survival_summary_json",
            "path": _safe_str(artifact_result.get("summary_json_path")),
            "source": SURVIVAL_ARTIFACT_SOURCE,
        })
    if artifact_result.get("summary_html_path"):
        artifacts.append({
            "kind": "survival_summary_html",
            "path": _safe_str(artifact_result.get("summary_html_path")),
            "source": SURVIVAL_ARTIFACT_SOURCE,
        })
    if artifact_result.get("readiness_json_path"):
        artifacts.append({
            "kind": "survival_readiness_json",
            "path": _safe_str(artifact_result.get("readiness_json_path")),
            "source": SURVIVAL_ARTIFACT_SOURCE,
        })
    if artifact_result.get("readiness_html_path"):
        artifacts.append({
            "kind": "survival_readiness_html",
            "path": _safe_str(artifact_result.get("readiness_html_path")),
            "source": SURVIVAL_ARTIFACT_SOURCE,
        })
    for member in artifact_result.get("zip_members") or []:
        kind = "survival_metrics_zip_member"
        if "index" in _safe_str(member):
            kind = "survival_index_zip_member"
        elif "summary" in _safe_str(member):
            kind = "survival_summary_zip_member"
        elif "readiness" in _safe_str(member):
            kind = "survival_readiness_zip_member"
        artifacts.append({
            "kind": kind,
            "path": _safe_str(member),
            "zip_path": _safe_str(artifact_result.get("zip_path")),
            "source": SURVIVAL_ARTIFACT_SOURCE,
        })
    manifest["artifacts"] = artifacts
    manifest["survival_report_metrics"] = _safe_dict(artifact_result.get("metrics"))
    if artifact_result.get("compact_summary"):
        manifest["survival_summary"] = _safe_dict(artifact_result.get("compact_summary"))
    if artifact_result.get("survival_readiness"):
        manifest["survival_readiness"] = _safe_dict(artifact_result.get("survival_readiness"))
    if artifact_result.get("index_html_path"):
        manifest["survival_index_html"] = _safe_str(artifact_result.get("index_html_path"))
    manifest["source"] = manifest.get("source") or SURVIVAL_ARTIFACT_SOURCE
    return manifest
