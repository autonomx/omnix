"""Phase 12.10 — Worker executor for pending image requests."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app.rpg.presentation.visual_state import (
    append_scene_illustration,
    append_visual_asset,
    build_visual_asset_record,
    ensure_visual_state,
    get_pending_image_requests,
    mark_image_request_complete,
    update_image_request,
    upsert_character_visual_identity,
)
from app.rpg.visual.asset_store import save_asset_bytes
from app.rpg.visual.global_image_adapter import generate_rpg_image
from app.rpg.visual.providers import image_generation_enabled
from app.runtime_paths import generated_images_root
from app.shared import DATA_DIR


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


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


def _complete_character_portrait(
    simulation_state: Dict[str, Any],
    *,
    request: Dict[str, Any],
    asset_id: str,
    image_url: str,
    local_path: str,
    status: str,
) -> Dict[str, Any]:
    """Write completed portrait result back to character visual identity."""
    target_id = _safe_str(request.get("target_id")).strip()
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    identities = _safe_dict(visual_state.get("character_visual_identities"))
    identity = _safe_dict(identities.get(target_id))

    identity["portrait_url"] = image_url
    identity["portrait_local_path"] = local_path
    identity["portrait_asset_id"] = asset_id
    identity["status"] = status

    return upsert_character_visual_identity(
        simulation_state,
        actor_id=target_id,
        identity=identity,
    )


def _complete_scene_illustration(
    simulation_state: Dict[str, Any],
    *,
    request: Dict[str, Any],
    asset_id: str,
    image_url: str,
    local_path: str,
    status: str,
) -> Dict[str, Any]:
    """Write completed scene illustration result back to visual state."""
    return append_scene_illustration(
        simulation_state,
        {
            "scene_id": _safe_str(request.get("target_id")).strip(),
            "event_id": _safe_str(request.get("request_id")).strip(),
            "title": _safe_str(request.get("target_id")).strip(),
            "image_url": image_url,
            "local_path": local_path,
            "asset_id": asset_id,
            "seed": request.get("seed"),
            "style": _safe_str(request.get("style")).strip(),
            "prompt": _safe_str(request.get("prompt")).strip(),
            "model": _safe_str(request.get("model")).strip(),
            "status": status,
        },
    )


def process_pending_image_requests(
    simulation_state: Dict[str, Any],
    *,
    limit: int = 8,
) -> Dict[str, Any]:
    """Process pending image requests through the configured provider."""
    simulation_state = ensure_visual_state(_safe_dict(simulation_state))
    if not image_generation_enabled():
        return simulation_state
    pending = get_pending_image_requests(simulation_state)[: max(1, int(limit))]

    for request in pending:
        request_id = _safe_str(request.get("request_id")).strip()
        attempts = request.get("attempts") if isinstance(request.get("attempts"), int) else 0
        max_attempts = request.get("max_attempts") if isinstance(request.get("max_attempts"), int) else 3
        current_status = _safe_str(request.get("status")).strip()
        now = _now_iso()

        # Skip already-terminal requests
        if current_status in {"complete", "failed", "blocked"}:
            continue

        # Requests already at or beyond max_attempts must not call the provider again.
        if attempts >= max_attempts:
            simulation_state = update_image_request(
                simulation_state,
                request_id=request_id,
                patch={
                    "status": "failed",
                    "attempts": attempts,
                    "error": _safe_str(request.get("error")).strip(),
                    "updated_at": now,
                    "completed_at": now,
                },
            )
            if _safe_str(request.get("kind")).strip() == "scene_illustration":
                simulation_state = _complete_scene_illustration(
                    simulation_state, request=request, asset_id="", image_path="", status="failed"
                )
            continue

        # Bump attempt count
        simulation_state = update_image_request(
            simulation_state,
            request_id=request_id,
            patch={
                "attempts": attempts + 1,
                "updated_at": now,
            },
        )

        payload = {
            "provider": _safe_str(request.get("provider")).strip(),
            "prompt": _safe_str(request.get("prompt")).strip(),
            "seed": request.get("seed") if isinstance(request.get("seed"), int) else None,
            "style": _safe_str(request.get("style")).strip(),
            "model": _safe_str(request.get("model")).strip(),
            "kind": _safe_str(request.get("kind")).strip(),
            "target_id": _safe_str(request.get("target_id")).strip(),
            "request_id": _safe_str(request.get("request_id")).strip(),
            "session_id": _safe_str(request.get("session_id")).strip(),
            "metadata": {
                "source": "rpg_worker"
            },
        }
        result = generate_rpg_image(payload)

        if not result.ok:
            moderation_status = _safe_str(result.moderation_status).strip()
            # Blocked/ moderated content: immediately terminal, no retry
            is_moderation_terminal = moderation_status == "blocked"

            # Retryable errors: network issues, HTTP 5xx, rate limits
            error_text = _safe_str(result.error).strip().lower()
            NON_RETRYABLE_ERRORS = [
                "flux_klein_missing_runtime",
                "flux_klein_load_failed",
                "missing_runtime",
                "invalid_request",
                "unsupported_model",
                "invalid",
                "rejected",
                "unauthorized",
                "not_implemented",
                "no_api_key"
            ]
            is_retryable = not is_moderation_terminal and not any(
                tag in error_text
                for tag in NON_RETRYABLE_ERRORS
            )

            new_attempts = int(request.get("attempts") or 0) + 1

            if is_moderation_terminal:
                # Moderation-blocked: immediately terminal
                simulation_state = update_image_request(
                    simulation_state,
                    request_id=request_id,
                    patch={
                        "status": "blocked",
                        "attempts": new_attempts,
                        "error": _safe_str(result.error).strip(),
                        "updated_at": now,
                        "completed_at": now,
                    },
                )
                # Record scene completion only for moderated block
                if _safe_str(request.get("kind")).strip() == "scene_illustration":
                    simulation_state = _complete_scene_illustration(
                        simulation_state,
                        request=request,
                        asset_id="",
                        image_path="",
                        status="blocked",
                    )
                continue

            if new_attempts >= max_attempts:
                # Exhausted retries → terminal failure
                simulation_state = update_image_request(
                    simulation_state,
                    request_id=request_id,
                    patch={
                        "status": "failed",
                        "attempts": new_attempts,
                        "error": _safe_str(result.error).strip(),
                        "updated_at": now,
                        "completed_at": now,
                    },
                )
                # Only complete scene on final exhaustion
                if _safe_str(request.get("kind")).strip() == "scene_illustration":
                    simulation_state = _complete_scene_illustration(
                        simulation_state,
                        request=request,
                        asset_id="",
                        image_path="",
                        status="failed",
                    )
            else:
                # Still have retries left — stay pending
                simulation_state = update_image_request(
                    simulation_state,
                    request_id=request_id,
                    patch={
                        "status": "pending",
                        "attempts": new_attempts,
                        "error": _safe_str(result.error).strip(),
                        "updated_at": now,
                    },
                )
            continue

        # Derive version from current identity if present (Part 15)
        version = 1
        if _safe_str(request.get("kind")).strip() == "character_portrait":
            presentation_state = _safe_dict(simulation_state.get("presentation_state"))
            visual_state = _safe_dict(presentation_state.get("visual_state"))
            identities = _safe_dict(visual_state.get("character_visual_identities"))
            identity = _safe_dict(identities.get(_safe_str(request.get("target_id")).strip()))
            if isinstance(identity.get("version"), int) and identity.get("version") > 0:
                version = identity.get("version")

        final_prompt = _safe_str(getattr(result, "revised_prompt", "")).strip() or _safe_str(request.get("prompt")).strip()
        image_bytes, mime_type = _result_bytes_and_mime(result)
        asset_id = f"{_safe_str(request.get('kind')).strip()}:{_safe_str(request.get('target_id')).strip()}:{version}:{request.get('seed')}"

        # Use asset_url from cache if available, otherwise save bytes and construct URL
        asset_url = _safe_str(getattr(result, "asset_url", "")).strip()
        if asset_url:
            public_image_url = asset_url
            # Save bytes for local_path reference, but URL already points to cached file
            image_path = save_asset_bytes(
                image_bytes,
                mime_type=mime_type,
                asset_id=asset_id,
                kind=_safe_str(request.get("kind")).strip(),
                target_id=_safe_str(request.get("target_id")).strip(),
            )
        else:
            image_path = save_asset_bytes(
                image_bytes,
                mime_type=mime_type,
                asset_id=asset_id,
                kind=_safe_str(request.get("kind")).strip(),
                target_id=_safe_str(request.get("target_id")).strip(),
            )
            public_image_url = _public_generated_image_url(image_path)

        # Register the asset
        simulation_state = append_visual_asset(
            simulation_state,
            build_visual_asset_record(
                kind=_safe_str(request.get("kind")).strip(),
                target_id=_safe_str(request.get("target_id")).strip(),
                version=version,
                seed=request.get("seed") if isinstance(request.get("seed"), int) else None,
                style=_safe_str(request.get("style")).strip(),
                model=_safe_str(request.get("model")).strip(),
                prompt=final_prompt,
                url=public_image_url,
                local_path=image_path,
                status="complete",
                created_from_request_id=request_id,
                moderation_status=result.moderation_status,
                moderation_reason=result.moderation_reason,
            ),
        )

        # Complete the appropriate target
        if _safe_str(request.get("kind")).strip() == "character_portrait":
            simulation_state = _complete_character_portrait(
                simulation_state,
                request=request,
                asset_id=asset_id,
                image_url=public_image_url,
                local_path=image_path,
                status="complete",
            )
        else:
            scene_request = dict(request)
            scene_request["prompt"] = final_prompt
            simulation_state = _complete_scene_illustration(
                simulation_state,
                request=scene_request,
                asset_id=asset_id,
                image_url=public_image_url,
                local_path=image_path,
                status="complete",
            )

        simulation_state = mark_image_request_complete(
            simulation_state,
            request_id=request_id,
            asset_id=asset_id,
            image_url=public_image_url,
            local_path=image_path,
        )

        # Mark request complete
        simulation_state = update_image_request(
            simulation_state,
            request_id=request_id,
            patch={
                "status": "complete",
                "error": "",
                "updated_at": now,
                "completed_at": now,
            },
        )

    return simulation_state