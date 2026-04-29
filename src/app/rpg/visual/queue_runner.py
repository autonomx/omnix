from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from app.image.asset_store import save_image_asset_bytes as save_asset_bytes
from app.image.job_queue import complete_image_job, fail_image_job
from app.rpg.session.durable_store import load_session_from_disk as load_runtime_session
from app.rpg.session.durable_store import save_session_to_disk as save_runtime_session
from app.rpg.visual.global_image_adapter import generate_rpg_image
from app.rpg.visual.job_queue import (
    claim_next_visual_job,
    complete_visual_job,
    release_visual_job,
)
from app.rpg.visual.providers import image_generation_enabled
from app.rpg.visual.worker import process_pending_image_requests
from app.runtime_paths import generated_images_root
from app.shared import DATA_DIR


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _result_ok(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("ok"))
    return bool(getattr(value, "ok", False))


def _result_error(value: Any) -> str:
    if isinstance(value, dict):
        return _safe_str(value.get("error")).strip()
    return _safe_str(getattr(value, "error", "")).strip()


def _result_local_path(value: Any) -> str:
    if isinstance(value, dict):
        return _safe_str(value.get("local_path")).strip()
    return _safe_str(getattr(value, "local_path", "")).strip()


def _result_mime_type(value: Any) -> str:
    if isinstance(value, dict):
        return _safe_str(value.get("mime_type")).strip()
    return _safe_str(getattr(value, "mime_type", "")).strip()


