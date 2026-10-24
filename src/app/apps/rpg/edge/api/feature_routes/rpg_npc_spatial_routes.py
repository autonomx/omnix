"""The world's people through the day: time passing with no player action, and where everyone is (RQ-2.7).

``/spatial-ticks`` lets the world go on for a few ticks: a ``world_tick`` turn through the turn route
(``session/turn/run.py``), so people follow their day (``rules/routines.py``), the clock and the causal pressures move,
and all of it commits with the campaign's revision. ``/spatial-state`` reads where everyone is from the campaign. The
routines are the world's own (``canon.routines``); the older spatial runtime, with its own clock, goals and routines
in tables outside the campaign, is gone (its tables retire by a forward migration after a release).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.edge.api.route_contracts import RpgSpatialStateResponse
from app.apps.rpg.edge.api.web_contracts import documented
from app.apps.rpg.narration.presentation.turn_response import RpgTurnResponse

_ROUTE_SENTINEL = "_omnix_rpg_npc_spatial_routes_registered"
MAX_TICKS = 12  # as time away: the most the world goes on in one turn (session/turn/run.py)


class RpgAdvanceCampaignSpatialTickRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticks: int = Field(default=1, ge=1, le=MAX_TICKS)


def _whereabouts(campaign_id: str) -> dict[str, Any]:
    from app.apps.rpg.foundation.safe_values import safe_dict as _d
    from app.apps.rpg.rules import routines
    from app.apps.rpg.session.service import load_session

    session = load_session(campaign_id)
    if not session:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found"})
    simulation = _d(session.get("simulation_state"))
    world = _d(simulation.get("world_model"))
    people, places = _d(world.get("npcs")), _d(world.get("locations"))
    minute = routines.clock(simulation)
    return {
        "ok": True,
        "campaign_id": campaign_id,
        "revision": int(_d(session.get("runtime_state")).get("state_revision") or 0),
        "absolute_minutes": minute,
        "hero_location_id": routines.hero_location(simulation),
        "present_npc_ids": routines.present_now(simulation)[1],
        "people": [
            {"npc_id": npc_id, "name": str(_d(people.get(npc_id)).get("name") or npc_id),
             "location_id": where.location_id,
             "location_name": str(_d(places.get(where.location_id)).get("name") or where.location_id),
             "activity": where.activity}
            for npc_id, where in routines.whereabouts(simulation, minute).items()
        ],
    }


def register_rpg_npc_spatial_routes(router: APIRouter, state) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.post(
        "/api/rpg/campaigns/{campaign_id}/spatial-ticks",
        responses={200: {"model": RpgTurnResponse, "description": "The world_tick turn's rpg_turn_response_v2 contract."}},
    )
    async def rpg_advance_campaign_spatial_tick(
        campaign_id: str,
        http_request: Request, request_body: RpgAdvanceCampaignSpatialTickRequestBody,
    ) -> Any:
        """The world goes on for ``ticks`` ticks (10 in-game minutes each), as a world_tick turn."""
        from app.apps.rpg.edge.api.turn_pipeline import execute_foreground_rpg_turn

        return await execute_foreground_rpg_turn(
            session_id=campaign_id,
            command="",
            request=http_request,
            action={"turn_kind": "world_tick", "ticks": request_body.ticks},
        )

    @router.get(
        "/api/rpg/campaigns/{campaign_id}/spatial-state",
        responses=documented(RpgSpatialStateResponse),
    )
    def rpg_read_campaign_spatial_state(campaign_id: str) -> dict[str, Any]:
        return _whereabouts(campaign_id)
