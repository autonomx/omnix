"""Phase 12.15 — Visual inspector builder."""
from __future__ import annotations

from typing import Any, Dict, List


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_visual_inspector_payload(
    simulation_state: Dict[str, Any],
    *,
    queue_jobs: List[Dict[str, Any]] | None = None,
    asset_manifest: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))

    image_requests = [_safe_dict(item) for item in _safe_list(visual_state.get("image_requests"))]
    visual_assets = [_safe_dict(item) for item in _safe_list(visual_state.get("visual_assets"))]

    request_rows = []
    for item in image_requests:
        request_rows.append(
            {
                "request_id": _safe_str(item.get("request_id")).strip(),
                "kind": _safe_str(item.get("kind")).strip(),
                "target_id": _safe_str(item.get("target_id")).strip(),
                "status": _safe_str(item.get("status")).strip(),
                "attempts": int(item.get("attempts") or 0),
                "max_attempts": int(item.get("max_attempts") or 0),
                "error": _safe_str(item.get("error")).strip(),
                "updated_at": _safe_str(item.get("updated_at")).strip(),
                "completed_at": _safe_str(item.get("completed_at")).strip(),
            }
        )

    asset_rows = []
    for item in visual_assets:
        asset_rows.append(
            {
                "asset_id": _safe_str(item.get("asset_id")).strip(),
                "kind": _safe_str(item.get("kind")).strip(),
                "target_id": _safe_str(item.get("target_id")).strip(),
                "status": _safe_str(item.get("status")).strip(),
                "model": _safe_str(item.get("model")).strip(),
                "style": _safe_str(item.get("style")).strip(),
                "url": _safe_str(item.get("url")).strip(),
                "local_path": _safe_str(item.get("local_path")).strip(),
                "created_from_request_id": _safe_str(item.get("created_from_request_id")).strip(),
            }
        )

    queue_rows = []
    for item in _safe_list(queue_jobs):
        item = _safe_dict(item)
        queue_rows.append(
            {
                "job_id": _safe_str(item.get("job_id")).strip(),
                "session_id": _safe_str(item.get("session_id")).strip(),
                "request_id": _safe_str(item.get("request_id")).strip(),
                "status": _safe_str(item.get("status")).strip(),
                "attempts": int(item.get("attempts") or 0),
                "lease_token": _safe_str(item.get("lease_token")).strip(),
                "lease_expires_at": _safe_str(item.get("lease_expires_at")).strip(),
                "updated_at": _safe_str(item.get("updated_at")).strip(),
                "completed_at": _safe_str(item.get("completed_at")).strip(),
                "error": _safe_str(item.get("error")).strip(),
            }
        )

    manifest_assets = _safe_dict(_safe_dict(asset_manifest).get("assets"))
    manifest_rows = []
    for asset_id in sorted(manifest_assets.keys()):
        item = _safe_dict(manifest_assets.get(asset_id))
        manifest_rows.append(
            {
                "asset_id": asset_id,
                "hash": _safe_str(item.get("hash")).strip(),
                "filename": _safe_str(item.get("filename")).strip(),
                "mime_type": _safe_str(item.get("mime_type")).strip(),
                "size": int(item.get("size") or 0),
                "kind": _safe_str(item.get("kind")).strip(),
                "target_id": _safe_str(item.get("target_id")).strip(),
            }
        )

    return {
        "request_count": len(request_rows),
        "asset_count": len(asset_rows),
        "queue_job_count": len(queue_rows),
        "manifest_asset_count": len(manifest_rows),
        "requests": request_rows,
        "assets": asset_rows,
        "queue_jobs": queue_rows,
        "asset_manifest": manifest_rows,
        "actions": {
            "queue_normalize_route": "/api/rpg/visual/queue/normalize",
            "queue_run_one_route": "/api/rpg/visual/queue/run_one",
            "queue_prune_route": "/api/rpg/visual/queue/prune",
            "asset_cleanup_route": "/api/rpg/visual/assets/cleanup",
        },
    }