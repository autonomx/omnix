from __future__ import annotations

import atexit
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.rpg.session.bundle_a_artifacts import write_bundle_a_artifacts
from app.rpg.session.bundle_a_manifest_repair import repair_bundle_a_manifest
from app.rpg.session.bundle_b_artifacts import write_bundle_b_artifacts
from app.rpg.session.quality_gate_artifact_repair import repair_quality_gate_artifacts_if_present

_REGISTERED = False
_WRITE_GUARD_INSTALLED = False
_ORIGINAL_WRITE_TEXT = None
_CANDIDATES: List[Path] = []
_BUNDLE_FILES = [
    "quality-gate-summary.json",
    "survival-exit-criteria-summary.json",
    "transcript-payload-budget-summary.json",
    "long-run-dry-run-projection-summary.json",
    "content-exhaustion-forecast-summary.json",
]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return {}
        return _safe_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return {}


def _bundle_manifest_from_physical_files(root: Path) -> Dict[str, Any]:
    physical = {name: (root / name).exists() and (root / name).stat().st_size > 2 for name in _BUNDLE_FILES}
    embedded = {name: _read_json(root / name) for name, present in physical.items() if present}
    return {
        "format_version": "bundle_ab_artifact_manifest_guard_v1",
        "source": "bundle_ab_late_manifest_empty_write_guard",
        "ok": all(physical.values()),
        "bundle_a_files": _BUNDLE_FILES[:3],
        "bundle_b_files": _BUNDLE_FILES[3:],
        "files": [name for name, present in physical.items() if present],
        "physical_presence": {name: physical[name] for name in _BUNDLE_FILES[:3]},
        "bundle_b_physical_presence": {name: physical[name] for name in _BUNDLE_FILES[3:]},
        "embedded_artifacts": embedded,
        "empty_write_guard_applied": True,
    }


def remember_manifest_candidates(paths: Iterable[str | Path]) -> None:
    global _CANDIDATES
    seen = set()
    out: List[Path] = []
    for raw in paths:
        path = Path(raw)
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    _CANDIDATES = out[:5]


def _candidate_root_for_manifest(path: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    if resolved.name != "artifact-manifest.json":
        return None
    root = resolved.parent
    if _CANDIDATES and all(root != candidate.resolve() for candidate in _CANDIDATES if candidate.exists()):
        # Only guard known autoplay result directories; do not alter unrelated writes.
        if not (root / "hundred-turn-evaluation.json").exists():
            return None
    if not (root / "hundred-turn-evaluation.json").exists():
        return None
    return root


def _install_empty_manifest_write_guard() -> None:
    global _WRITE_GUARD_INSTALLED, _ORIGINAL_WRITE_TEXT
    if _WRITE_GUARD_INSTALLED:
        return
    _ORIGINAL_WRITE_TEXT = Path.write_text

    def _guarded_write_text(self, data, *args, **kwargs):
        root = _candidate_root_for_manifest(Path(self))
        if root is not None and (data is None or str(data).strip() == ""):
            manifest = _bundle_manifest_from_physical_files(root)
            if manifest.get("embedded_artifacts"):
                data = json.dumps(manifest, indent=2, sort_keys=False) + "\n"
        return _ORIGINAL_WRITE_TEXT(self, data, *args, **kwargs)

    Path.write_text = _guarded_write_text
    _WRITE_GUARD_INSTALLED = True


def _repair_one(path: Path) -> dict:
    quality = repair_quality_gate_artifacts_if_present(path)
    bundle_a = write_bundle_a_artifacts(path)
    manifest_a = repair_bundle_a_manifest(path)
    bundle_b = write_bundle_b_artifacts(path)
    manifest_b = repair_bundle_a_manifest(path)
    return {
        "path": str(path),
        "quality": quality,
        "bundle_a": bundle_a,
        "manifest_a": manifest_a,
        "bundle_b": bundle_b,
        "manifest_b": manifest_b,
    }


def run_late_manifest_repair(paths: Iterable[str | Path] | None = None) -> dict:
    _install_empty_manifest_write_guard()
    repairs = []
    candidates = [Path(path) for path in (paths or _CANDIDATES)]
    for path in candidates[:5]:
        try:
            item = _repair_one(path)
        except Exception as exc:
            item = {"path": str(path), "error": repr(exc), "source": "bundle_ab_late_manifest_repair"}
        repairs.append(item)
        if any(isinstance(item.get(key), dict) and item[key].get("applied") for key in ("quality", "bundle_a", "manifest_a", "bundle_b", "manifest_b")):
            break
    return {"source": "bundle_ab_late_manifest_repair", "repairs": repairs, "applied": bool(repairs)}


def _run_registered_repair() -> None:
    globals()["BUNDLE_AB_LATE_MANIFEST_REPAIR_RESULT"] = run_late_manifest_repair()


def register_late_manifest_repair(paths: Iterable[str | Path] | None = None) -> None:
    global _REGISTERED
    if paths is not None:
        remember_manifest_candidates(paths)
    _install_empty_manifest_write_guard()
    if _REGISTERED:
        return
    atexit.register(_run_registered_repair)
    _REGISTERED = True
