from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

SOURCE = "bundle_d_readiness_report_projection"
REPORT_PROJECTION_FILE = "readiness-report-projection-summary.json"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"
EVALUATION_FILE = "hundred-turn-evaluation.json"
READINESS_FILE = "hundred-turn-readiness-summary.json"
HEALTH_FILE = "autoplay-health.json"

SECTION_SPECS = [
    {
        "id": "survival-exit-criteria",
        "title": "Survival Exit Criteria",
        "artifact": "survival-exit-criteria-summary.json",
        "required_keys": ["ok", "drink_water_count", "eat_food_count", "blocked_relief_count", "capped_thirst_turns"],
    },
    {
        "id": "transcript-payload-budget",
        "title": "Transcript Payload Budget",
        "artifact": "transcript-payload-budget-summary.json",
        "required_keys": ["ok", "advisory_ok", "projected_1000_turn_transcript_bytes", "oversized_row_count"],
    },
    {
        "id": "long-run-dry-run-projection",
        "title": "Long-Run Dry-Run Projection",
        "artifact": "long-run-dry-run-projection-summary.json",
        "required_keys": ["ok", "advisory_ok", "target_profiles", "recommended_next_run"],
    },
    {
        "id": "content-exhaustion-forecast",
        "title": "Content Exhaustion Forecast",
        "artifact": "content-exhaustion-forecast-summary.json",
        "required_keys": ["ok", "advisory_ok", "classification", "turns_until_content_exhaustion_estimate"],
    },
    {
        "id": "npc-agency-schedule",
        "title": "NPC Agency / Schedule Evidence",
        "artifact": "npc-agency-schedule-summary.json",
        "required_keys": ["ok", "npc_count", "schedule_event_count", "memory_event_count"],
    },
    {
        "id": "economy-resource-pressure",
        "title": "Economy / Resource Pressure",
        "artifact": "economy-resource-pressure-summary.json",
        "required_keys": ["ok", "paid_count", "unpaid_count", "total_spent", "ending_currency"],
    },
]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _read_json(path: Path) -> Any:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _artifact_from_sources(root: Path, evaluation: Dict[str, Any], manifest: Dict[str, Any], filename: str) -> Dict[str, Any]:
    embedded = _safe_dict(manifest.get("embedded_artifacts"))
    if isinstance(embedded.get(filename), dict) and embedded[filename]:
        return embedded[filename]
    summaries = _safe_dict(evaluation.get("artifact_level_summaries"))
    if isinstance(summaries.get(filename), dict) and summaries[filename]:
        return summaries[filename]
    return _safe_dict(_read_json(root / filename))


