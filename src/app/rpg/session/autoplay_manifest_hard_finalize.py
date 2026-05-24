from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

SOURCE = "bundle_d_hard_artifact_manifest_finalizer"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"
HEALTH_FILE = "autoplay-health.json"
EVALUATION_FILE = "hundred-turn-evaluation.json"
READINESS_FILE = "hundred-turn-readiness-summary.json"

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
BUNDLE_D_FILES = [
    "readiness-report-projection-summary.json",
]
ALL_BUNDLE_FILES = [*BUNDLE_A_FILES, *BUNDLE_B_FILES, *BUNDLE_C_FILES, *BUNDLE_D_FILES]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=False) + "\n"
    tmp_path = path.with_name(path.name + ".tmp-hard-finalize")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)


def _presence(root: Path, names: Iterable[str]) -> Dict[str, bool]:
    return {name: (root / name).exists() and (root / name).stat().st_size > 2 for name in names}


def _present_names(presence: Dict[str, bool]) -> List[str]:
    return [name for name, present in presence.items() if present]


def _bundle_ok(presence: Dict[str, bool], *, required: bool) -> bool:
    if required:
        return all(presence.values())
    if not any(presence.values()):
        return True
    return all(presence.values())


def build_hard_finalized_manifest(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    existing = _read_json(root / ARTIFACT_MANIFEST_FILE)
    bundle_a_presence = _presence(root, BUNDLE_A_FILES)
    bundle_b_presence = _presence(root, BUNDLE_B_FILES)
    bundle_c_presence = _presence(root, BUNDLE_C_FILES)
    bundle_d_presence = _presence(root, BUNDLE_D_FILES)
    physical = {
        **bundle_a_presence,
        **bundle_b_presence,
        **bundle_c_presence,
        **bundle_d_presence,
    }
    files = list(dict.fromkeys([*list(existing.get("files") or []), *_present_names(physical)]))
    embedded = _safe_dict(existing.get("embedded_artifacts"))
    for name in files:
        if name in ALL_BUNDLE_FILES:
            embedded[name] = _read_json(root / name)
    return {
        **existing,
        "format_version": "bundle_abcd_artifact_manifest_hard_finalized_v1",
        "source": SOURCE,
        "ok": _bundle_ok(bundle_a_presence, required=True)
        and _bundle_ok(bundle_b_presence, required=False)
        and _bundle_ok(bundle_c_presence, required=False)
        and _bundle_ok(bundle_d_presence, required=False),
        "bundle_a_files": list(BUNDLE_A_FILES),
        "bundle_b_files": list(BUNDLE_B_FILES),
        "bundle_c_files": list(BUNDLE_C_FILES),
        "bundle_d_files": list(BUNDLE_D_FILES),
        "files": files,
        "physical_presence": bundle_a_presence,
        "bundle_b_physical_presence": bundle_b_presence,
        "bundle_c_physical_presence": bundle_c_presence,
        "bundle_d_physical_presence": bundle_d_presence,
        "embedded_artifacts": embedded,
        "hard_finalized": True,
        "final_write_after_all_wrappers": True,
    }


def _patch_health(root: Path, manifest: Dict[str, Any]) -> None:
    path = root / HEALTH_FILE
    health = _read_json(path)
    if not health:
        return
    health["artifact_manifest_hard_finalized"] = {
        "applied": True,
        "source": SOURCE,
        "manifest_file": ARTIFACT_MANIFEST_FILE,
        "ok": bool(manifest.get("ok")),
        "final_write_after_all_wrappers": True,
    }
    _atomic_write_json(path, health)


def _patch_evaluation(root: Path, manifest: Dict[str, Any]) -> None:
    path = root / EVALUATION_FILE
    evaluation = _read_json(path)
    if not evaluation:
        return
    summaries = _safe_dict(evaluation.get("artifact_level_summaries"))
    summaries[ARTIFACT_MANIFEST_FILE] = {
        "source": SOURCE,
        "ok": manifest.get("ok"),
        "format_version": manifest.get("format_version"),
        "hard_finalized": True,
        "final_write_after_all_wrappers": True,
        "bundle_a_files": manifest.get("bundle_a_files"),
        "bundle_b_files": manifest.get("bundle_b_files"),
        "bundle_c_files": manifest.get("bundle_c_files"),
        "bundle_d_files": manifest.get("bundle_d_files"),
        "physical_presence": manifest.get("physical_presence"),
        "bundle_b_physical_presence": manifest.get("bundle_b_physical_presence"),
        "bundle_c_physical_presence": manifest.get("bundle_c_physical_presence"),
        "bundle_d_physical_presence": manifest.get("bundle_d_physical_presence"),
    }
    evaluation["artifact_level_summaries"] = summaries
    _atomic_write_json(path, evaluation)


def _patch_readiness(root: Path, manifest: Dict[str, Any]) -> None:
    path = root / READINESS_FILE
    readiness = _read_json(path)
    if not readiness:
        return
    readiness["artifact_manifest_hard_finalized"] = {
        "applied": True,
        "source": SOURCE,
        "manifest_file": ARTIFACT_MANIFEST_FILE,
        "ok": bool(manifest.get("ok")),
        "final_write_after_all_wrappers": True,
    }
    _atomic_write_json(path, readiness)


def hard_finalize_artifact_manifest(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    if not (root / EVALUATION_FILE).exists():
        return {"applied": False, "reason": "evaluation_missing", "source": SOURCE, "result_dir": str(root)}
    manifest = build_hard_finalized_manifest(root)
    manifest_path = root / ARTIFACT_MANIFEST_FILE
    _atomic_write_json(manifest_path, manifest)
    _patch_health(root, manifest)
    _patch_evaluation(root, manifest)
    _patch_readiness(root, manifest)
    # Keep manifest as the last write, after sidecar patches.
    _atomic_write_json(manifest_path, manifest)
    return {
        "applied": True,
        "source": SOURCE,
        "result_dir": str(root),
        "manifest_path": str(manifest_path),
        "manifest_ok": bool(manifest.get("ok")),
        "manifest_size": manifest_path.stat().st_size if manifest_path.exists() else 0,
        "final_write_after_all_wrappers": True,
    }
