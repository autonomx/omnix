from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

SOURCE = "bundle_a1_final_artifact_manifest_repair"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"
BUNDLE_A_FILES = [
    "quality-gate-summary.json",
    "survival-exit-criteria-summary.json",
    "transcript-payload-budget-summary.json",
]
HEALTH_FILE = "autoplay-health.json"
EVALUATION_FILE = "hundred-turn-evaluation.json"
READINESS_FILE = "hundred-turn-readiness-summary.json"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return {}
        return _safe_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _manifest_needs_repair(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 2:
        return True
    manifest = _read_json(path)
    if not manifest:
        return True
    embedded = _safe_dict(manifest.get("embedded_artifacts"))
    return not all(name in embedded for name in BUNDLE_A_FILES)


def repair_bundle_a_manifest(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    manifest_path = root / ARTIFACT_MANIFEST_FILE
    physical_presence = {name: (root / name).exists() and (root / name).stat().st_size > 2 for name in BUNDLE_A_FILES}
    embedded = {name: _read_json(root / name) for name in BUNDLE_A_FILES if physical_presence.get(name)}
    if not all(physical_presence.values()):
        return {
            "applied": False,
            "reason": "bundle_a_files_missing",
            "source": SOURCE,
            "result_dir": str(root),
            "physical_presence": physical_presence,
        }
    if not _manifest_needs_repair(manifest_path):
        return {
            "applied": False,
            "reason": "manifest_already_complete",
            "source": SOURCE,
            "result_dir": str(root),
            "physical_presence": physical_presence,
        }

    existing = _read_json(manifest_path)
    existing_files = []
    if isinstance(existing.get("files"), list):
        existing_files = [str(item) for item in existing.get("files") if item]
    files = list(dict.fromkeys([*existing_files, *BUNDLE_A_FILES]))
    manifest = {
        **existing,
        "format_version": "bundle_a1_artifact_manifest_v2",
        "source": SOURCE,
        "ok": True,
        "bundle_a_files": list(BUNDLE_A_FILES),
        "files": files,
        "physical_presence": physical_presence,
        "embedded_artifacts": embedded,
        "repair_applied": True,
        "notes": [
            "Rebuilt from physical Bundle A files at finalization time.",
            "This makes the manifest robust even if an earlier writer left artifact-manifest.json empty."
        ],
    }
    _write_json(manifest_path, manifest)

    health_path = root / HEALTH_FILE
    health = _read_json(health_path)
    if health:
        health["bundle_a_artifact_manifest_path"] = ARTIFACT_MANIFEST_FILE
        health["bundle_a_manifest_repair"] = {"applied": True, "source": SOURCE, "manifest_file": ARTIFACT_MANIFEST_FILE}
        health["bundle_a_artifacts_ok"] = True
        _write_json(health_path, health)

    evaluation_path = root / EVALUATION_FILE
    evaluation = _read_json(evaluation_path)
    if evaluation:
        summaries = _safe_dict(evaluation.get("artifact_level_summaries"))
        summaries[ARTIFACT_MANIFEST_FILE] = {
            "source": SOURCE,
            "ok": True,
            "bundle_a_files": list(BUNDLE_A_FILES),
            "physical_presence": physical_presence,
        }
        evaluation["artifact_level_summaries"] = summaries
        _write_json(evaluation_path, evaluation)

    readiness_path = root / READINESS_FILE
    readiness = _read_json(readiness_path)
    if readiness:
        bundle = _safe_dict(readiness.get("bundle_a_artifacts"))
        bundle["manifest_repair_source"] = SOURCE
        bundle["manifest_file"] = ARTIFACT_MANIFEST_FILE
        readiness["bundle_a_artifacts"] = bundle
        _write_json(readiness_path, readiness)

    return {
        "applied": True,
        "source": SOURCE,
        "result_dir": str(root),
        "manifest_path": str(manifest_path),
        "physical_presence": physical_presence,
    }
