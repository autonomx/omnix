"""FastAPI Router for the Creator UX v1 — Adventure Builder API.

Provides structured endpoints for template browsing, adventure setup
validation, rich preview, and launching adventures through the
``AdventureSetup`` → ``GameLoop`` pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.rpg.ai.world_scene_narrator import play_scene as narrate_scene
from app.rpg.services import adventure_builder_service as builder

logger = logging.getLogger(__name__)

creator_bp = APIRouter()


async def _read_json_body(request: Request) -> dict[str, Any] | None:
    try:
        payload = await request.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _json_response(payload: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status_code)


# ---------------------------------------------------------------------------
# 1. GET /api/rpg/adventure/templates
# ---------------------------------------------------------------------------

@creator_bp.get("/api/rpg/adventure/templates")
async def list_adventure_templates():
    """Return available adventure setup templates."""
    try:
        templates = builder.get_templates()
        return {"success": True, "templates": templates}
    except Exception:
        logger.exception("Failed to list templates")
        return JSONResponse({"success": False, "error": "Failed to list templates"}, status_code=500)


# ---------------------------------------------------------------------------
# 2. POST /api/rpg/adventure/template
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/template", methods=["POST"])
async def build_adventure_template(request: Request):
    """Build a full editable setup payload from a named template."""
    data = await _read_json_body(request) or {}
    template_name = data.get("template_name", "")

    if not template_name:
        return _json_response({"success": False, "error": "template_name is required"}, status_code=400)

    try:
        result = builder.build_template_payload(template_name)
        if not result.get("success"):
            return _json_response(result, status_code=404)
        return _json_response(result)
    except ValueError:
        return _json_response({"success": False, "error": f"Unknown template: {template_name}"}, status_code=404)
    except Exception:
        logger.exception("Failed to build template")
        return _json_response({"success": False, "error": "Failed to build template"}, status_code=500)


# ---------------------------------------------------------------------------
# 3. POST /api/rpg/adventure/validate
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/validate", methods=["POST"])
async def validate_adventure_setup(request: Request):
    """Validate a raw adventure setup payload."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Request body is required"}, status_code=400)

    try:
        result = builder.validate_setup(data)
        return _json_response(result)
    except Exception:
        logger.exception("Failed to validate setup")
        return _json_response({"success": False, "error": "Failed to validate setup"}, status_code=500)


# ---------------------------------------------------------------------------
# 4. POST /api/rpg/adventure/preview
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/preview", methods=["POST"])
async def preview_adventure_setup(request: Request):
    """Normalize, validate, and preview an adventure setup."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Request body is required"}, status_code=400)

    try:
        result = builder.preview_setup(data)
        return _json_response(result)
    except Exception:
        logger.exception("Failed to preview setup")
        return _json_response({"success": False, "error": "Failed to preview setup"}, status_code=500)


# ---------------------------------------------------------------------------
# 5. POST /api/rpg/adventure/start
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/start", methods=["POST"])
async def start_adventure(request: Request):
    """Create a brand-new adventure using the structured creator pipeline."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Request body is required"}, status_code=400)

    try:
        result = builder.start_adventure(data)
        status = 201 if result.get("success") else 400
        return _json_response(result, status_code=status)
    except Exception:
        logger.exception("Failed to start adventure")
        return _json_response({"success": False, "error": "Failed to start adventure"}, status_code=500)


# ---------------------------------------------------------------------------
# 6. POST /api/rpg/adventure/regenerate
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/regenerate", methods=["POST"])
async def regenerate_adventure_section(request: Request):
    """Regenerate a single section of the adventure setup.

    Supports ``mode: "preview"`` (diff without applying) and
    ``mode: "apply"`` (apply the regeneration, optionally with merge strategy).
    """
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    target = data.get("target")
    payload = data.get("setup") or {}
    mode = data.get("mode", "apply")
    apply_token = data.get("apply_token")
    apply_strategy = data.get("apply_strategy", "replace")
    tone = data.get("tone")
    constraints = data.get("constraints")

    if not target:
        return _json_response({"success": False, "error": "Missing regeneration target"}, status_code=400)

    try:
        result = builder.regenerate_setup_section(
            payload,
            target,
            mode=mode,
            apply_token=apply_token,
            apply_strategy=apply_strategy,
            tone=tone,
            constraints=constraints,
        )
        status = 200 if result.get("success") else 400
        return _json_response(result, status_code=status)
    except Exception:
        logger.exception("Failed to regenerate setup section")
        return _json_response({"success": False, "error": "Failed to regenerate setup section"}, status_code=500)


