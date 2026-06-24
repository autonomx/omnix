"""Environmental panel report artifacts for autoplay outputs."""

from __future__ import annotations

import json
import zipfile
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from app.rpg.environmental_panel_runtime import build_environmental_panel_report

ENVIRONMENTAL_REPORT_SOURCE = "phase38_environmental_report_artifacts_v1"
ENVIRONMENTAL_PANEL_JSON_NAME = "environmental-panel.json"
ENVIRONMENTAL_PANEL_HTML_NAME = "environmental-panel.html"


def environmental_panel_artifact_payload(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    panels = [_panel_from_row(row) for row in rows if isinstance(row, Mapping)]
    panels = [panel for panel in panels if panel]
    payload: Dict[str, Any] = {
        "ok": bool(panels),
        "source": ENVIRONMENTAL_REPORT_SOURCE,
        "summary": _summary(panels),
        "latest_panels": panels[-40:],
        "json_filename": ENVIRONMENTAL_PANEL_JSON_NAME,
        "html_filename": ENVIRONMENTAL_PANEL_HTML_NAME,
    }
    payload["json_text"] = _json_dumps(payload)
    payload["html_text"] = render_environmental_panel_html(payload)
    return payload


def render_environmental_panel_html(payload: Mapping[str, Any]) -> str:
    payload = _safe_dict(payload)
    summary = _safe_dict(payload.get("summary"))
    panels = [_safe_dict(panel) for panel in _safe_list(payload.get("latest_panels"))]
    rows_html = "".join(_render_panel_row(panel) for panel in panels) or "<tr><td colspan='6'>No environmental panels observed.</td></tr>"
    changed_html = _count_list(summary.get("changed_field_counts"))
    opportunity_html = _count_list(summary.get("opportunity_counts"))
    trigger_html = _count_list(summary.get("trigger_counts"))
    return "\n".join(
        [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'><title>Environmental Panel</title>",
            "<style>body{font-family:system-ui,sans-serif;margin:24px;line-height:1.45}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.card{border:1px solid #ddd;border-radius:12px;padding:14px}table{border-collapse:collapse;width:100%;margin-top:16px}th,td{border:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}.badge{display:inline-block;border:1px solid #aaa;border-radius:999px;padding:2px 7px;margin:1px;font-size:.85em}</style>",
            "</head><body>",
            "<h1>Environmental Panel</h1>",
            "<div class='grid'>",
            f"<div class='card'><strong>Turns</strong><p>{_safe_int(summary.get('turn_count'))}</p></div>",
            f"<div class='card'><strong>Ready</strong><p>{_safe_int(summary.get('ready_turn_count'))}</p></div>",
            f"<div class='card'><strong>Changed fields</strong>{changed_html}</div>",
            f"<div class='card'><strong>Opportunities</strong>{opportunity_html}</div>",
            f"<div class='card'><strong>Triggers</strong>{trigger_html}</div>",
            "</div>",
            "<h2>Latest environmental panels</h2>",
            "<table><thead><tr><th>Turn</th><th>Badges</th><th>Triggers</th><th>Changed</th><th>Activity</th><th>Cues</th></tr></thead>",
            f"<tbody>{rows_html}</tbody></table>",
            "</body></html>",
        ]
    )


def write_environmental_report_artifacts(output_dir: str | Path, rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    payload = environmental_panel_artifact_payload(rows)
    json_path = _write_text(output_dir / ENVIRONMENTAL_PANEL_JSON_NAME, str(payload.get("json_text") or "{}"))
    html_path = _write_text(output_dir / ENVIRONMENTAL_PANEL_HTML_NAME, str(payload.get("html_text") or ""))
    return {
        "ok": True,
        "source": ENVIRONMENTAL_REPORT_SOURCE,
        "json_path": str(json_path),
        "html_path": str(html_path),
        "json_filename": ENVIRONMENTAL_PANEL_JSON_NAME,
        "html_filename": ENVIRONMENTAL_PANEL_HTML_NAME,
        "summary": payload.get("summary") or {},
    }


def append_environmental_report_artifacts_to_zip(
    zip_path: str | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    prefix: str = "environment",
) -> Dict[str, Any]:
    zip_path = Path(zip_path)
    payload = environmental_panel_artifact_payload(rows)
    normalized = prefix.strip().strip("/")
    json_name = f"{normalized}/{ENVIRONMENTAL_PANEL_JSON_NAME}" if normalized else ENVIRONMENTAL_PANEL_JSON_NAME
    html_name = f"{normalized}/{ENVIRONMENTAL_PANEL_HTML_NAME}" if normalized else ENVIRONMENTAL_PANEL_HTML_NAME
    with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(json_name, str(payload.get("json_text") or "{}"))
        zf.writestr(html_name, str(payload.get("html_text") or ""))
    return {
        "ok": True,
        "source": ENVIRONMENTAL_REPORT_SOURCE,
        "zip_path": str(zip_path),
        "json_member": json_name,
        "html_member": html_name,
        "summary": payload.get("summary") or {},
    }


def attach_environmental_artifact_manifest(manifest: Mapping[str, Any], artifact: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(manifest)
    result["environmental_panel_report"] = dict(artifact)
    return result


def _panel_from_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    panel = _safe_dict(row.get("environmental_panel"))
    if panel:
        return dict(panel)
    sections = _safe_dict(_safe_dict(row.get("report_surface")).get("sections"))
    panel = _safe_dict(sections.get("environmental_panel"))
    if panel:
        return dict(panel)
    turn_result = _safe_dict(row.get("turn_result"))
    if turn_result:
        return build_environmental_panel_report(turn_result)
    return {}


def _summary(panels: list[Mapping[str, Any]]) -> Dict[str, Any]:
    ready = 0
    triggers: Dict[str, int] = {}
    changed: Dict[str, int] = {}
    opportunities: Dict[str, int] = {}
    for panel in panels:
        ready += int(panel.get("ready") is True)
        _count_values(triggers, panel.get("triggers"))
        _count_values(changed, panel.get("changed_fields"))
        _count_values(opportunities, panel.get("opportunities"))
    return {
        "turn_count": len(panels),
        "ready_turn_count": ready,
        "trigger_counts": dict(sorted(triggers.items())),
        "changed_field_counts": dict(sorted(changed.items())),
        "opportunity_counts": dict(sorted(opportunities.items())),
    }


def _render_panel_row(panel: Mapping[str, Any]) -> str:
    badges = "".join(f"<span class='badge'>{escape(_safe_str(item))}</span>" for item in _safe_list(panel.get("badges")))
    triggers = ", ".join(escape(_safe_str(item)) for item in _safe_list(panel.get("triggers")))
    changed = ", ".join(escape(_safe_str(item)) for item in _safe_list(panel.get("changed_fields")))
    cues = "<br>".join(escape(_safe_str(item)) for item in _safe_list(panel.get("panel_cues")))
    activity = "<br>".join(escape(_safe_str(_safe_dict(item).get("text"))) for item in _safe_list(panel.get("visible_activity")))
    return "<tr>" + "".join(
        [
            f"<td>{escape(_safe_str(panel.get('turn_index') or ''))}</td>",
            f"<td>{badges}</td>",
            f"<td>{triggers}</td>",
            f"<td>{changed}</td>",
            f"<td>{activity}</td>",
            f"<td>{cues}</td>",
        ]
    ) + "</tr>"


def _count_values(counts: Dict[str, int], values: Any) -> None:
    for value in _safe_list(values):
        key = _safe_str(value)
        if key:
            counts[key] = counts.get(key, 0) + 1


def _count_list(value: Any) -> str:
    counts = _safe_dict(value)
    if not counts:
        return "<p>none</p>"
    return "<ul>" + "".join(f"<li>{escape(_safe_str(key))}: {_safe_int(count)}</li>" for key, count in counts.items()) + "</ul>"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0