def _section_projection(root: Path, evaluation: Dict[str, Any], manifest: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    artifact = str(spec["artifact"])
    data = _artifact_from_sources(root, evaluation, manifest, artifact)
    missing_keys = [key for key in _safe_list(spec.get("required_keys")) if key not in data]
    physical_exists = (root / artifact).exists() and (root / artifact).stat().st_size > 2
    embedded = artifact in _safe_dict(manifest.get("embedded_artifacts"))
    ok = bool(data.get("ok")) and not missing_keys and physical_exists
    return {
        "id": spec["id"],
        "title": spec["title"],
        "artifact": artifact,
        "ok": ok,
        "artifact_ok": bool(data.get("ok")),
        "advisory_ok": bool(data.get("advisory_ok", data.get("ok"))),
        "physical_exists": physical_exists,
        "manifest_embedded": embedded,
        "missing_keys": missing_keys,
        "summary": {key: data.get(key) for key in _safe_list(spec.get("required_keys")) if key in data},
    }


def build_readiness_report_projection_summary(
    evaluation: Dict[str, Any],
    readiness: Dict[str, Any],
    manifest: Dict[str, Any],
    *,
    root: str | Path | None = None,
) -> Dict[str, Any]:
    result_root = Path(root) if root is not None else Path(".")
    evaluation = _safe_dict(evaluation)
    readiness = _safe_dict(readiness)
    manifest = _safe_dict(manifest)
    sections = [_section_projection(result_root, evaluation, manifest, spec) for spec in SECTION_SPECS]
    manifest_checks = {
        "manifest_ok": bool(manifest.get("ok")),
        "manifest_non_empty": bool(manifest),
        "manifest_final_write_after_sidecars": bool(manifest.get("final_write_after_sidecars")),
        "all_sections_manifest_embedded": all(section.get("manifest_embedded") for section in sections),
        "all_sections_physical": all(section.get("physical_exists") for section in sections),
    }
    checks = {
        "evaluation_ok": bool(evaluation.get("ok")),
        "readiness_ok": bool(readiness.get("ok")),
        "all_report_sections_ok": all(section.get("ok") for section in sections),
        **manifest_checks,
    }
    failed = [key for key, value in checks.items() if not value]
    return {
        "format_version": "bundle_d_readiness_report_projection_v1",
        "source": SOURCE,
        "ok": not failed,
        "advisory_ok": checks["all_report_sections_ok"] and checks["all_sections_physical"],
        "failed_checks": failed,
        "checks": checks,
        "section_count": len(sections),
        "sections": sections,
        "manifest_source": manifest.get("source"),
        "manifest_format_version": manifest.get("format_version"),
        "report_nav_items": [
            {"id": section["id"], "title": section["title"], "artifact": section["artifact"], "ok": section["ok"]}
            for section in sections
        ],
        "recommended_next_actions": [
            "Render these sections in the HTML campaign report with a product-facing summary and collapsed JSON details.",
            "Use this projection as the single report gate before 250/300-turn dry-run profiles.",
        ],
        "artifact_files": {"summary": REPORT_PROJECTION_FILE},
    }


def _patch_manifest(root: Path, projection: Dict[str, Any]) -> Dict[str, Any]:
    path = root / ARTIFACT_MANIFEST_FILE
    manifest = _safe_dict(_read_json(path))
    files = [str(item) for item in _safe_list(manifest.get("files")) if item]
    if REPORT_PROJECTION_FILE not in files:
        files.append(REPORT_PROJECTION_FILE)
    embedded = _safe_dict(manifest.get("embedded_artifacts"))
    embedded[REPORT_PROJECTION_FILE] = projection
    manifest.update({
        "source": "bundle_d_artifact_manifest_projection",
        "bundle_d_files": [REPORT_PROJECTION_FILE],
        "files": files,
        "bundle_d_physical_presence": {REPORT_PROJECTION_FILE: (root / REPORT_PROJECTION_FILE).exists() and (root / REPORT_PROJECTION_FILE).stat().st_size > 2},
        "embedded_artifacts": embedded,
    })
    manifest["ok"] = bool(manifest.get("ok", True)) and bool(manifest["bundle_d_physical_presence"][REPORT_PROJECTION_FILE])
    _write_json(path, manifest)
    return manifest


def _patch_evaluation(root: Path, projection: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    path = root / EVALUATION_FILE
    evaluation = _safe_dict(_read_json(path))
    if not evaluation:
        return
    summaries = _safe_dict(evaluation.get("artifact_level_summaries"))
    summaries[REPORT_PROJECTION_FILE] = projection
    summaries[ARTIFACT_MANIFEST_FILE] = {
        "source": manifest.get("source"),
        "ok": manifest.get("ok"),
        "bundle_d_files": manifest.get("bundle_d_files"),
        "bundle_d_physical_presence": manifest.get("bundle_d_physical_presence"),
    }
    evaluation["artifact_level_summaries"] = summaries
    evaluation["bundle_d_artifacts"] = {
        "source": SOURCE,
        "readiness_report_projection_ok": projection.get("ok"),
        "readiness_report_projection_advisory_ok": projection.get("advisory_ok"),
        "section_count": projection.get("section_count"),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
        "files": [REPORT_PROJECTION_FILE],
    }
    _write_json(path, evaluation)


def _patch_readiness(root: Path, projection: Dict[str, Any]) -> None:
    path = root / READINESS_FILE
    readiness = _safe_dict(_read_json(path))
    if not readiness:
        return
    readiness["bundle_d_artifacts"] = {
        "source": SOURCE,
        "readiness_report_projection_ok": bool(projection.get("ok")),
        "readiness_report_projection_advisory_ok": bool(projection.get("advisory_ok")),
        "section_count": projection.get("section_count"),
        "files": [REPORT_PROJECTION_FILE],
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    }
    _write_json(path, readiness)


def _patch_health(root: Path, projection: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    path = root / HEALTH_FILE
    health = _safe_dict(_read_json(path))
    if not health:
        return
    health["bundle_d_artifacts_ok"] = bool(projection.get("ok")) and bool(manifest.get("ok", True))
    health["readiness_report_projection_ok"] = bool(projection.get("ok"))
    health["readiness_report_projection_advisory_ok"] = bool(projection.get("advisory_ok"))
    health["bundle_d_artifact_manifest_path"] = ARTIFACT_MANIFEST_FILE
    health["bundle_d_artifacts"] = {
        "source": SOURCE,
        "files": [REPORT_PROJECTION_FILE],
        "physical_presence": manifest.get("bundle_d_physical_presence"),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    }
    _write_json(path, health)


def write_bundle_d_artifacts(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    evaluation = _safe_dict(_read_json(root / EVALUATION_FILE))
    readiness = _safe_dict(_read_json(root / READINESS_FILE))
    manifest = _safe_dict(_read_json(root / ARTIFACT_MANIFEST_FILE))
    if not evaluation:
        return {"applied": False, "reason": "evaluation_missing", "source": SOURCE, "result_dir": str(root)}
    projection = build_readiness_report_projection_summary(evaluation, readiness, manifest, root=root)
    _write_json(root / REPORT_PROJECTION_FILE, projection)
    manifest = _patch_manifest(root, projection)
    _patch_evaluation(root, projection, manifest)
    _patch_readiness(root, projection)
    _patch_health(root, projection, manifest)
    return {
        "applied": True,
        "source": SOURCE,
        "result_dir": str(root),
        "readiness_report_projection_ok": projection.get("ok"),
        "readiness_report_projection_advisory_ok": projection.get("advisory_ok"),
        "manifest_ok": manifest.get("ok"),
        "files": [REPORT_PROJECTION_FILE],
    }
