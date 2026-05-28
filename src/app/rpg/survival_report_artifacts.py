"""Bundle BH — survival metrics artifact writer helpers.

BG introduced the aggregation and HTML rendering primitives.  BH turns those
primitives into concrete artifact files that autoplay/report pipelines can write
or bundle into ZIP outputs without duplicating survival logic.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from app.rpg.survival_report_metrics import (
    build_survival_report_metrics,
    render_survival_report_html,
)

SURVIVAL_ARTIFACT_SOURCE = "runtime_survival_report_artifacts"
SURVIVAL_METRICS_JSON_NAME = "survival-report-metrics.json"
SURVIVAL_METRICS_HTML_NAME = "survival-report-metrics.html"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def survival_metrics_artifact_payload(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    metrics = build_survival_report_metrics(rows)
    html = render_survival_report_html(metrics)
    return {
        "metrics": metrics,
        "json_filename": SURVIVAL_METRICS_JSON_NAME,
        "html_filename": SURVIVAL_METRICS_HTML_NAME,
        "json_text": _json_dumps(metrics),
        "html_text": html,
        "source": SURVIVAL_ARTIFACT_SOURCE,
    }


def write_survival_report_artifacts(
    output_dir: str | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    json_name: str = SURVIVAL_METRICS_JSON_NAME,
    html_name: str = SURVIVAL_METRICS_HTML_NAME,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    payload = survival_metrics_artifact_payload(rows)
    json_path = _write_text(output_dir / json_name, _safe_str(payload.get("json_text")))
    html_path = _write_text(output_dir / html_name, _safe_str(payload.get("html_text")))
    return {
        "ok": True,
        "metrics": _safe_dict(payload.get("metrics")),
        "json_path": str(json_path),
        "html_path": str(html_path),
        "json_filename": json_name,
        "html_filename": html_name,
        "source": SURVIVAL_ARTIFACT_SOURCE,
    }


def append_survival_report_artifacts_to_zip(
    zip_path: str | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    prefix: str = "",
    json_name: str = SURVIVAL_METRICS_JSON_NAME,
    html_name: str = SURVIVAL_METRICS_HTML_NAME,
) -> Dict[str, Any]:
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    payload = survival_metrics_artifact_payload(rows)
    normalized_prefix = _safe_str(prefix).strip().strip("/")
    json_arcname = f"{normalized_prefix}/{json_name}" if normalized_prefix else json_name
    html_arcname = f"{normalized_prefix}/{html_name}" if normalized_prefix else html_name
    mode = "a" if zip_path.exists() else "w"
    with zipfile.ZipFile(zip_path, mode, compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(json_arcname, _safe_str(payload.get("json_text")))
        zf.writestr(html_arcname, _safe_str(payload.get("html_text")))
    return {
        "ok": True,
        "metrics": _safe_dict(payload.get("metrics")),
        "zip_path": str(zip_path),
        "zip_members": [json_arcname, html_arcname],
        "source": SURVIVAL_ARTIFACT_SOURCE,
    }


def attach_survival_artifact_manifest(report_manifest: Optional[Mapping[str, Any]], artifact_result: Mapping[str, Any]) -> Dict[str, Any]:
    manifest = dict(_safe_dict(report_manifest))
    artifacts = list(manifest.get("artifacts") or [])
    artifact_result = _safe_dict(artifact_result)
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
    for member in artifact_result.get("zip_members") or []:
        artifacts.append({
            "kind": "survival_metrics_zip_member",
            "path": _safe_str(member),
            "zip_path": _safe_str(artifact_result.get("zip_path")),
            "source": SURVIVAL_ARTIFACT_SOURCE,
        })
    manifest["artifacts"] = artifacts
    manifest["survival_report_metrics"] = _safe_dict(artifact_result.get("metrics"))
    manifest["source"] = manifest.get("source") or SURVIVAL_ARTIFACT_SOURCE
    return manifest
