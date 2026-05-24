from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from app.rpg.session.artifact_export_invariant import validate_artifact_export_invariant

SOURCE = "bundle_d3_artifact_manifest_digest"
DIGEST_FILE = "artifact-manifest-digest.json"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or path.stat().st_size <= 2:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_text(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=False) + "\n"


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(data), encoding="utf-8")


def _candidate_zip_paths(result_dir: Path) -> List[Path]:
    candidates: List[Path] = []
    if result_dir.name.endswith("-unzipped"):
        candidates.append(result_dir.with_name(result_dir.name[: -len("-unzipped")] + ".zip"))
    candidates.extend(result_dir.parent.glob("*.zip"))
    out: List[Path] = []
    seen = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists() and zipfile.is_zipfile(path):
            out.append(path)
    return out


def _zip_manifest_digest(zip_path: Path) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [name for name in zf.namelist() if name.replace("\\", "/").endswith(ARTIFACT_MANIFEST_FILE)]
            if not names:
                return {"zip_path": str(zip_path), "ok": False, "reason": "manifest_entry_missing"}
            payload = zf.read(names[0])
            manifest = json.loads(payload.decode("utf-8")) if payload.strip() else {}
            embedded = _safe_dict(_safe_dict(manifest).get("embedded_artifacts"))
            return {
                "zip_path": str(zip_path),
                "ok": bool(manifest) and bool(manifest.get("ok")) and bool(manifest.get("hard_finalized")) and bool(embedded),
                "entry_name": names[0],
                "byte_size": len(payload),
                "sha256": _sha256_bytes(payload),
                "format_version": _safe_dict(manifest).get("format_version"),
                "source": _safe_dict(manifest).get("source"),
                "hard_finalized": bool(_safe_dict(manifest).get("hard_finalized")),
                "embedded_artifact_count": len(embedded),
            }
    except Exception as exc:
        return {"zip_path": str(zip_path), "ok": False, "reason": repr(exc)}


def build_artifact_manifest_digest(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    manifest_path = root / ARTIFACT_MANIFEST_FILE
    payload = manifest_path.read_bytes() if manifest_path.exists() else b""
    manifest = _read_json(manifest_path)
    embedded = _safe_dict(manifest.get("embedded_artifacts"))
    invariant = validate_artifact_export_invariant(root)
    zip_digests = [_zip_manifest_digest(path) for path in _candidate_zip_paths(root)]
    digest = {
        "format_version": "bundle_d3_artifact_manifest_digest_v1",
        "source": SOURCE,
        "ok": bool(invariant.get("ok")) and bool(manifest) and bool(embedded),
        "result_dir": str(root),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
        "manifest_exists": manifest_path.exists(),
        "manifest_byte_size": len(payload),
        "manifest_sha256": _sha256_bytes(payload) if payload else "",
        "manifest_format_version": manifest.get("format_version"),
        "manifest_source": manifest.get("source"),
        "manifest_ok": bool(manifest.get("ok")),
        "manifest_hard_finalized": bool(manifest.get("hard_finalized")),
        "manifest_final_write_after_all_wrappers": bool(manifest.get("final_write_after_all_wrappers")),
        "embedded_artifact_count": len(embedded),
        "embedded_artifact_names": sorted(embedded.keys()),
        "invariant_ok": bool(invariant.get("ok")),
        "invariant_failed_checks": invariant.get("failed_checks", []),
        "zip_manifest_digests": zip_digests,
        "zip_manifest_valid_count": sum(1 for item in zip_digests if item.get("ok")),
        "review_note": "Use this small digest for manifest review; artifact-manifest.json may be too large for inline content readers.",
    }
    return digest


def write_artifact_manifest_digest(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    digest = build_artifact_manifest_digest(root)
    _write_json(root / DIGEST_FILE, digest)
    return {
        "applied": True,
        "source": SOURCE,
        "result_dir": str(root),
        "digest_file": DIGEST_FILE,
        "ok": bool(digest.get("ok")),
        "manifest_byte_size": digest.get("manifest_byte_size"),
        "embedded_artifact_count": digest.get("embedded_artifact_count"),
        "zip_manifest_valid_count": digest.get("zip_manifest_valid_count"),
    }