# ---------------------------------------------------------------------------
# 7. POST /api/rpg/adventure/regenerate-item
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/regenerate-item", methods=["POST"])
async def regenerate_adventure_item(request: Request):
    """Regenerate a single entity within a section of the adventure setup."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    target = data.get("target")
    item_id = data.get("item_id")
    payload = data.get("setup") or {}

    if not target:
        return _json_response({"success": False, "error": "Missing regeneration target"}, status_code=400)
    if not item_id:
        return _json_response({"success": False, "error": "Missing item_id"}, status_code=400)

    try:
        result = builder.regenerate_single_item(payload, target, item_id)
        status = 200 if result.get("success") else 400
        return _json_response(result, status_code=status)
    except Exception:
        logger.exception("Failed to regenerate single item")
        return _json_response({"success": False, "error": "Failed to regenerate single item"}, status_code=500)


# ---------------------------------------------------------------------------
# 8. POST /api/rpg/adventure/regenerate-multiple  (Phase 1.5)
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/regenerate-multiple", methods=["POST"])
async def regenerate_multiple_items(request: Request):
    """Regenerate multiple entities within a section of the adventure setup."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    target = data.get("target")
    item_ids = data.get("item_ids") or []
    payload = data.get("setup") or {}

    if not target:
        return _json_response({"success": False, "error": "Missing regeneration target"}, status_code=400)

    try:
        result = builder.regenerate_multiple_items_service(payload, target, item_ids)
        status = 200 if result.get("success") else 400
        return _json_response(result, status_code=status)
    except Exception:
        logger.exception("Failed to regenerate multiple items")
        return _json_response({"success": False, "error": "Failed to regenerate multiple items"}, status_code=500)


# ---------------------------------------------------------------------------
# 9. POST /api/rpg/adventure/inspect-world  (Phase 2)
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/inspect-world", methods=["POST"])
async def inspect_world(request: Request):
    """Compute the world graph, simulation summary, and entity inspector."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    payload = data.get("setup") or data
    try:
        result = builder.inspect_world(payload)
        return _json_response(result)
    except Exception:
        logger.exception("Failed to inspect world")
        return _json_response({"success": False, "error": "Failed to inspect world"}, status_code=500)


# ---------------------------------------------------------------------------
# 10. POST /api/rpg/adventure/inspect-world-snapshot  (Phase 2.5)
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/inspect-world-snapshot", methods=["POST"])
async def inspect_world_snapshot(request: Request):
    """Build a full snapshot wrapper around the world inspection result."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    payload = data.get("setup") or data
    label = data.get("label")
    try:
        result = builder.inspect_world_snapshot(payload, label=label)
        return _json_response(result)
    except Exception:
        logger.exception("Failed to build world snapshot")
        return _json_response({"success": False, "error": "Failed to build world snapshot"}, status_code=500)


