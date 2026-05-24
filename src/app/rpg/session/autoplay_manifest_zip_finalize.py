from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List

SOURCE = "bundle_d_result_zip_manifest_finalizer"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _manifest_payload(result_dir: Path) -> bytes:
    manifest = _read_json(result_dir / ARTIFACT_MANIFEST_FILE)
    if not manifest:
        return b""
    manifest["zip_manifest_finalized"] = True
    manifest["zip_manifest_finalizer_source"] = SOURCE
    return (json.dumps(manifest, indent=2, sort_keys=False) + "\n").encode("utf-8")


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


def _manifest_entry_names(zip_path: Path) -> List[str]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [info.filename for info in zf.infolist() if info.filename.replace("\\", "/").endswith(ARTIFACT_MANIFEST_FILE)]
    return list(dict.fromkeys(names)) or [ARTIFACT_MANIFEST_FILE]


def _rewrite_zip_manifest(zip_path: Path, payload: bytes) -> bool:
    entry_names = set(_manifest_entry_names(zip_path))
    tmp_path = zip_path.with_name(zip_path.name + ".tmp-manifest-finalize")
    wrote = set()
    with zipfile.ZipFile(zip_path, "r") as src, zipfile.ZipFile(tmp_path, "w") as dst:
        for info in src.infolist():
            if info.filename in entry_names:
                dst.writestr(info.filename, payload)
                wrote.add(info.filename)
            else:
                dst.writestr(info, src.read(info.filename))
        for name in sorted(entry_names - wrote):
            dst.writestr(name, payload)
    os.replace(tmp_path, zip_path)
    return True


def finalize_manifest_in_result_zips(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    payload = _manifest_payload(root)
    if not payload:
        return {"applied": False, "reason": "manifest_missing_or_empty", "source": SOURCE, "result_dir": str(root)}
    updated: List[str] = []
    failed: List[Dict[str, str]] = []
    for zip_path in _candidate_zips(root):
        try:
            if _rewrite_zip_manifest(zip_path, payload):
                updated.append(str(zip_path))
        except Exception as exc:
            failed.append({"path": str(zip_path), "error": repr(exc)})
    return {
        "applied": bool(updated),
        "source": SOURCE,
        "result_dir": str(root),
        "updated_paths": updated,
        "failed": failed,
        "ok": bool(updated) and not failed if (updated or failed) else True,
    }
