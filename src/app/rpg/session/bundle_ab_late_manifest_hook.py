from __future__ import annotations

import atexit
from pathlib import Path
from typing import Iterable, List

from app.rpg.session.bundle_a_artifacts import write_bundle_a_artifacts
from app.rpg.session.bundle_a_manifest_repair import repair_bundle_a_manifest
from app.rpg.session.bundle_b_artifacts import write_bundle_b_artifacts
from app.rpg.session.quality_gate_artifact_repair import repair_quality_gate_artifacts_if_present

_REGISTERED = False
_CANDIDATES: List[Path] = []


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
    if _REGISTERED:
        return
    atexit.register(_run_registered_repair)
    _REGISTERED = True