# ---------------------------------------------------------------------------
# 11. POST /api/rpg/adventure/compare-world  (Phase 2.5)
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/compare-world", methods=["POST"])
async def compare_world(request: Request):
    """Compare two setup payloads and return a graph diff."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    before_setup = data.get("before_setup")
    after_setup = data.get("after_setup")
    if not before_setup or not after_setup:
        return _json_response({"success": False, "error": "Both before_setup and after_setup are required"}, status_code=400)

    try:
        result = builder.compare_world(before_setup, after_setup)
        return _json_response(result)
    except Exception:
        logger.exception("Failed to compare world snapshots")
        return _json_response({"success": False, "error": "Failed to compare world snapshots"}, status_code=500)


# ---------------------------------------------------------------------------
# 12. POST /api/rpg/adventure/compare-entity  (Phase 2.5)
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/compare-entity", methods=["POST"])
async def compare_entity(request: Request):
    """Compare a specific entity between two setup payloads."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    before_setup = data.get("before_setup")
    after_setup = data.get("after_setup")
    entity_id = data.get("entity_id")

    if not before_setup or not after_setup:
        return _json_response({"success": False, "error": "Both before_setup and after_setup are required"}, status_code=400)
    if not entity_id:
        return _json_response({"success": False, "error": "entity_id is required"}, status_code=400)

    try:
        result = builder.compare_world_entity(before_setup, after_setup, entity_id)
        return _json_response(result)
    except Exception:
        logger.exception("Failed to compare entity")
        return _json_response({"success": False, "error": "Failed to compare entity"}, status_code=500)


# ---------------------------------------------------------------------------
# 13. POST /api/rpg/adventure/simulate-step  (Phase 3A)
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/simulate-step", methods=["POST"])
async def simulate_step(request: Request):
    """Advance the world simulation by one tick."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    payload = data.get("setup") or data
    try:
        result = builder.advance_world_simulation(payload)
        return _json_response(result)
    except Exception:
        logger.exception("Failed to advance simulation step")
        return _json_response({"success": False, "error": "Failed to advance simulation step"}, status_code=500)


# ---------------------------------------------------------------------------
# 14. POST /api/rpg/adventure/simulation-state  (Phase 3A)
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/simulation-state", methods=["POST"])
async def simulation_state(request: Request):
    """Return the current simulation state (or initialise it)."""
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    payload = data.get("setup") or data
    try:
        result = builder.get_simulation_state(payload)
        return _json_response(result)
    except Exception:
        logger.exception("Failed to get simulation state")
        return _json_response({"success": False, "error": "Failed to get simulation state"}, status_code=500)


# ---------------------------------------------------------------------------
# 15. POST /api/rpg/adventure/simulation/action  (Phase 4.5)
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/adventure/simulation/action", methods=["POST"])
async def simulation_action(request: Request):
    """Apply a player action to the simulation and advance one tick.

    Request body:
        setup (dict, required): Current adventure setup payload
        action (dict, required): { "type": "...", "target_id": "..." }
    """
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    setup = data.get("setup")
    action = data.get("action")
    if not setup or not action:
        return _json_response({"success": False, "error": "Both 'setup' and 'action' are required"}, status_code=400)

    try:
        result = builder.apply_player_action_endpoint({"setup": setup, "action": action})
        return _json_response(result)
    except Exception:
        logger.exception("Failed to apply player action")
        return _json_response({"success": False, "error": "Failed to apply player action"}, status_code=500)


# ---------------------------------------------------------------------------
# 16. POST /api/rpg/scene/play  (Phase 5)
# ---------------------------------------------------------------------------

@creator_bp.api_route("/api/rpg/scene/play", methods=["POST"])
async def play_scene(request: Request):
    """Play a scene and return narrated result with NPC reactions.

    Request body:
        scene (dict, required): Scene to play
        state (dict, optional): Current game state
        tone (str, optional): Narrative tone (default: 'dramatic')

    Returns narrated scene with choices, NPC dialogue, and reactions.
    """
    data = await _read_json_body(request)
    if not data:
        return _json_response({"success": False, "error": "Missing JSON body"}, status_code=400)

    scene = data.get("scene")
    if not scene:
        return _json_response({"success": False, "error": "Missing 'scene' in request body"}, status_code=400)

    state = data.get("state") or {}
    tone = data.get("tone", "dramatic")

    try:
        result = narrate_scene(scene, state, tone=tone)
        return _json_response({"success": True, **result})
    except Exception:
        logger.exception("Failed to play scene")
        return _json_response({"success": False, "error": "Failed to play scene"}, status_code=500)
