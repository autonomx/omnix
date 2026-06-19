"""Post-run size guard for autoplay report artifacts.

Large 100-turn runs can generate oversized report JSON/HTML artifacts when full
runtime rows are embedded in the report.  This module replaces oversized report
files and ZIP members with compact manifests while preserving the rest of the
artifact bundle.  It runs only after the campaign has completed and never affects
simulation truth.
"""
from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.rpg.autoplay_item_report_hook import run_autoplay_item_report_hook

SIZE_GUARD_SOURCE = "autoplay_report_size_guard_v1"
REPORT_JSON_NAME = "autoplay-campaign-report.json"
REPORT_HTML_NAMES = {"autoplay-campaign-report.html", "autoplay-campaign-report-rich.html"}
DEFAULT_MAX_REPORT_JSON_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_REPORT_HTML_BYTES = 15 * 1024 * 1024
SUMMARY_NAME = "autoplay-report-size-guard-summary.json"


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _json_limit() -> int:
    return _safe_int(os.environ.get("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES"), DEFAULT_MAX_REPORT_JSON_BYTES)


def _html_limit() -> int:
    return _safe_int(os.environ.get("RPG_AUTOPLAY_MAX_REPORT_HTML_BYTES"), DEFAULT_MAX_REPORT_HTML_BYTES)


def _is_report_json(path_or_name: str | Path) -> bool:
    return Path(str(path_or_name)).name == REPORT_JSON_NAME


def _is_report_html(path_or_name: str | Path) -> bool:
    return Path(str(path_or_name)).name in REPORT_HTML_NAMES


def _limit_for_name(path_or_name: str | Path) -> int:
    if _is_report_json(path_or_name):
        return _json_limit()
    if _is_report_html(path_or_name):
        return _html_limit()
    return 0


def _compact_json_payload(*, artifact_name: str, original_size_bytes: int, limit_bytes: int) -> bytes:
    payload = {
        "ok": True,
        "capped": True,
        "source": SIZE_GUARD_SOURCE,
        "artifact_name": artifact_name,
        "original_size_bytes": original_size_bytes,
        "limit_bytes": limit_bytes,
        "reason": "report_artifact_exceeded_size_limit",
        "note": "Full-detail rows are retained in transcript/review artifacts; this report was replaced to keep operator bundles manageable.",
    }
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _compact_html_payload(*, artifact_name: str, original_size_bytes: int, limit_bytes: int) -> bytes:
    body = "\n".join(
        [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'><title>Autoplay Report Capped</title></head><body>",
            "<h1>Autoplay report capped</h1>",
            f"<p>Artifact: {artifact_name}</p>",
            f"<p>Original size bytes: {original_size_bytes}</p>",
            f"<p>Limit bytes: {limit_bytes}</p>",
            "<p>Full-detail rows are retained in transcript/review artifacts; this report was replaced to keep operator bundles manageable.</p>",
            "</body></html>",
        ]
    )
    return body.encode("utf-8")


def _compact_payload(name: str, original_size_bytes: int, limit_bytes: int) -> bytes:
    if _is_report_html(name):
        return _compact_html_payload(
            artifact_name=name,
            original_size_bytes=original_size_bytes,
            limit_bytes=limit_bytes,
        )
    return _compact_json_payload(
        artifact_name=name,
        original_size_bytes=original_size_bytes,
        limit_bytes=limit_bytes,
    )


def cap_oversized_report_files(output_dir: str | Path) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    capped: List[Dict[str, Any]] = []
    if not output_dir.exists():
        return {"ok": True, "capped_files": capped, "source": SIZE_GUARD_SOURCE}
    candidates = [path for path in output_dir.rglob("*") if path.is_file() and (_is_report_json(path) or _is_report_html(path))]
    for path in candidates:
        limit = _limit_for_name(path)
        if limit <= 0:
            continue
        size = path.stat().st_size
        if size <= limit:
            continue
        payload = _compact_payload(path.name, size, limit)
        path.write_bytes(payload)
        capped.append(
            {
                "path": str(path),
                "original_size_bytes": size,
                "new_size_bytes": len(payload),
                "limit_bytes": limit,
            }
        )
    return {"ok": True, "capped_files": capped, "source": SIZE_GUARD_SOURCE}


