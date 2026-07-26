"""Adventure Builder setup, preview, inspection, and simulation routes.

Generated world lore is owned exclusively by the durable World Library and World Forge
APIs. The obsolete Adventure Builder generated-package endpoints are intentionally not
registered here.
"""
from __future__ import annotations

import traceback
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services.adventure_builder_service import (
    build_adventure_preview,
    build_template_payload,
    compare_world,
    compute_creator_health,
    get_templates,
    inspect_world,
    inspect_world_snapshot,
    preview_setup,
    regenerate_multiple_items_service,
    regenerate_setup_section,
    regenerate_single_item,
    start_adventure,
    validate_setup,
)

rpg_adventure_bp = APIRouter()


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


@rpg_adventure_bp.get("/api/rpg/adventure/templates")
async def adventure_templates():
    try:
        return {"success": True, "templates": get_templates()}
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": str(exc), "trace": traceback.format_exc()},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/template")
async def adventure_template(request: Request):
    try:
        data = await request.json()
        template_name = data.get("template_name", "")
        if not template_name:
            return JSONResponse(
                {"success": False, "error": "Missing template_name"}, status_code=400
            )
        return build_template_payload(template_name)
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": str(exc), "trace": traceback.format_exc()},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/validate")
async def adventure_validate(request: Request):
    try:
        result = validate_setup(await request.json())
        validation = _safe_dict(result.get("validation"))
        return {
            "ok": not validation.get("blocking", False),
            "validation": validation,
            "errors": [
                issue
                for issue in _safe_list(validation.get("issues"))
                if isinstance(issue, dict) and issue.get("severity") == "error"
            ],
            "warnings": _safe_list(result.get("warnings")),
            "notices": _safe_list(result.get("notices")),
            "semantic_scores": _safe_dict(result.get("semantic_scores")),
        }
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": str(exc), "trace": traceback.format_exc()},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/preview")
async def adventure_preview(request: Request):
    try:
        data = await request.json()
        setup = data.get("setup") if isinstance(data, dict) else None
        setup = setup if isinstance(setup, dict) else data
        result = preview_setup(setup)
        if "adventure_preview" not in result:
            result["adventure_preview"] = _safe_dict(build_adventure_preview(setup))
        return result
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": str(exc), "trace": traceback.format_exc()},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/start")
async def adventure_start(request: Request):
    try:
        return start_adventure(await request.json())
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": str(exc), "trace": traceback.format_exc()},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/regenerate")
async def adventure_regenerate(request: Request):
    try:
        data = await request.json()
        target = data.get("target", "")
        if not target:
            return JSONResponse(
                {"success": False, "error": "Missing target"}, status_code=400
            )
        return regenerate_setup_section(
            payload=data.get("setup", {}),
            target=target,
            mode=data.get("mode", "apply"),
            apply_token=data.get("apply_token"),
            apply_strategy=data.get("apply_strategy", "replace"),
            tone=data.get("tone"),
            constraints=data.get("constraints"),
        )
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": str(exc), "trace": traceback.format_exc()},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/regenerate-item")
async def adventure_regenerate_item(request: Request):
    try:
        data = await request.json()
        target = data.get("target", "")
        item_id = data.get("item_id", "")
        if not target or not item_id:
            return JSONResponse(
                {"success": False, "error": "Missing target or item_id"},
                status_code=400,
            )
        return regenerate_single_item(
            payload=data.get("setup", {}), target=target, item_id=item_id
        )
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@rpg_adventure_bp.post("/api/rpg/adventure/regenerate-multiple")
async def adventure_regenerate_multiple(request: Request):
    try:
        data = await request.json()
        target = data.get("target", "")
        item_ids = data.get("item_ids", [])
        if not target or not item_ids:
            return JSONResponse(
                {"success": False, "error": "Missing target or item_ids"},
                status_code=400,
            )
        return regenerate_multiple_items_service(
            payload=data.get("setup", {}), target=target, item_ids=item_ids
        )
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@rpg_adventure_bp.post("/api/rpg/adventure/inspect-world")
async def adventure_inspect_world(request: Request):
    try:
        data = await request.json()
        return inspect_world(data.get("setup", {}))
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@rpg_adventure_bp.post("/api/rpg/adventure/inspect-world-snapshot")
async def adventure_inspect_world_snapshot(request: Request):
    try:
        data = await request.json()
        return inspect_world_snapshot(data.get("setup", {}), label=data.get("label"))
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@rpg_adventure_bp.post("/api/rpg/adventure/compare-world")
async def adventure_compare_world(request: Request):
    try:
        data = await request.json()
        return compare_world(data.get("before_setup", {}), data.get("after_setup", {}))
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@rpg_adventure_bp.post("/api/rpg/adventure/compare-entity")
async def adventure_compare_entity(request: Request):
    try:
        data = await request.json()
        entity_id = data.get("entity_id", "")
        if not entity_id:
            return JSONResponse(
                {"success": False, "error": "Missing entity_id"}, status_code=400
            )
        from ..creator.world_snapshot import build_world_snapshot, compute_entity_diff

        before = build_world_snapshot(dict(data.get("before_setup") or {}), label="Before")
        after = build_world_snapshot(dict(data.get("after_setup") or {}), label="After")
        return {
            "success": True,
            "entity_id": entity_id,
            "diff": compute_entity_diff(
                before.get("inspector", {}), after.get("inspector", {}), entity_id
            ),
        }
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@rpg_adventure_bp.post("/api/rpg/adventure/simulate-step")
async def adventure_simulate_step(request: Request):
    try:
        data = await request.json()
        setup = data.get("setup", {})
        tick = setup.get("simulation_tick", 0) + 1
        setup["simulation_tick"] = tick
        return {
            "success": True,
            "tick": tick,
            "setup": setup,
            "health": compute_creator_health(setup),
        }
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@rpg_adventure_bp.post("/api/rpg/adventure/simulation-state")
async def adventure_simulation_state(request: Request):
    try:
        data = await request.json()
        setup = data.get("setup", {})
        return {
            "success": True,
            "tick": setup.get("simulation_tick", 0),
            "setup": setup,
            "health": compute_creator_health(setup),
        }
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)
