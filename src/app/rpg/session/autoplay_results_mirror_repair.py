from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.rpg.session.autoplay_manifest_hard_finalize import hard_finalize_artifact_manifest
from app.rpg.session.autoplay_manifest_zip_finalize import finalize_manifest_in_result_zips

SOURCE = "bundle_d_results_mirror_extraction_repair"
MIRROR_SUMMARY_FILE = "essential-mirror-consistency-summary.json"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"
CORE_FILES = [
    ARTIFACT_MANIFEST_FILE,
    "autoplay-health.json",
    "summary.json",
    "hundred-turn-evaluation.json",
]


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _file_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 2


def _artifact_manifest_valid(result_dir: Path) -> bool:
    path = result_dir / ARTIFACT_MANIFEST_FILE
    if not _file_nonempty(path):
        return False
    manifest = _read_json(path)
    return bool(manifest.get("ok")) and bool(manifest.get("hard_finalized")) and bool(manifest.get("embedded_artifacts"))


def _core_file_valid(result_dir: Path, name: str) -> bool:
    if name == ARTIFACT_MANIFEST_FILE:
        return _artifact_manifest_valid(result_dir)
    return _file_nonempty(result_dir / name)


def _candidate_zips(result_dir: Path) -> List[Path]:
    candidates: List[Path] = []
    if result_dir.name.endswith("-unzipped"):
        candidates.append(result_dir.with_name(result_dir.name[: -len("-unzipped")] + ".zip"))
    candidates.extend(result_dir.parent.glob("*.zip"))
    seen = set()
    out: List[Path] = []
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists() and zipfile.is_zipfile(path):
            out.append(path)
    return out


def _has_core_files(result_dir: Path) -> bool:
    return all(_core_file_valid(result_dir, name) for name in CORE_FILES)


def _extract_zip(zip_path: Path, result_dir: Path) -> int:
    count = 0
    result_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            target = result_dir / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member.filename))
            count += 1
    return count


def _write_mirror_summary(result_dir: Path, *, zip_path: Path | None, extracted_count: int, repaired: bool) -> Dict[str, Any]:
    files = [path for path in result_dir.rglob("*") if path.is_file()]
    core_presence = {name: _core_file_valid(result_dir, name) for name in CORE_FILES}
    raw_file_presence = {name: _file_nonempty(result_dir / name) for name in CORE_FILES}
    manifest = _read_json(result_dir / ARTIFACT_MANIFEST_FILE)
    summary = {
        "format_version": "bundle_d_results_mirror_extraction_repair_v2",
        "source": SOURCE,
        "ok": all(core_presence.values()),
        "repaired": repaired,
        "mirror_dir": str(result_dir),
        "zip_path": str(zip_path) if zip_path else "",
        "extracted_file_count": extracted_count,
        "present_file_count": len(files),
        "core_presence": core_presence,
        "raw_file_presence": raw_file_presence,
        "artifact_manifest_valid": _artifact_manifest_valid(result_dir),
        "artifact_manifest_format_version": manifest.get("format_version"),
        "artifact_manifest_hard_finalized": bool(manifest.get("hard_finalized")),
        "artifact_manifest_embedded_artifact_count": len(manifest.get("embedded_artifacts") or {}) if isinstance(manifest.get("embedded_artifacts"), dict) else 0,
        "missing_core_files": [name for name, present in core_presence.items() if not present],
        "note": "Generated review mirror must include valid core artifacts, not only present files.",
    }
    _write_json(result_dir / MIRROR_SUMMARY_FILE, summary)
    return summary


def repair_results_mirror_from_zip(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    before_has_core = _has_core_files(root)
    selected_zip: Path | None = None
    extracted_count = 0
    repaired = False
    if not before_has_core:
        for zip_path in _candidate_zips(root):
            selected_zip = zip_path
            extracted_count = _extract_zip(zip_path, root)
            repaired = True
            if _has_core_files(root):
                break
    hard_finalize = hard_finalize_artifact_manifest(root) if (root / "hundred-turn-evaluation.json").exists() else {"applied": False, "reason": "evaluation_missing"}
    zip_finalize = finalize_manifest_in_result_zips(root) if (root / ARTIFACT_MANIFEST_FILE).exists() else {"applied": False, "reason": "manifest_missing"}
    summary = _write_mirror_summary(root, zip_path=selected_zip, extracted_count=extracted_count, repaired=repaired)
    return {
        "applied": repaired or bool(hard_finalize.get("applied")) or bool(zip_finalize.get("applied")),
        "source": SOURCE,
        "result_dir": str(root),
        "ok": bool(summary.get("ok")),
        "before_has_core": before_has_core,
        "after_has_core": _has_core_files(root),
        "selected_zip": str(selected_zip) if selected_zip else "",
        "extracted_file_count": extracted_count,
        "hard_finalize": hard_finalize,
        "zip_finalize": zip_finalize,
        "summary": summary,
    }


def latest_result_dirs(test_results_roots: Iterable[str | Path], *, limit: int = 5) -> List[Path]:
    seen = set()
    candidates: List[Path] = []
    for raw_root in test_results_roots:
        base = Path(raw_root)
        if not base.exists():
            continue
        for marker in base.rglob(MIRROR_SUMMARY_FILE):
            parent = marker.parent.resolve()
            if parent in seen:
                continue
            seen.add(parent)
            candidates.append(parent)
        for marker in base.rglob("autoplay-campaign-results.zip"):
            parent = marker.with_name(marker.stem + "-unzipped").resolve()
            if parent in seen:
                continue
            seen.add(parent)
            candidates.append(parent)
    candidates.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return candidates[:limit]
