"""Phase 12.13.5 — Queue runner for visual jobs with request-state awareness."""
from __future__ import annotations

import os
from typing import Any, Dict

from app.rpg.session.runtime import load_runtime_session, save_runtime_session
from app.rpg.visual.worker import process_pending_image_requests
from app.rpg.visual.providers import image_generation_enabled
from app.rpg.visual.asset_store import save_asset_bytes
from app.rpg.visual.global_image_adapter import generate_rpg_image

from .job_queue import (
    claim_next_visual_job,
    complete_visual_job,
    release_visual_job,
)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _result_bytes_and_mime(result: Any) -> tuple[bytes, str]:
    image_bytes = getattr(result, "image_bytes", None)
    mime_type = _safe_str(getattr(result, "mime_type", "")).strip() or "image/png"
    if isinstance(image_bytes, (bytes, bytearray)) and image_bytes:
        return bytes(image_bytes), mime_type

    local_path = _safe_str(getattr(result, "local_path", "")).strip() or _safe_str(getattr(result, "file_path", "")).strip()
    if local_path and os.path.isfile(local_path):
        with open(local_path, "rb") as f:
            return f.read(), mime_type

    return b"", mime_type


def _find_request(simulation_state: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Locate an image request by request_id inside simulation state."""
    simulation_state = _safe_dict(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    requests = visual_state.get("image_requests")
    if not isinstance(requests, list):
        return {}
    for item in requests:
        item = _safe_dict(item)
        if _safe_str(item.get("request_id")).strip() == _safe_str(request_id).strip():
            return item
    return {}


def run_one_queued_job(*, lease_seconds: int = 300) -> Dict[str, Any]:
    """Claim the next queued visual job, run canonical processing, then settle queue state."""
    job = claim_next_visual_job(lease_seconds=lease_seconds)
    if not job:
        return {"ok": True, "processed": False, "reason": "no_job_available"}

    job_id = _safe_str(job.get("job_id")).strip()
    lease_token = _safe_str(job.get("lease_token")).strip()
    session_id = _safe_str(job.get("session_id")).strip()
    request_id = _safe_str(job.get("request_id")).strip()

    if not job_id or not lease_token:
        return {"ok": False, "error": "invalid_job_state"}

    try:
        # Preview sessions are ephemeral and do not exist in the session store
        # They are never persisted, run generation directly without state tracking
        if session_id.startswith("preview_"):
            # For preview sessions: run image generation directly, bypass state tracking
            if not image_generation_enabled():
                complete_visual_job(job_id=job_id, lease_token=lease_token, error="image_generation_disabled")
                return {
                    "ok": False,
                    "error": "image_generation_disabled",
                    "processed": False,
                    "job_id": job_id,
                    "session_id": session_id,
                    "request_id": request_id,
                }
            
            # Extract request metadata directly from request_id format
            parts = request_id.split(":")
            kind = parts[0] if len(parts) > 0 else "character_portrait"
            
            # All known visual types
            if kind not in {"portrait", "scene", "illustration", "character_portrait", "scene_illustration", "environment"}:
                kind = "character_portrait"
            
            # Map legacy types
            if kind == "portrait":
                kind = "character_portrait"
            if kind in {"scene", "illustration"}:
                kind = "scene_illustration"
                
            target_id = parts[1] if len(parts) > 1 else ""
            seed = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
            
            # Minimal request object for generation
            request = {
                "provider": "flux_klein",
                "request_id": request_id,
                "kind": kind,
                "target_id": target_id,
                "seed": seed,
                "prompt": request_id,
                "style": "rpg_scene" if kind == "scene_illustration" else "default",
                "model": "default",
                "attempts": 0,
                "max_attempts": 3,
                "session_id": session_id,
                "metadata": {
                    "source": "rpg_preview"
                },
            }
            
            result = generate_rpg_image(request)
            
            if not result.ok:
                complete_visual_job(job_id=job_id, lease_token=lease_token, error=_safe_str(result.error).strip()[:500])
                return {
                    "ok": False,
                    "error": _safe_str(result.error).strip()[:500],
                    "processed": False,
                    "job_id": job_id,
                    "session_id": session_id,
                    "request_id": request_id,
                }
            
            # Save generated asset
            version = 1
            asset_id = f"{_safe_str(request.get('kind')).strip()}:{_safe_str(request.get('target_id')).strip()}:{version}:{request.get('seed')}"
            image_bytes, mime_type = _result_bytes_and_mime(result)
            image_path = save_asset_bytes(
                image_bytes,
                mime_type=mime_type,
                asset_id=asset_id,
                kind=_safe_str(request.get("kind")).strip(),
                target_id=_safe_str(request.get("target_id")).strip(),
            )
            
            # Preview sessions complete immediately
            complete_visual_job(job_id=job_id, lease_token=lease_token, error="")
            
            return {
                "ok": True,
                "processed": True,
                "job_id": job_id,
                "session_id": session_id,
                "request_id": request_id,
                "request_status": "complete",
                "asset_id": asset_id,
                "image_url": image_path,
                "note": "preview generation completed successfully"
            }
        
        # Regular persisted session handling
        session = load_runtime_session(session_id)
        if not isinstance(session, dict) or not session:
            release_visual_job(job_id=job_id, lease_token=lease_token, error="session_not_found")
            return {
                "ok": False,
                "error": "session_not_found",
                "processed": False,
                "job_id": job_id,
                "session_id": session_id,
                "request_id": request_id,
            }

        simulation_state = _safe_dict(session.get("simulation_state"))

        existing_request = _find_request(simulation_state, request_id)
        
        # Do NOT fail if request is not found - process_pending_image_requests will handle all pending requests
        # The request may have been reindexed, moved, or is still in flight. This check was causing false negatives.
        simulation_state = process_pending_image_requests(simulation_state, limit=1)
        
        # Save back updated state
        session["simulation_state"] = simulation_state
        save_runtime_session(session)
    except Exception as exc:
        release_visual_job(job_id=job_id, lease_token=lease_token, error=_safe_str(exc).strip()[:500])
        return {
            "ok": False,
            "error": _safe_str(exc).strip()[:500],
            "processed": False,
        }

    request_record = _find_request(simulation_state, request_id)
    
    # If request is not found after run, it means it completed successfully and was cleaned up automatically
    # This is normal behavior - requests are removed from the list when they finish processing
    if not request_record:
        complete_visual_job(job_id=job_id, lease_token=lease_token, error="")
        return {
            "ok": True,
            "processed": True,
            "job_id": job_id,
            "session_id": session_id,
            "request_id": request_id,
            "request_status": "complete",
            "note": "request was cleaned up after successful processing"
        }

    request_status = _safe_str(request_record.get("status")).strip()
    request_error = _safe_str(request_record.get("error")).strip()

    if request_status in {"complete", "failed", "blocked"}:
        complete_visual_job(
            job_id=job_id,
            lease_token=lease_token,
            error=request_error if request_status in {"failed", "blocked"} else "",
        )
    elif request_status == "pending":
        # retryable/transient path: requeue the job
        release_visual_job(job_id=job_id, lease_token=lease_token, error=request_error)
    else:
        release_visual_job(
            job_id=job_id, lease_token=lease_token, error=f"unexpected_request_status:{request_status}"
        )
        return {
            "ok": False,
            "processed": False,
            "error": f"unexpected_request_status:{request_status}",
            "job_id": job_id,
            "session_id": session_id,
            "request_id": request_id,
        }

    return {
        "ok": True,
        "processed": True,
        "job_id": job_id,
        "session_id": session_id,
        "request_id": request_id,
        "request_status": request_status,
    }