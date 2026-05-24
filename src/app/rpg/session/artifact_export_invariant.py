from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List

SOURCE = "bundle_d2_single_writer_artifact_export_invariant"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"
REQUIRED_UNZIPPED_FILES = [
    ARTIFACT_MANIFEST_FILE,
    "autoplay-health.json",
    "summary.json",
    "hundred-turn-evaluation.json",
    "readiness-report-projection-summary.json",
]
REQUIRED_MANIFEST_EMBEDDED = [
    "quality-gate-summary.json",
    "survival-exit-criteria-summary.json",
    "transcript-payload-budget-summary.json",
    "long-run-dry-run-projection-summary.json",
    "content-exhaustion-forecast-summary.json",
    "npc-agency-schedule-summary.json",
    "economy-resource-pressure-summary.json",
    "readiness-report-projection-summary.json",
]


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


def _zip_manifest_candidates(result_dir: Path) -> List[Path]:
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


def _read_zip_manifest(zip_path: Path) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [name for name in zf.namelist() if name.replace("\\", "/").endswith(ARTIFACT_MANIFEST_FILE)]
            if not names:
                return {}
            payload = zf.read(names[0]).decode("utf-8")
            if not payload.strip():
                return {}
            value = json.loads(payload)
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _manifest_validation(manifest: Dict[str, Any]) -> Dict[str, Any]:
    embedded = _safe_dict(manifest.get("embedded_artifacts"))
    missing_embedded = [name for name in REQUIRED_MANIFEST_EMBEDDED if name not in embedded]
    checks = {
        "manifest_non_empty_json": bool(manifest),
        "manifest_ok_true": bool(manifest.get("ok")),
        "manifest_hard_finalized_true": bool(manifest.get("hard_finalized")),
        "manifest_embedded_artifacts_non_empty": bool(embedded),
        "manifest_required_embedded_present": not missing_embedded,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "missing_embedded_artifacts": missing_embedded,
        "format_version": manifest.get("format_version"),
        "source": manifest.get("source"),
        "embedded_artifact_count": len(embedded),
    }


def validate_artifact_export_invariant(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    missing_unzipped = [name for name in REQUIRED_UNZIPPED_FILES if not (root / name).exists() or (root / name).stat().st_size <= 2]
    unzipped_manifest = _read_json(root / ARTIFACT_MANIFEST_FILE)
    unzipped_validation = _manifest_validation(unzipped_manifest)
    zip_results = []
    for zip_path in _zip_manifest_candidates(root):
        manifest = _read_zip_manifest(zip_path)
        validation = _manifest_validation(manifest)
        zip_results.append({
            "zip_path": str(zip_path),
            "ok": validation.get("ok"),
            "validation": validation,
        })
    checks = {
        "result_dir_exists": root.exists(),
        "required_unzipped_files_present": not missing_unzipped,
        "unzipped_manifest_valid": bool(unzipped_validation.get("ok")),
        "result_zip_manifest_valid": any(item.get("ok") for item in zip_results) if zip_results else False,
    }
    failed_checks = [name for name, ok in checks.items() if not ok]
    return {
        "format_version": "bundle_d2_artifact_export_invariant_v1",
        "source": SOURCE,
        "ok": not failed_checks,
        "checks": checks,
        "failed_checks": failed_checks,
        "result_dir": str(root),
        "missing_unzipped_files": missing_unzipped,
        "unzipped_manifest": unzipped_validation,
        "zip_manifest_results": zip_results,
        "zip_count": len(zip_results),
    }


def enforce_artifact_export_invariant(result_dir: str | Path) -> Dict[str, Any]:
    result = validate_artifact_export_invariant(result_dir)
    if not result.get("ok"):
        raise RuntimeError(
            "artifact_export_invariant_failed:"
            f"failed_checks={result.get('failed_checks')}:"
            f"missing_unzipped_files={result.get('missing_unzipped_files')}:"
            f"unzipped_manifest={result.get('unzipped_manifest')}:"
            f"zip_count={result.get('zip_count')}"
        )
    return result
