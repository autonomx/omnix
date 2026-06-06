"""Autoplay performance summary artifact helpers.

Phase 13.2 turns the 5-turn smoke evidence into a bounded hardening target:
autoplay runs should emit structured blocking/background timing artifacts so slow
runs can be triaged without manually parsing console logs.  These helpers are
advisory-only and never decide simulation truth.
"""
from __future__ import annotations

import json
import zipfile
from html import escape
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional

PERFORMANCE_ARTIFACT_SOURCE = "autoplay_performance_artifacts"
PERFORMANCE_SUMMARY_JSON_NAME = "autoplay-performance-summary.json"
PERFORMANCE_SUMMARY_HTML_NAME = "autoplay-performance-summary.html"
_MANUAL_TIMING_MAP_KEYS = (
    "manual_turn_stage_timing",
    "manual_stage_timing",
    "manual_stage_trace",
    "stage_timing",
    "manual_turn_breakdown",
)
_MANUAL_BREAKDOWN_KEYS = {
    "manual_turn_ms": ("manual_turn_ms", "manual_turn_duration_ms"),
    "pre_runtime_intent_llm_ms": ("pre_runtime_intent_llm_ms", "intent_llm_ms", "first_call_llm_ms"),
    "deterministic_runtime_apply_ms": ("deterministic_runtime_apply_ms", "runtime_apply_ms"),
    "grounding_validation_ms": ("grounding_validation_ms", "validation_ms"),
    "repair_ms": ("repair_ms", "grounding_repair_ms"),
    "state_snapshot_ms": ("state_snapshot_ms", "snapshot_ms"),
    "deferred_enqueue_ms": ("deferred_enqueue_ms", "background_enqueue_ms"),
}
_DEFAULT_TARGETS = {
    "avg_wall_seconds": 10.0,
    "avg_player_agent_seconds": 3.0,
    "avg_runtime_seconds": 7.0,
    "final_drain_seconds": 3.0,
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _nested_maps(row: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    maps: List[Mapping[str, Any]] = [row]
    primary_keys = (
        "performance",
        "timing",
        "metrics",
        "turn_result",
        "runtime",
        "turn_runtime",
        *_MANUAL_TIMING_MAP_KEYS,
    )
    for key in primary_keys:
        value = row.get(key)
        if isinstance(value, dict):
            maps.append(value)
            for nested_key in primary_keys:
                nested = value.get(nested_key)
                if isinstance(nested, dict):
                    maps.append(nested)
    return maps


def _first_number(row: Mapping[str, Any], keys: Iterable[str]) -> Optional[float]:
    wanted = tuple(keys)
    for mapping in _nested_maps(row):
        for key in wanted:
            value = _safe_float(mapping.get(key))
            if value is not None:
                return value
    return None


def _metric_stats(values: Iterable[Optional[float]]) -> Dict[str, Any]:
    clean = [value for value in values if value is not None and value >= 0]
    if not clean:
        return {"count": 0, "avg_seconds": None, "max_seconds": None, "min_seconds": None}
    return {
        "count": len(clean),
        "avg_seconds": round(mean(clean), 3),
        "max_seconds": round(max(clean), 3),
        "min_seconds": round(min(clean), 3),
    }


def _metric_stats_ms(values: Iterable[Optional[float]]) -> Dict[str, Any]:
    clean = [value for value in values if value is not None and value >= 0]
    if not clean:
        return {"count": 0, "avg_ms": None, "max_ms": None, "min_ms": None}
    return {
        "count": len(clean),
        "avg_ms": round(mean(clean), 3),
        "max_ms": round(max(clean), 3),
        "min_ms": round(min(clean), 3),
    }


def _turn_index(row: Mapping[str, Any], fallback: int) -> int:
    value = _first_number(row, ("turn_index", "turn", "turn_number", "tick"))
    return int(value) if value is not None else fallback


def _build_turn_metrics(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    for index, raw_row in enumerate(rows, start=1):
        row = _safe_dict(raw_row)
        if not row:
            continue
        turn_metric = {
            "turn_index": _turn_index(row, index),
            "wall_seconds": _first_number(row, ("wall_seconds", "elapsed_seconds", "duration_seconds", "turn_seconds", "turn_wall_seconds")),
            "blocking_seconds": _first_number(row, ("blocking_seconds", "human_blocking_seconds", "foreground_seconds")),
            "player_agent_seconds": _first_number(row, ("player_agent_seconds", "player_agent_duration_seconds", "action_selection_seconds")),
            "runtime_seconds": _first_number(row, ("runtime_seconds", "turn_runtime_seconds", "runtime_duration_seconds")),
            "background_seconds": _first_number(row, ("background_seconds", "background_job_seconds", "background_llm_seconds")),
        }
        if any(value is not None for key, value in turn_metric.items() if key != "turn_index"):
            metrics.append(turn_metric)
    return metrics


def _manual_breakdown_row(row: Mapping[str, Any], index: int) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"turn_index": _turn_index(row, index)}
    for output_key, aliases in _MANUAL_BREAKDOWN_KEYS.items():
        payload[output_key] = _first_number(row, aliases)
    return payload


def _build_manual_turn_breakdown(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    breakdown_rows: List[Dict[str, Any]] = []
    for index, raw_row in enumerate(rows, start=1):
        row = _safe_dict(raw_row)
        if not row:
            continue
        payload = _manual_breakdown_row(row, index)
        if any(value is not None for key, value in payload.items() if key != "turn_index"):
            breakdown_rows.append(payload)
    summary = {
        key: _metric_stats_ms(row.get(key) for row in breakdown_rows)
        for key in _MANUAL_BREAKDOWN_KEYS
    }
    return {"turns_observed": len(breakdown_rows), "summary": summary, "turn_metrics": breakdown_rows}


def _summary_number(summary: Mapping[str, Any], keys: Iterable[str]) -> Optional[float]:
    for mapping in _nested_maps(summary):
        for key in keys:
            value = _safe_float(mapping.get(key))
            if value is not None:
                return value
    return None


def build_autoplay_performance_summary(
    rows: Iterable[Mapping[str, Any]],
    *,
    run_summary: Optional[Mapping[str, Any]] = None,
    targets: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    rows = list(rows)
    run_summary = _safe_dict(run_summary)
    targets = dict(_DEFAULT_TARGETS if targets is None else targets)
    turn_metrics = _build_turn_metrics(rows)
    manual_breakdown = _build_manual_turn_breakdown(rows)
    wall = _metric_stats(row.get("wall_seconds") for row in turn_metrics)
    blocking = _metric_stats(row.get("blocking_seconds") for row in turn_metrics)
    player_agent = _metric_stats(row.get("player_agent_seconds") for row in turn_metrics)
    runtime = _metric_stats(row.get("runtime_seconds") for row in turn_metrics)
    background = _metric_stats(row.get("background_seconds") for row in turn_metrics)
    final_drain = _summary_number(run_summary, ("final_drain_seconds", "background_final_drain_seconds", "drain_seconds"))
    warnings: List[str] = []
    if wall.get("avg_seconds") is not None and wall["avg_seconds"] > targets["avg_wall_seconds"]:
        warnings.append("avg_wall_seconds_above_target")
    if player_agent.get("avg_seconds") is not None and player_agent["avg_seconds"] > targets["avg_player_agent_seconds"]:
        warnings.append("avg_player_agent_seconds_above_target")
    if runtime.get("avg_seconds") is not None and runtime["avg_seconds"] > targets["avg_runtime_seconds"]:
        warnings.append("avg_runtime_seconds_above_target")
    if final_drain is not None and final_drain > targets["final_drain_seconds"]:
        warnings.append("final_drain_seconds_above_target")
    return {
        "ok": not warnings,
        "advisory_only": True,
        "source": PERFORMANCE_ARTIFACT_SOURCE,
        "turns_observed": len(turn_metrics),
        "targets": targets,
        "summary": {
            "wall": wall,
            "blocking": blocking,
            "player_agent": player_agent,
            "runtime": runtime,
            "background": background,
            "final_drain_seconds": round(final_drain, 3) if final_drain is not None else None,
        },
        "manual_turn_breakdown": manual_breakdown,
        "warnings": warnings,
        "turn_metrics": turn_metrics,
    }


def render_autoplay_performance_html(summary: Mapping[str, Any]) -> str:
    summary = _safe_dict(summary)
    metrics = _safe_dict(summary.get("summary"))
    manual = _safe_dict(_safe_dict(summary.get("manual_turn_breakdown")).get("summary"))
    warnings = summary.get("warnings") or []
    warning_html = "".join(f"<li>{escape(_safe_str(item))}</li>" for item in warnings) or "<li>none</li>"
    rows = []
    for name in ("wall", "blocking", "player_agent", "runtime", "background"):
        stat = _safe_dict(metrics.get(name))
        rows.append(
            f"<tr><td>{escape(name)}</td><td>{escape(_safe_str(stat.get('avg_seconds')))}</td>"
            f"<td>{escape(_safe_str(stat.get('max_seconds')))}</td><td>{escape(_safe_str(stat.get('count')))}</td></tr>"
        )
    manual_rows = []
    for name in _MANUAL_BREAKDOWN_KEYS:
        stat = _safe_dict(manual.get(name))
        manual_rows.append(
            f"<tr><td>{escape(name)}</td><td>{escape(_safe_str(stat.get('avg_ms')))}</td>"
            f"<td>{escape(_safe_str(stat.get('max_ms')))}</td><td>{escape(_safe_str(stat.get('count')))}</td></tr>"
        )
    return "\n".join([
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Autoplay Performance Summary</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:24px;line-height:1.45}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px 10px}.status{font-weight:800}</style>",
        "</head><body>",
        "<h1>Autoplay Performance Summary</h1>",
        f"<p class='status'>ok: {str(bool(summary.get('ok'))).lower()}</p>",
        f"<p>turns observed: {escape(_safe_str(summary.get('turns_observed')))}</p>",
        "<table><thead><tr><th>metric</th><th>avg seconds</th><th>max seconds</th><th>count</th></tr></thead><tbody>",
        *rows,
        "</tbody></table>",
        "<h2>Manual turn breakdown</h2>",
        "<table><thead><tr><th>stage</th><th>avg ms</th><th>max ms</th><th>count</th></tr></thead><tbody>",
        *manual_rows,
        "</tbody></table>",
        "<h2>Warnings</h2>",
        f"<ul>{warning_html}</ul>",
        "</body></html>",
    ])


def write_autoplay_performance_artifacts(output_dir: str | Path, rows: Iterable[Mapping[str, Any]], *, run_summary: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    summary = build_autoplay_performance_summary(rows, run_summary=run_summary)
    json_path = _write_text(output_dir / PERFORMANCE_SUMMARY_JSON_NAME, _json_dumps(summary))
    html_path = _write_text(output_dir / PERFORMANCE_SUMMARY_HTML_NAME, render_autoplay_performance_html(summary))
    return {"ok": True, "summary": summary, "json_path": str(json_path), "html_path": str(html_path), "source": PERFORMANCE_ARTIFACT_SOURCE}


def append_autoplay_performance_artifacts_to_zip(zip_path: str | Path, rows: Iterable[Mapping[str, Any]], *, run_summary: Optional[Mapping[str, Any]] = None, prefix: str = "performance") -> Dict[str, Any]:
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    summary = build_autoplay_performance_summary(rows, run_summary=run_summary)
    prefix = _safe_str(prefix).strip().strip("/")
    json_name = f"{prefix}/{PERFORMANCE_SUMMARY_JSON_NAME}" if prefix else PERFORMANCE_SUMMARY_JSON_NAME
    html_name = f"{prefix}/{PERFORMANCE_SUMMARY_HTML_NAME}" if prefix else PERFORMANCE_SUMMARY_HTML_NAME
    mode = "a" if zip_path.exists() else "w"
    with zipfile.ZipFile(zip_path, mode, compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(json_name, _json_dumps(summary))
        zf.writestr(html_name, render_autoplay_performance_html(summary))
    return {"ok": True, "summary": summary, "zip_path": str(zip_path), "zip_members": [json_name, html_name], "source": PERFORMANCE_ARTIFACT_SOURCE}


def attach_autoplay_performance_manifest(report_manifest: Optional[Mapping[str, Any]], artifact_result: Mapping[str, Any]) -> Dict[str, Any]:
    manifest = dict(_safe_dict(report_manifest))
    artifact_result = _safe_dict(artifact_result)
    artifacts = list(manifest.get("artifacts") or [])
    if artifact_result.get("json_path"):
        artifacts.append({"kind": "autoplay_performance_json", "path": _safe_str(artifact_result.get("json_path")), "source": PERFORMANCE_ARTIFACT_SOURCE})
    if artifact_result.get("html_path"):
        artifacts.append({"kind": "autoplay_performance_html", "path": _safe_str(artifact_result.get("html_path")), "source": PERFORMANCE_ARTIFACT_SOURCE})
    for member in artifact_result.get("zip_members") or []:
        artifacts.append({"kind": "autoplay_performance_zip_member", "path": _safe_str(member), "zip_path": _safe_str(artifact_result.get("zip_path")), "source": PERFORMANCE_ARTIFACT_SOURCE})
    manifest["artifacts"] = artifacts
    manifest["autoplay_performance_summary"] = _safe_dict(artifact_result.get("summary"))
    manifest["source"] = manifest.get("source") or PERFORMANCE_ARTIFACT_SOURCE
    return manifest
