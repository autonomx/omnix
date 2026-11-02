"""Tactical moves and attacks on a campaign's map: structured-action turns through the one turn pipeline (RQ-2.6).

A grid command is a turn like any other (``session/turn/tactical.py``): the campaign revision the player last saw is
its only token, a refused command takes no turn, and the response names the hero's cell and the map's revision.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel as _TypedRequestBaseModel, ConfigDict as _TypedRequestConfigDict, Field as _typed_field

from app.apps.rpg.edge.api.route_contracts import RpgTacticalResponse
from app.apps.rpg.edge.api.web_contracts import documented


class _TypedRequestModel(_TypedRequestBaseModel):
    model_config = _TypedRequestConfigDict(extra="allow", populate_by_name=True)


class RpgTacticalMoveRequestBody(_TypedRequestModel):
    submission_id: str = _typed_field(min_length=1)
    command_id: str = _typed_field(min_length=1)
    actor_id: str = _typed_field(min_length=1)
    destination: tuple[int, int]
    expected_campaign_revision: int = _typed_field(ge=0)
    # Accepted as the play screen sends it; the campaign revision is the only token (turns change the map).
    expected_map_state_revision: int | None = _typed_field(default=None, ge=0)


class RpgTacticalAttackRequestBody(_TypedRequestModel):
    submission_id: str = _typed_field(min_length=1)
    command_id: str = _typed_field(min_length=1)
    actor_id: str = _typed_field(min_length=1)
    target_id: str = _typed_field(min_length=1)
    action_type: Literal["melee_attack", "ranged_attack", "unarmed_attack"] = "melee_attack"
    expected_campaign_revision: int = _typed_field(ge=0)
    expected_map_state_revision: int | None = _typed_field(default=None, ge=0)


_ROUTE_SENTINEL = "_omnix_rpg_tactical_spatial_routes_registered"


def _campaign_of(map_instance_id: str) -> str:
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    with unit_of_work() as work:
        instance = work.map_instances.get_instance(current_tenant(), map_instance_id)
        work.rollback()
    if instance is None:
        raise HTTPException(status_code=404, detail={"ok": False, "error": f"map_instance_not_found:{map_instance_id}"})
    return str(instance["campaign_id"])


def _grid_turn(map_instance_id: str, *, actor_id: str, submission_id: str, command: str,
               action: dict[str, Any]) -> dict[str, Any]:
    from app.apps.rpg.edge.api.turn_pipeline import submit_rpg_turn
    from app.apps.rpg.session.turn.tactical import hero_on_map

    campaign_id = _campaign_of(map_instance_id)
    if actor_id != hero_on_map(campaign_id):
        raise HTTPException(status_code=409, detail={"ok": False, "error": "tactical_actor_not_current"})
    payload = submit_rpg_turn(session_id=campaign_id, command=command, submission_id=submission_id,
                              source="tactical_grid",
                              action={"turn_kind": "structured_action", "map_instance_id": map_instance_id, **action})
    if payload.get("ok") is False:
        from app.apps.rpg.edge.api.stale_view import stale_refusal

        detail = stale_refusal(campaign_id, {key: value for key, value in payload.items() if key != "status_code"})
        raise HTTPException(status_code=int(payload.get("status_code") or 409), detail=detail)
    outcome = raw_outcome if isinstance(raw_outcome := payload.get("outcome"), dict) else {}
    answer = raw_action_result if isinstance(raw_action_result := outcome.get("action_result"), dict) else {}
    return {
        "ok": True,
        "kind": action["type"],
        "campaign_id": campaign_id,
        "map_instance_id": map_instance_id,
        "map_state_revision": int(answer.get("map_state_revision") or 0),
        "actor_id": actor_id,
        "tactical": dict(answer.get("tactical") or {}),
        "idempotent_replay": payload.get("idempotent_replay") is True,
        "campaign_revision": int(outcome.get("revision") or 0),
        **{key: answer[key] for key in ("actor_cell", "map_event_id", "target_id") if key in answer},
        **({"turn_id": str(payload["turn_id"])} if payload.get("turn_id") else {}),
    }


def register_rpg_tactical_spatial_routes(router: APIRouter, state) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.post(
        "/api/rpg/map-instances/{map_instance_id}/tactical/move",
        tags=["rpg-tactical-spatial"],
        responses=documented(RpgTacticalResponse),
    )
    def rpg_tactical_move(map_instance_id: str, request: Request,
                          request_body: RpgTacticalMoveRequestBody) -> dict[str, Any]:
        x, y = request_body.destination
        return _grid_turn(map_instance_id, actor_id=request_body.actor_id, submission_id=request_body.submission_id,
                          command=f"I move to ({x}, {y}) on the map.",
                          action={"type": "tactical_move", "destination": [x, y], "command_id": request_body.command_id,
                                  "expected_campaign_revision": request_body.expected_campaign_revision})

    @router.post(
        "/api/rpg/map-instances/{map_instance_id}/tactical/attack",
        tags=["rpg-tactical-spatial"],
        responses=documented(RpgTacticalResponse),
    )
    def rpg_tactical_attack(map_instance_id: str, request: Request,
                            request_body: RpgTacticalAttackRequestBody) -> dict[str, Any]:
        return _grid_turn(map_instance_id, actor_id=request_body.actor_id, submission_id=request_body.submission_id,
                          command=f"I attack {request_body.target_id} on the map.",
                          action={"type": "tactical_attack", "target_id": request_body.target_id,
                                  "attack": request_body.action_type, "command_id": request_body.command_id,
                                  "expected_campaign_revision": request_body.expected_campaign_revision})
