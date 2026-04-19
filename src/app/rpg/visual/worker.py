"""Phase 12.10 — Worker executor for pending image requests."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from app.rpg.presentation.visual_state import (
    append_scene_illustration,
    append_visual_asset,
    build_visual_asset_record,
    ensure_visual_state,
    get_pending_image_requests,
    update_image_request,
    upsert_character_visual_identity,
)
from app.rpg.visual.asset_store import save_asset_bytes
from app.rpg.visual.providers import get_image_provider, image_generation_enabled


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _complete_character_portrait(
    simulation_state: Dict[str, Any],
    *,
    request: Dict[str, Any],
    asset_id: str,
    image_path: str,
    status: str,
) -> Dict[str, Any]:
    """Write completed portrait result back to character visual identity."""
    target_id = _safe_str(request.get("target_id")).strip()
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    identities = _safe_dict(visual_state.get("character_visual_identities"))
    identity = _safe_dict(identities.get(target_id))

    identity["portrait_url"] = image_path
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
    image_path: str,
    status: str,
) -> Dict[str, Any]:
    """Write completed scene illustration result back to visual state."""
    return append_scene_illustration(
        simulation_state,
        {
            "scene_id": _safe_str(request.get("target_id")).strip(),
            "event_id": _safe_str(request.get("request_id")).strip(),
            "title": _safe_str(request.get("target_id")).strip(),
            "image_url": image_path,
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
    provider = get_image_provider()
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

        result = provider.generate(
            prompt=_safe_str(request.get("prompt")).strip(),
            seed=request.get("seed") if isinstance(request.get("seed"), int) else None,
            style=_safe_str(request.get("style")).strip(),
            model=_safe_str(request.get("model")).strip(),
            kind=_safe_str(request.get("kind")).strip(),
            target_id=_safe_str(request.get("target_id")).strip(),
        )

        if not result.ok:
            moderation_status = _safe_str(result.moderation_status).strip()
            # Blocked/ moderated content: immediately terminal, no retry
            is_moderation_terminal = moderation_status == "blocked"

            # Retryable errors: network issues, HTTP 5xx, rate limits
            error_text = _safe_str(result.error).strip().lower()
            is_retryable = not is_moderation_terminal and not any(
                tag in error_text
                for tag in ("invalid", "rejected", "unauthorized", "not_implemented", "no_api_key", "missing_runtime")
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

        final_prompt = _safe_str(result.revised_prompt).strip() or _safe_str(request.get("prompt")).strip()

        asset_id = f"{_safe_str(request.get('kind')).strip()}:{_safe_str(request.get('target_id')).strip()}:{version}:{request.get('seed')}"
        image_path = save_asset_bytes(
            result.image_bytes or b"",
            mime_type=result.mime_type,
            asset_id=asset_id,
            kind=_safe_str(request.get("kind")).strip(),
            target_id=_safe_str(request.get("target_id")).strip(),
        )

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
                url=image_path,
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
                image_path=image_path,
                status="complete",
            )
        else:
            scene_request = dict(request)
            scene_request["prompt"] = final_prompt
            simulation_state = _complete_scene_illustration(
                simulation_state,
                request=scene_request,
                asset_id=asset_id,
                image_path=image_path,
                status="complete",
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