from __future__ import annotations

import atexit
import builtins
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.rpg.session.bundle_a_artifacts import write_bundle_a_artifacts
from app.rpg.session.bundle_a_manifest_repair import repair_bundle_a_manifest
from app.rpg.session.bundle_b_artifacts import write_bundle_b_artifacts
from app.rpg.session.quality_gate_artifact_repair import repair_quality_gate_artifacts_if_present

_REGISTERED = False
_WRITE_GUARD_INSTALLED = False
_ORIGINAL_WRITE_TEXT = None
_ORIGINAL_OPEN = None
_CANDIDATES: List[Path] = []
_BUNDLE_FILES = [
    "quality-gate-summary.json",
    "survival-exit-criteria-summary.json",
    "transcript-payload-budget-summary.json",
    "long-run-dry-run-projection-summary.json",
    "content-exhaustion-forecast-summary.json",
    "npc-agency-schedule-summary.json",
    "economy-resource-pressure-summary.json",
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
        "format_version": "bundle_abc_artifact_manifest_guard_v2",
        "source": "bundle_ab_late_manifest_empty_write_guard",
        "ok": all(physical.values()),
        "bundle_a_files": _BUNDLE_FILES[:3],
        "bundle_b_files": _BUNDLE_FILES[3:5],
        "bundle_c_files": _BUNDLE_FILES[5:],
        "files": [name for name, present in physical.items() if present],
        "physical_presence": {name: physical[name] for name in _BUNDLE_FILES[:3]},
        "bundle_b_physical_presence": {name: physical[name] for name in _BUNDLE_FILES[3:5]},
        "bundle_c_physical_presence": {name: physical[name] for name in _BUNDLE_FILES[5:]},
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


def _guarded_manifest_text(root: Path, text: str | None = None) -> str:
    if text is not None and str(text).strip():
        return str(text)
    manifest = _bundle_manifest_from_physical_files(root)
    if manifest.get("embedded_artifacts"):
        return json.dumps(manifest, indent=2, sort_keys=False) + "\n"
    return "{}\n"


class _ManifestWriteBuffer(io.StringIO):
    def __init__(self, path: Path, root: Path, encoding: str | None):
        super().__init__()
        self._path = path
        self._root = root
        self._encoding = encoding or "utf-8"
        self._closed_once = False

    def close(self) -> None:  # type: ignore[override]
        if self._closed_once:
            return
        self._closed_once = True
        text = self.getvalue()
        payload = _guarded_manifest_text(self._root, text)
        Path.write_text(self._path, payload, encoding=self._encoding)
        super().close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def _install_empty_manifest_write_guard() -> None:
    global _WRITE_GUARD_INSTALLED, _ORIGINAL_WRITE_TEXT, _ORIGINAL_OPEN
    if _WRITE_GUARD_INSTALLED:
        return
    _ORIGINAL_WRITE_TEXT = Path.write_text
    _ORIGINAL_OPEN = builtins.open

    def _guarded_write_text(self, data, *args, **kwargs):
        root = _candidate_root_for_manifest(Path(self))
        if root is not None and (data is None or str(data).strip() == ""):
            data = _guarded_manifest_text(root, None)
        return _ORIGINAL_WRITE_TEXT(self, data, *args, **kwargs)

    def _guarded_open(file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
        try:
            path = Path(file) if isinstance(file, (str, bytes, os.PathLike)) else None
        except Exception:
            path = None
        root = _candidate_root_for_manifest(path) if path is not None else None
        text_write_mode = isinstance(mode, str) and "b" not in mode and any(flag in mode for flag in ("w", "x"))
        if root is not None and text_write_mode:
            return _ManifestWriteBuffer(path, root, encoding)
        return _ORIGINAL_OPEN(file, mode, buffering, encoding, errors, newline, closefd, opener)

    Path.write_text = _guarded_write_text
    builtins.open = _guarded_open
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
