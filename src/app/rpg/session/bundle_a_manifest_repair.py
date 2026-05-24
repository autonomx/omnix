from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

SOURCE = "bundle_abc_final_artifact_manifest_repair"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"
BUNDLE_A_FILES = [
    "quality-gate-summary.json",
    "survival-exit-criteria-summary.json",
    "transcript-payload-budget-summary.json",
]
BUNDLE_B_FILES = [
    "long-run-dry-run-projection-summary.json",
    "content-exhaustion-forecast-summary.json",
]
BUNDLE_C_FILES = [
    "npc-agency-schedule-summary.json",
    "economy-resource-pressure-summary.json",
]
HEALTH_FILE = "autoplay-health.json"
EVALUATION_FILE = "hundred-turn-evaluation.json"
READINESS_FILE = "hundred-turn-readiness-summary.json"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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


def _presence(root: Path, names: List[str]) -> Dict[str, bool]:
    return {name: (root / name).exists() and (root / name).stat().st_size > 2 for name in names}


def _present_names(presence: Dict[str, bool]) -> List[str]:
    return [name for name, present in presence.items() if present]


def _manifest_needs_repair(path: Path, required_embedded_names: List[str]) -> bool:
    if not path.exists() or path.stat().st_size <= 2:
        return True
    manifest = _read_json(path)
    if not manifest:
        return True
    embedded = _safe_dict(manifest.get("embedded_artifacts"))
    return not all(name in embedded for name in required_embedded_names)