def _result_seed(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("seed")
    return getattr(value, "seed", None)


def _public_generated_image_url(image_path: str) -> str:
    image_path = _safe_str(image_path).strip()
    if not image_path:
        return ""
    try:
        root = generated_images_root().resolve()
        path = Path(image_path).resolve()
        rel = path.relative_to(root).as_posix()
        return f"/generated-images/{rel}"
    except Exception:
        return f"/generated-images/{os.path.basename(image_path)}"


def _result_to_jsonable(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {
        "ok": bool(getattr(value, "ok", False)),
        "provider": _safe_str(getattr(value, "provider", "")).strip(),
        "status": _safe_str(getattr(value, "status", "")).strip(),
        "error": _safe_str(getattr(value, "error", "")).strip(),
        "asset_url": _safe_str(getattr(value, "asset_url", "")).strip(),
        "local_path": _safe_str(getattr(value, "local_path", "")).strip(),
        "seed": getattr(value, "seed", None),
        "width": getattr(value, "width", None),
        "height": getattr(value, "height", None),
        "mime_type": _safe_str(getattr(value, "mime_type", "")).strip(),
        "metadata": getattr(value, "metadata", {}) if isinstance(getattr(value, "metadata", {}), dict) else {},
    }


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


def _load_pending_request(session_id: str, request_id: str) -> Dict[str, Any]:
    session_id = _safe_str(session_id).strip()
    request_id = _safe_str(request_id).strip()
    if not session_id or not request_id:
        return {}

    session = load_runtime_session(session_id)
    if not isinstance(session, dict):
        return {}

    simulation_state = _safe_dict(session.get("simulation_state"))
    return _find_request(simulation_state, request_id)


def _claim_next_live_visual_job(*, lease_seconds: int = 300, max_skip: int = 8) -> Dict[str, Any]:
    """
    Claim the next queue job whose request still exists in session state.
    Skip stale jobs left behind after request replacement/dedup.
    """
    for _ in range(max_skip):
        job = claim_next_visual_job(lease_seconds=lease_seconds)
        if not job:
            return {}

        payload = _safe_dict(job.get("payload"))
        job_id = _safe_str(job.get("job_id")).strip()
        lease_token = _safe_str(job.get("lease_token")).strip()
        session_id = _safe_str(job.get("session_id")).strip() or _safe_str(payload.get("session_id")).strip()
        request_id = _safe_str(job.get("request_id")).strip() or _safe_str(payload.get("request_id")).strip()

        request = _load_pending_request(session_id=session_id, request_id=request_id)
        if request:
            job["_resolved_request"] = request
            job["_resolved_session_id"] = session_id
            job["_resolved_request_id"] = request_id
            return job

        if job_id and lease_token:
            fail_image_job(job_id=job_id, lease_token=lease_token, error="stale_request_not_found")

    return {}


def run_one_queued_job(*, lease_seconds: int = 300) -> Dict[str, Any]:
    """Claim the next queued visual job, run canonical processing, then settle queue state."""
    job = _claim_next_live_visual_job(lease_seconds=lease_seconds)
    if not job:
        return {"ok": True, "processed": False, "reason": "no_live_job_available"}

    job_id = _safe_str(job.get("job_id")).strip()
    lease_token = _safe_str(job.get("lease_token")).strip()
    session_id = _safe_str(job.get("_resolved_session_id")).strip()
    request_id = _safe_str(job.get("_resolved_request_id")).strip()
    print("[RPG][visual/run_one]", {"job_id": job_id, "session_id": session_id, "request_id": request_id})

    if not job_id or not lease_token:
        return {"ok": False, "error": "invalid_job_state"}

    try:
        request = _safe_dict(job.get("_resolved_request"))

        request_kind = _safe_str(request.get("kind")).strip() or "scene_illustration"
        request_target_id = _safe_str(request.get("target_id")).strip()
        request_prompt = _safe_str(request.get("prompt")).strip()
        request_style = _safe_str(request.get("style")).strip()
        request_model = _safe_str(request.get("model")).strip() or "default"
        request_seed = request.get("seed")
        request_version = request.get("version")

        existing_status = _safe_str(request.get("status")).strip().lower()
        existing_asset_id = _safe_str(request.get("asset_id")).strip()
        if existing_status == "complete" or existing_asset_id:
            complete_image_job(job_id=job_id, lease_token=lease_token, result={"error": "", "status": "complete"})
            return {
                "ok": True,
                "processed": False,
                "reason": "request_already_completed",
                "session_id": session_id,
                "request_id": request_id,
            }

        # Preview sessions are ephemeral and do not exist in the persisted session store.
        if session_id.startswith("preview_"):
            if not image_generation_enabled():
                complete_image_job(job_id=job_id, lease_token=lease_token, result={"error": "", "status": "complete"})
                return {"ok": False, "processed": False, "error": "image_generation_disabled"}

            result = _generate_preview_image_for_request(
                request=request,
                request_id=request_id,
                session_id=session_id,
            )
            if not _result_ok(result):
                error_text = _result_error(result) or "preview_generation_failed"
                print("[RPG][preview_generation_failed]", {
                    "session_id": session_id,
                    "request_id": request_id,
                    "request": request,
                    "result": _result_to_jsonable(result),
                })
                fail_image_job(job_id=job_id, lease_token=lease_token, error=error_text[:300])
                return {
                    "ok": False,
                    "processed": False,
                    "error": error_text,
                    "provider_result": _result_to_jsonable(result),
                }

            asset_id = _safe_str(_safe_dict(result).get("asset_id")).strip()
            image_path = _result_local_path(result)
            mime_type = _result_mime_type(result) or "image/png"

            # Eliminate duplicate files:
            # - if provider already wrote a file, reuse it
            # - otherwise fall back to saving returned bytes into asset store
            if not image_path or not os.path.isfile(image_path):
                image_bytes, inferred_mime_type = _result_bytes_and_mime(result)
                mime_type = inferred_mime_type or mime_type
                image_path = save_asset_bytes(
                    image_bytes,
                    mime_type=mime_type,
                    asset_id=asset_id,
                    metadata={},
                )

            complete_image_job(job_id=job_id, lease_token=lease_token, result={"error": "", "status": "complete"})

            # Use asset_url from cache if available, otherwise construct from image_path
            asset_url = _safe_str(_safe_dict(result).get("asset_url")).strip()
            if asset_url:
                public_image_url = asset_url
            else:
                public_image_url = _public_generated_image_url(image_path)

            if not asset_id:

                hash_part = os.path.splitext(os.path.basename(image_path))[0].split("_")[-1]

                seed_part = request_seed if isinstance(request_seed, int) else "noseed"

                asset_id = f"{request_kind}:{request_target_id}:{seed_part}:{hash_part}"

            return {
                "ok": True,
                "processed": True,
                "job_id": job_id,
                "session_id": session_id,
                "request_id": request_id,
                "request_status": "complete",
                "asset_id": asset_id,
                "image_url": public_image_url,
                "local_path": image_path,
                "kind": request_kind,
                "target_id": request_target_id,
                "prompt": request_prompt,
                "style": request_style,
                "model": request_model,
                "seed": request_seed if isinstance(request_seed, int) else _result_seed(result),
                "version": request_version,
                "provider_result": _result_to_jsonable(result),
                "note": "preview generation completed successfully",
            }

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

        simulation_state = process_pending_image_requests(simulation_state, limit=1)

        session["simulation_state"] = simulation_state
        save_runtime_session(session)
    except Exception as exc:
        release_visual_job(job_id=job_id, lease_token=lease_token, error=_safe_str(exc).strip()[:500])
        return {
            "ok": False,
            "processed": False,
            "error": _safe_str(exc).strip()[:500] or "run_one_failed",
            "error_type": type(exc).__name__,
        }

    request_record = _find_request(simulation_state, request_id)

    # If request disappeared after processing, treat that as successful completion.
    if not request_record:
        complete_visual_job(job_id=job_id, lease_token=lease_token, error="")
        return {
            "ok": True,
            "processed": True,
            "job_id": job_id,
            "session_id": session_id,
            "request_id": request_id,
            "request_status": "complete",
            "note": "request was cleaned up after successful processing",
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


def _generate_preview_image_for_request(*, request: Dict[str, Any], request_id: str, session_id: str) -> Dict[str, Any]:
    prompt = _safe_str(request.get("prompt")).strip()
    style = _safe_str(request.get("style")).strip()
    seed = request.get("seed")
    target_id = _safe_str(request.get("target_id")).strip()

    payload = {
        "kind": "scene_illustration",
        "prompt": prompt,
        "style": style,
        "seed": seed,
        "session_id": session_id,
        "target_id": target_id,
        "quality": _safe_str(request.get("quality")).strip() or "fast",
        "width": request.get("width"),
        "height": request.get("height"),
        "num_inference_steps": request.get("num_inference_steps"),
    }
    print("[RPG][preview_generate][request]", payload)
    result = generate_rpg_image(payload)
    print("[RPG][preview_generate][result]", _result_to_jsonable(result))
    return result


def run_one_image_job():
    return run_one_queued_job()


__all__ = ["run_one_image_job", "run_one_queued_job"]