def _zip_member_limit(name: str) -> int:
    return _limit_for_name(name)


def _zip_member_should_cap(info: zipfile.ZipInfo) -> bool:
    limit = _zip_member_limit(info.filename)
    return limit > 0 and int(info.file_size) > limit


def _copy_zipinfo(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    copied = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
    copied.comment = info.comment
    copied.extra = info.extra
    copied.internal_attr = info.internal_attr
    copied.external_attr = info.external_attr
    copied.create_system = info.create_system
    copied.compress_type = zipfile.ZIP_DEFLATED
    return copied


def cap_oversized_report_zip(zip_path: str | Path) -> Dict[str, Any]:
    zip_path = Path(zip_path)
    if not zip_path.exists():
        return {"ok": True, "zip_path": str(zip_path), "capped_members": [], "source": SIZE_GUARD_SOURCE}
    capped: List[Dict[str, Any]] = []
    with zipfile.ZipFile(zip_path, "r") as source:
        infos = source.infolist()
        if not any(_zip_member_should_cap(info) for info in infos):
            return {"ok": True, "zip_path": str(zip_path), "capped_members": [], "source": SIZE_GUARD_SOURCE}
        fd, temp_name = tempfile.mkstemp(prefix=zip_path.stem + "-capped-", suffix=".zip", dir=str(zip_path.parent))
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as target:
                for info in infos:
                    out_info = _copy_zipinfo(info)
                    if _zip_member_should_cap(info):
                        limit = _zip_member_limit(info.filename)
                        payload = _compact_payload(info.filename, int(info.file_size), limit)
                        target.writestr(out_info, payload)
                        capped.append(
                            {
                                "member": info.filename,
                                "original_size_bytes": int(info.file_size),
                                "new_size_bytes": len(payload),
                                "limit_bytes": limit,
                            }
                        )
                    else:
                        target.writestr(out_info, source.read(info.filename))
            temp_path.replace(zip_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
    return {"ok": True, "zip_path": str(zip_path), "capped_members": capped, "source": SIZE_GUARD_SOURCE}


def _read_existing_summary(summary_path: Path) -> Dict[str, Any]:
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _merge_file_results(existing: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(current)
    existing_file_result = existing.get("file_result") if isinstance(existing.get("file_result"), dict) else {}
    existing_capped = list(existing_file_result.get("capped_files") or []) if isinstance(existing_file_result, dict) else []
    current_capped = list(current.get("capped_files") or [])
    merged["capped_files"] = existing_capped + current_capped
    return merged


def _merge_zip_results(existing: Dict[str, Any], current: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    existing_zip_results = existing.get("zip_results") if isinstance(existing.get("zip_results"), list) else []
    return list(existing_zip_results or []) + list(current or [])


def _safe_item_report_hook(output_dir: Path, zip_paths: List[str | Path]) -> Dict[str, Any]:
    try:
        return run_autoplay_item_report_hook(output_dir, zip_paths=zip_paths)
    except Exception as exc:  # pragma: no cover - defensive post-run guard
        return {"ok": False, "error": repr(exc), "source": "autoplay_item_report_hook_guard"}


def cap_oversized_autoplay_reports(output_dir: str | Path, *, zip_paths: Iterable[str | Path] = ()) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    zip_path_list = [path for path in zip_paths if path]
    summary_path = output_dir / SUMMARY_NAME
    existing_summary = _read_existing_summary(summary_path)
    item_report_result = _safe_item_report_hook(output_dir, zip_path_list)
    file_result = cap_oversized_report_files(output_dir)
    zip_results = [cap_oversized_report_zip(path) for path in zip_path_list]
    payload = dict(existing_summary)
    payload.update(
        {
            "ok": True,
            "source": SIZE_GUARD_SOURCE,
            "materialization_guard_source": existing_summary.get("materialization_guard_source"),
            "item_autoplay_report": item_report_result,
            "file_result": _merge_file_results(existing_summary, file_result),
            "zip_results": _merge_zip_results(existing_summary, zip_results),
        }
    )
    if not payload.get("materialization_guard_source"):
        payload.pop("materialization_guard_source", None)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["summary_path"] = str(summary_path)
    return payload