def repair_bundle_a_manifest(result_dir: str | Path) -> Dict[str, Any]:
    """Repair the final artifact manifest for Bundle A/B/C files.

    Kept under the original function name because the late autoplay wrapper already
    calls it after bundle writers.  The repair is idempotent and treats later
    bundle files as required when their physical summaries are present.
    """

    root = Path(result_dir)
    manifest_path = root / ARTIFACT_MANIFEST_FILE
    bundle_a_presence = _presence(root, BUNDLE_A_FILES)
    bundle_b_presence = _presence(root, BUNDLE_B_FILES)
    bundle_c_presence = _presence(root, BUNDLE_C_FILES)
    if not all(bundle_a_presence.values()):
        return {
            "applied": False,
            "reason": "bundle_a_files_missing",
            "source": SOURCE,
            "result_dir": str(root),
            "physical_presence": bundle_a_presence,
            "bundle_b_physical_presence": bundle_b_presence,
            "bundle_c_physical_presence": bundle_c_presence,
        }

    required_names = [*BUNDLE_A_FILES, *_present_names(bundle_b_presence), *_present_names(bundle_c_presence)]
    if not _manifest_needs_repair(manifest_path, required_names):
        return {
            "applied": False,
            "reason": "manifest_already_complete",
            "source": SOURCE,
            "result_dir": str(root),
            "physical_presence": bundle_a_presence,
            "bundle_b_physical_presence": bundle_b_presence,
            "bundle_c_physical_presence": bundle_c_presence,
        }

    existing = _read_json(manifest_path)
    existing_files = [str(item) for item in _safe_list(existing.get("files")) if item]
    files = list(dict.fromkeys([*existing_files, *required_names]))
    embedded = dict(_safe_dict(existing.get("embedded_artifacts")))
    for name in required_names:
        embedded[name] = _read_json(root / name)
    bundle_b_complete = all(bundle_b_presence.values()) if any(bundle_b_presence.values()) else False
    bundle_c_complete = all(bundle_c_presence.values()) if any(bundle_c_presence.values()) else False
    manifest = {
        **existing,
        "format_version": "bundle_abc_artifact_manifest_v1",
        "source": SOURCE,
        "ok": all(bundle_a_presence.values()) and (not any(bundle_b_presence.values()) or bundle_b_complete) and (not any(bundle_c_presence.values()) or bundle_c_complete),
        "bundle_a_files": list(BUNDLE_A_FILES),
        "bundle_b_files": list(BUNDLE_B_FILES),
        "bundle_c_files": list(BUNDLE_C_FILES),
        "files": files,
        "physical_presence": bundle_a_presence,
        "bundle_b_physical_presence": bundle_b_presence,
        "bundle_c_physical_presence": bundle_c_presence,
        "embedded_artifacts": embedded,
        "repair_applied": True,
        "notes": [
            "Rebuilt from physical Bundle A/B/C files at finalization time.",
            "This remains robust if an earlier writer leaves artifact-manifest.json empty or only embeds earlier bundles."
        ],
    }
    _write_json(manifest_path, manifest)

    health_path = root / HEALTH_FILE
    health = _read_json(health_path)
    if health:
        health["bundle_a_artifact_manifest_path"] = ARTIFACT_MANIFEST_FILE
        health["bundle_a_manifest_repair"] = {"applied": True, "source": SOURCE, "manifest_file": ARTIFACT_MANIFEST_FILE}
        health["bundle_a_artifacts_ok"] = True
        if bundle_b_complete:
            health["bundle_b_artifact_manifest_path"] = ARTIFACT_MANIFEST_FILE
            health["bundle_b_manifest_repair"] = {"applied": True, "source": SOURCE, "manifest_file": ARTIFACT_MANIFEST_FILE}
            health["bundle_b_artifacts_ok"] = True
        if bundle_c_complete:
            health["bundle_c_artifact_manifest_path"] = ARTIFACT_MANIFEST_FILE
            health["bundle_c_manifest_repair"] = {"applied": True, "source": SOURCE, "manifest_file": ARTIFACT_MANIFEST_FILE}
            health["bundle_c_artifacts_ok"] = True
        _write_json(health_path, health)

    evaluation_path = root / EVALUATION_FILE
    evaluation = _read_json(evaluation_path)
    if evaluation:
        summaries = _safe_dict(evaluation.get("artifact_level_summaries"))
        summaries[ARTIFACT_MANIFEST_FILE] = {
            "source": SOURCE,
            "ok": manifest.get("ok"),
            "bundle_a_files": list(BUNDLE_A_FILES),
            "bundle_b_files": list(BUNDLE_B_FILES),
            "bundle_c_files": list(BUNDLE_C_FILES),
            "physical_presence": bundle_a_presence,
            "bundle_b_physical_presence": bundle_b_presence,
            "bundle_c_physical_presence": bundle_c_presence,
        }
        evaluation["artifact_level_summaries"] = summaries
        _write_json(evaluation_path, evaluation)

    readiness_path = root / READINESS_FILE
    readiness = _read_json(readiness_path)
    if readiness:
        bundle_a = _safe_dict(readiness.get("bundle_a_artifacts"))
        bundle_a["manifest_repair_source"] = SOURCE
        bundle_a["manifest_file"] = ARTIFACT_MANIFEST_FILE
        readiness["bundle_a_artifacts"] = bundle_a
        if bundle_b_complete or readiness.get("bundle_b_artifacts"):
            bundle_b = _safe_dict(readiness.get("bundle_b_artifacts"))
            bundle_b["manifest_repair_source"] = SOURCE
            bundle_b["manifest_file"] = ARTIFACT_MANIFEST_FILE
            readiness["bundle_b_artifacts"] = bundle_b
        if bundle_c_complete or readiness.get("bundle_c_artifacts"):
            bundle_c = _safe_dict(readiness.get("bundle_c_artifacts"))
            bundle_c["manifest_repair_source"] = SOURCE
            bundle_c["manifest_file"] = ARTIFACT_MANIFEST_FILE
            readiness["bundle_c_artifacts"] = bundle_c
        _write_json(readiness_path, readiness)

    return {
        "applied": True,
        "source": SOURCE,
        "result_dir": str(root),
        "manifest_path": str(manifest_path),
        "physical_presence": bundle_a_presence,
        "bundle_b_physical_presence": bundle_b_presence,
        "bundle_c_physical_presence": bundle_c_presence,
    }
