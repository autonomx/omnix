"""Typed router for legacy RPG browser compatibility paths."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import RootModel

from .compat.rpg_adventure_compat import (
    adventure_simulation_state_payload,
    compare_adventure_entity_payload,
    compare_adventure_world_payload,
    inspect_adventure_world_payload,
    inspect_adventure_world_snapshot_payload,
    list_adventure_templates_payload,
    preview_adventure_payload,
    simulate_adventure_step_payload,
    validate_adventure_payload,
)
from .compat.rpg_inspection_compat import (
    inspect_npc_reasoning_payload,
    inspect_tick_diff_payload,
    inspect_timeline_payload,
    inspect_timeline_tick_payload,
    inspect_world_events_payload,
)
from .compat.rpg_player_compat import (
    player_codex_payload,
    player_encounter_payload,
    player_journal_payload,
    player_objectives_payload,
    player_state_payload,
)
from .compat.rpg_session_compat import list_rpg_sessions_payload
from .compat.rpg_session_genesis_compat import get_rpg_session_payload


class RpgCompatibilityRequest(RootModel[dict[str, Any]]):
    """Preserve legacy object payloads while publishing an explicit schema."""


def create_rpg_compatibility_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/rpg/adventure/templates", tags=["rpg-adventure-compat"])
    def rpg_adventure_templates() -> dict[str, Any]:
        return list_adventure_templates_payload()

    @router.post("/api/rpg/adventure/validate", tags=["rpg-adventure-compat"])
    def rpg_adventure_validate(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return validate_adventure_payload(request.root)

    @router.post("/api/rpg/adventure/preview", tags=["rpg-adventure-compat"])
    def rpg_adventure_preview(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return preview_adventure_payload(request.root)

    @router.post("/api/rpg/adventure/inspect-world", tags=["rpg-adventure-compat"])
    def rpg_adventure_inspect_world(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return inspect_adventure_world_payload(request.root)

    @router.post("/api/rpg/adventure/inspect-world-snapshot", tags=["rpg-adventure-compat"])
    def rpg_adventure_inspect_world_snapshot(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return inspect_adventure_world_snapshot_payload(request.root)

    @router.post("/api/rpg/adventure/compare-world", tags=["rpg-adventure-compat"])
    def rpg_adventure_compare_world(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return compare_adventure_world_payload(request.root)

    @router.post("/api/rpg/adventure/compare-entity", tags=["rpg-adventure-compat"])
    def rpg_adventure_compare_entity(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return compare_adventure_entity_payload(request.root)

    @router.post("/api/rpg/adventure/simulate-step", tags=["rpg-adventure-compat"])
    def rpg_adventure_simulate_step(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return simulate_adventure_step_payload(request.root)

    @router.post("/api/rpg/adventure/simulation-state", tags=["rpg-adventure-compat"])
    def rpg_adventure_simulation_state(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return adventure_simulation_state_payload(request.root)

    @router.post("/api/rpg/session/list", tags=["rpg-session-compat"])
    def rpg_session_list() -> dict[str, Any]:
        return list_rpg_sessions_payload()

    @router.post("/api/rpg/session/get", tags=["rpg-session-compat"])
    def rpg_session_get(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return get_rpg_session_payload(request.root)

    @router.post("/api/rpg/inspect/timeline", tags=["rpg-inspection-compat"])
    def rpg_inspect_timeline(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return inspect_timeline_payload(request.root)

    @router.post("/api/rpg/inspect/timeline_tick", tags=["rpg-inspection-compat"])
    def rpg_inspect_timeline_tick(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return inspect_timeline_tick_payload(request.root)

    @router.post("/api/rpg/inspect/tick_diff", tags=["rpg-inspection-compat"])
    def rpg_inspect_tick_diff(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return inspect_tick_diff_payload(request.root)

    @router.post("/api/rpg/inspect/npc_reasoning", tags=["rpg-inspection-compat"])
    def rpg_inspect_npc_reasoning(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return inspect_npc_reasoning_payload(request.root)

    @router.post("/api/rpg/inspect/world_events", tags=["rpg-inspection-compat"])
    def rpg_inspect_world_events(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return inspect_world_events_payload(request.root)

    @router.post("/api/rpg/player/state", tags=["rpg-player-compat"])
    def rpg_player_state(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return player_state_payload(request.root)

    @router.post("/api/rpg/player/journal", tags=["rpg-player-compat"])
    def rpg_player_journal(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return player_journal_payload(request.root)

    @router.post("/api/rpg/player/codex", tags=["rpg-player-compat"])
    def rpg_player_codex(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return player_codex_payload(request.root)

    @router.post("/api/rpg/player/objectives", tags=["rpg-player-compat"])
    def rpg_player_objectives(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return player_objectives_payload(request.root)

    @router.post("/api/rpg/player/encounter", tags=["rpg-player-compat"])
    def rpg_player_encounter(request: RpgCompatibilityRequest) -> dict[str, Any]:
        return player_encounter_payload(request.root)

    return router
