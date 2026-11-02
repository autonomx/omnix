"""Clean RPG session launch and save-management gateway routes."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import JsonValue, RootModel

from app.config.env import env_str as _env_str

import asyncio
from typing import Any

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from .rpg_campaign_lore_routes import register_rpg_campaign_lore_routes
from .rpg_narrative_delivery_routes import (
    register_rpg_narrative_delivery_routes,
)
from app.apps.rpg.edge.api.turn_pipeline import execute_foreground_rpg_turn
from app.apps.rpg.narration.presentation.turn_response import RpgTurnResponse
from app.apps.rpg.session.ability_coverage import summarize_ability_coverage
from app.apps.rpg.world.environment_narration import build_environment_narration_contract
from app.apps.rpg.world.environment_regions import derive_active_region_snapshot
from app.apps.rpg.genesis.forge.pipeline_adapter import create_new_game_from_genesis_payload
from app.apps.rpg.session.loadout import RpgLoadoutActionRequest
from app.apps.rpg.session.new_game import (
    RpgNewGameRequest,
    RpgRenameSessionRequest,
    continue_rpg_session,
    create_new_game_session,
    delete_rpg_session,
    list_rpg_presets,
    rename_rpg_session,
    start_rpg_preset,
)
from app.apps.rpg.session.service import list_session_summaries, load_session

from pydantic import BaseModel as _TypedRequestBaseModel, ConfigDict as _TypedRequestConfigDict, Field
from typing import Any as _TypedRequestAny
from app.apps.rpg.session.service import SESSION_CAMPAIGN_SESSIONS
from app.apps.rpg.edge.api.web_contracts import (
    documented,
    RpgCampaignImportResponse,
    RpgLaunchResponse,
    RpgLoadoutActionResponse,
    RpgPresetListResponse,
    RpgSavePointsResponse,
    RpgSessionListResponse,
    RpgSessionMutationResponse,
    RpgTurnDraftResponse,
)
from app.apps.rpg.edge.api.route_contracts import (
    TURN_STREAM,
    RpgAbilityCoverageResponse,
    RpgCampaignPackage,
    RpgLocalDialogueFixtureResponse,
)

class _TypedRequestModel(_TypedRequestBaseModel):
    model_config = _TypedRequestConfigDict(extra="allow", populate_by_name=True)

class RpgNewGameRequestBody(RpgNewGameRequest):
    genesis: dict[str, Any] | None = None

class RpgApplyTurnRequestBody(_TypedRequestModel):
    command: str | dict[str, Any] | None = None
    # A card the player clicked (evolution roadmap EV-9): the reading it carries, played with no model call.
    card: dict[str, Any] | None = None
    # A wish for the story the game master's panel offered, confirmed (EV-0): its kind and value.
    preference: dict[str, Any] | None = None
    player_input: str | dict[str, Any] | None = None
    text: str | dict[str, Any] | None = None
    message: str | dict[str, Any] | None = None

class RpgRewindRequestBody(_TypedRequestModel):
    save_point: str | None = Field(default=None, min_length=1, max_length=80)  # none: undo the last turn


class RpgSavePointRequestBody(_TypedRequestModel):
    name: str = Field(min_length=1, max_length=80)


class RpgResumeRequestBody(_TypedRequestModel):
    elapsed_seconds: int = Field(default=0, ge=0, le=31_536_000)


class RpgLocalDialogueFixtureRequestBody(_TypedRequestModel):
    case_id: _TypedRequestAny = None
    run_id: _TypedRequestAny = None
    session_id: _TypedRequestAny = None


_ROUTE_SENTINEL = "_omnix_rpg_session_routes_registered"
_GENESIS_CONTRACT_VERSION = "rpg_genesis_v2"
_LOCAL_DIALOGUE_FIXTURE_HEADER = "x-omnix-rpg-live-smoke"
STREAM_APPEAR_SECONDS = 2.0  # how long a stream route waits for the turn to be taken


class _TruthyZero(int):
    """Preserve explicit seed=0 through legacy truthiness checks."""

    def __new__(cls) -> "_TruthyZero":
        return int.__new__(cls, 0)

    def __bool__(self) -> bool:
        return True


def _raise_for_error(
    payload: dict[str, Any],
    *,
    not_found_errors: set[str] | None = None,
) -> dict[str, Any]:
    if payload.get("ok") is not False:
        return payload
    error = str(payload.get("error") or "rpg_session_error")
    status_code = 404 if error in (not_found_errors or set()) else 400
    raise HTTPException(status_code=status_code, detail=payload)


def _payload_root(payload: dict[str, Any]) -> dict[str, Any]:
    request = payload.get("request")
    return request if isinstance(request, dict) else payload


def _has_genesis_contract(payload: dict[str, Any]) -> bool:
    root = _payload_root(payload)
    genesis = root.get("genesis")
    if isinstance(genesis, dict):
        return True
    return root.get("contract_version") == _GENESIS_CONTRACT_VERSION


def _preserve_seed_zero(request: RpgNewGameRequest) -> RpgNewGameRequest:
    if request.seed == 0 and not bool(request.seed):
        object.__setattr__(request, "seed", _TruthyZero())
    return request


def _create_new_game_from_payload(
    payload: dict[str, Any],
    legacy_request: RpgNewGameRequest | None = None,
) -> dict[str, Any]:
    try:
        if _has_genesis_contract(payload):  # the web client's (``withRpgGenesisContract``)
            created = create_new_game_from_genesis_payload(payload, sessions=SESSION_CAMPAIGN_SESSIONS)
        else:
            request = legacy_request or RpgNewGameRequest.model_validate(payload)
            created = create_new_game_session(_preserve_seed_zero(request))
        if isinstance(created, dict) and created.get("ok") is not False:
            from app.apps.rpg.session.jobs.game_master_job import fill_areas_at_launch

            fill_areas_at_launch(str(created.get("session_id") or ""))  # the start's areas, filled in ahead (EV-10)
        return created
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _ability_coverage_payload(state: dict[str, Any]) -> dict[str, Any]:
    report = summarize_ability_coverage(state)
    return report.model_dump(exclude={"observations"})


def _environment_snapshot_from_state(
    state: dict[str, Any],
) -> dict[str, Any] | None:
    # Campaigns launched from a published world before it had a live environment kept a fixed opening snapshot;
    # their `world.environment` still belongs to the new-game template (the Rusty Flagon Tavern), so keep it.
    legacy_snapshot = state.get("environment_snapshot")
    if (
        isinstance(state.get("published_world"), dict)
        and isinstance(legacy_snapshot, dict)
        and legacy_snapshot.get("schema_version") == "rpg_published_opening_environment_v1"
    ):
        return dict(legacy_snapshot)
    world_value = state.get("world")
    world = world_value if isinstance(world_value, dict) else {}
    environment_value = world.get("environment")
    regions_value = world.get("regions")
    environment = environment_value if isinstance(environment_value, dict) else None
    regions = regions_value if isinstance(regions_value, dict) else None
    if environment is None and regions is None:
        return None
    scene_value = state.get("scene")
    scene = scene_value if isinstance(scene_value, dict) else {}
    context_value = scene.get("environment_context")
    context = context_value if isinstance(context_value, dict) else {}
    return derive_active_region_snapshot(world, context)


def _attach_environment_snapshot_to_session(
    session: dict[str, Any],
) -> dict[str, Any]:
    state = (
        raw_state if isinstance(raw_state := session.get("state"), dict) else None
    )
    if state is None:
        return session
    snapshot = _environment_snapshot_from_state(state)
    if snapshot is not None:
        state["environment_snapshot"] = snapshot
        state["environment_narration_contract"] = (
            build_environment_narration_contract(snapshot)
        )
    return session


def _loadout_as_turn(session_id: str, *, command: str, action: dict[str, Any], prefix: str, title: str,
                     kind: str) -> dict[str, Any]:
    """A loadout action as a structured-action turn through the turn pipeline (RQ-2.4), answered as the loadout
    answers: its event, and the campaign as the turn left it. What the rule refuses is a 409 with its words."""
    import uuid

    from app.apps.rpg.edge.api.payloads.player_view import player_session_view
    from app.apps.rpg.edge.api.turn_pipeline import submit_rpg_turn
    from app.apps.rpg.session.service import load_session

    payload = submit_rpg_turn(session_id=session_id, command=command, submission_id=f"{prefix}:{uuid.uuid4().hex}",
                              source="loadout", action={"turn_kind": "structured_action", **action})
    if payload.get("ok") is False:
        detail = {key: value for key, value in payload.items() if key != "status_code"}
        raise HTTPException(status_code=int(payload.get("status_code") or 400), detail=detail)
    outcome = raw_outcome if isinstance(raw_outcome := payload.get("outcome"), dict) else {}
    answer = raw_action_result if isinstance(raw_action_result := outcome.get("action_result"), dict) else {}
    saved = load_session(session_id)
    return {
        "ok": True,
        "session_id": session_id,
        "status": "ready",
        "event": {"title": title, "detail": str(answer.get("detail") or ""), "kind": kind},
        "session": player_session_view(saved),
        "game": saved.get("state", {}),
    }


_PACK_VERBS = {"use": "use", "equip": "equip", "drop": "drop", "unequip": "take off"}


def _loadout_turn(session_id: str, request: Any) -> dict[str, Any]:
    """The play screen's loadout action as its turn: a pack action (the item rule's), an ability used (the ability
    rule's, in a fight or not), one learned (a level's choice), or a hotbar slot set or cleared."""
    action = request.action
    if action in _PACK_VERBS:
        if not request.item_name:
            raise HTTPException(status_code=422, detail={"ok": False, "error": "item_name_required"})
        return _loadout_as_turn(
            session_id, command=f"I {_PACK_VERBS[action]} the {request.item_name}.", prefix="loadout",
            action={"type": "loadout", "action": action, "item_name": request.item_name},
            title=f"{action.title()} {request.item_name}", kind="inventory")
    ability = str(request.ability_id or request.ability_name or "")
    if action in {"use_ability", "hotbar"}:
        ability = ability or str(request.hotbar_slot if request.hotbar_slot is not None else "")
        name = str(request.ability_name or ability)
        return _loadout_as_turn(
            session_id, command=f"I use {name or ability}.", prefix="ability",
            action={"type": "ability", "ability": ability, "target": str(request.target or "")},
            title=f"Use {name or ability}", kind="ability")
    name = str(request.ability_name or ability)
    if action == "unlock_ability":
        return _loadout_as_turn(
            session_id, command=f"I learn {name}.", prefix="learn", action={"type": "learn", "ability": ability},
            title=f"Learn {name}", kind="ability_progression")
    slot = str(request.hotbar_slot if request.hotbar_slot is not None else "")
    cleared = action == "remove_hotbar"
    if not cleared and not ability:
        raise HTTPException(status_code=422, detail={"ok": False, "error": "ability_required",
                                                     "message": "Name the ability to put on the hotbar."})
    return _loadout_as_turn(
        session_id, command=f"Hotbar slot {slot}: {'empty' if cleared else name}.", prefix="hotbar",
        action={"type": "hotbar", "slot": slot, "ability": "" if cleared else ability},
        title=f"Hotbar slot {slot}", kind="ability_progression")


def _session_or_404(session_id: str) -> dict[str, Any]:
    from app.apps.rpg.session.service import load_session

    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found"})
    return session


def _save_points(session_id: str) -> list[dict[str, Any]]:
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    _session_or_404(session_id)
    with unit_of_work() as work:
        points = work.rpg.save_points(current_tenant(), session_id)
        work.rollback()
    return points


def _create_save_point(session_id: str, name: str) -> dict[str, Any]:
    """A save point (rewind.md): at most 20 a campaign, none in hardcore."""
    from app.apps.rpg.rules.combat.stakes import is_hardcore
    from app.apps.rpg.session.turn.rewind import MAX_SAVE_POINTS
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    session = _session_or_404(session_id)
    if is_hardcore(session.get("simulation_state") or {}):
        raise HTTPException(status_code=409, detail={"ok": False, "error": "save_points_hardcore",
                                                     "message": "There is no going back in a hardcore campaign."})
    points = _save_points(session_id)
    if len(points) >= MAX_SAVE_POINTS and name not in {point["name"] for point in points}:
        raise HTTPException(status_code=409, detail={"ok": False, "error": "save_points_full",
                                                     "message": f"A campaign keeps at most {MAX_SAVE_POINTS} save points."})
    with unit_of_work() as work:
        point = work.rpg.put_save_point(current_tenant(), campaign_id=session_id, name=name)
        work.commit()
    return {"ok": True, "session_id": session_id, "save_point": point, "save_points": _save_points(session_id)}


def _with_environment_snapshot(
    payload: dict[str, Any],
) -> dict[str, Any]:
    session = (
        raw_session if isinstance(raw_session := payload.get("session"), dict) else None
    )
    state = (
        session.get("state")
        if session and isinstance(session.get("state"), dict)
        else None
    )
    if state is None and isinstance(payload.get("game"), dict):
        state = payload["game"]
    if state is None:
        return payload
    snapshot = _environment_snapshot_from_state(state)
    if snapshot is None:
        return payload
    contract = build_environment_narration_contract(snapshot)
    state["environment_snapshot"] = snapshot
    state["environment_narration_contract"] = contract
    payload["environment_snapshot"] = snapshot
    payload["environment_narration_contract"] = contract
    payload["game"] = state
    return payload


def _with_ability_coverage(
    payload: dict[str, Any],
) -> dict[str, Any]:
    session = (
        raw_session if isinstance(raw_session := payload.get("session"), dict) else None
    )
    if not session:
        return payload
    state = (
        raw_state if isinstance(raw_state := session.get("state"), dict) else None
    )
    if not state:
        return payload
    coverage = _ability_coverage_payload(state)
    mechanics = (
        raw_mechanics if isinstance(raw_mechanics := state.get("mechanics"), dict) else {}
    )
    mechanics["ability_coverage_latest"] = coverage
    state["mechanics"] = mechanics
    payload["ability_coverage"] = coverage
    payload["game"] = state
    return payload


def _with_rpg_response_surface(
    payload: dict[str, Any],
) -> dict[str, Any]:
    from app.apps.rpg.edge.api.payloads.player_view import with_player_session_view

    # The campaign leaves the server as its player may see it (no world secrets, no private canon).
    return with_player_session_view(_with_ability_coverage(
        _with_environment_snapshot(payload)
    ))


def _foreground_turn_command(payload: Any) -> str:
    if isinstance(payload, dict):
        value = (
            payload.get("command")
            or payload.get("player_input")
            or payload.get("text")
            or payload.get("message")
        )
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(
        status_code=400,
        detail={"ok": False, "error": "missing_command"},
    )


def _require_local_dialogue_fixture_request(request: Request) -> None:
    client_host = str(request.client.host if request.client else "").strip().casefold()
    loopback_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}
    if client_host not in loopback_hosts:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    if str(_env_str("CI") or "").strip().casefold() in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    if request.headers.get(_LOCAL_DIALOGUE_FIXTURE_HEADER) != "1":
        raise HTTPException(
            status_code=403,
            detail={"ok": False, "error": "local_dialogue_fixture_opt_in_required"},
        )


class RpgCampaignImportBody(RootModel[dict[str, JsonValue]]):
    """A campaign's save package, as ``/export`` wrote it; ``import_campaign`` checks what it holds."""


def register_rpg_session_routes(router: APIRouter, state) -> None:
    """Attach the typed RPG session API once."""
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)
    register_rpg_campaign_lore_routes(router, state)
    register_rpg_narrative_delivery_routes(router, state)

    @router.get("/api/rpg/presets", tags=["rpg-session"], responses=documented(RpgPresetListResponse))
    def rpg_presets() -> dict[str, Any]:
        return list_rpg_presets()

    @router.post("/api/rpg/presets/{preset_id}/start", tags=["rpg-session"], responses=documented(RpgLaunchResponse))
    def rpg_start_preset(preset_id: str) -> dict[str, Any]:
        return _with_rpg_response_surface(
            _raise_for_error(
                start_rpg_preset(preset_id),
                not_found_errors={"unknown_rpg_preset"},
            )
        )

    @router.get("/api/rpg/sessions", tags=["rpg-session"], responses=documented(RpgSessionListResponse))
    def rpg_sessions(
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        sessions = [
            _attach_environment_snapshot_to_session(session)
            for session in (list_session_summaries(limit=limit) or [])
        ]
        return {"ok": True, "sessions": sessions}

    @router.get("/api/rpg/sessions/{session_id}", tags=["rpg-session"], responses=documented(RpgLaunchResponse))
    def rpg_read_session(session_id: str) -> dict[str, Any]:
        session = load_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "error": "session_not_found",
                    "session_id": session_id,
                },
            )
        from app.apps.rpg.session.turn.narration_timing import with_narrations

        session = dict(with_narrations(session))  # turns narrated after their commit read theirs from the table
        return _with_rpg_response_surface(
            {
                "ok": True,
                "session_id": session_id,
                "session": session,
                "game": session.get("state", {}),
            }
        )

    @router.get(
        "/api/rpg/sessions/{session_id}/ability-coverage",
        tags=["rpg-session"],
        responses=documented(RpgAbilityCoverageResponse),
    )
    def rpg_ability_coverage(session_id: str) -> dict[str, Any]:
        session = load_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "error": "session_not_found",
                    "session_id": session_id,
                },
            )
        state = (
            raw_state if isinstance(raw_state := session.get("state"), dict) else {}
        )
        return {
            "ok": True,
            "session_id": session_id,
            "ability_coverage": _ability_coverage_payload(state),
        }

    @router.post("/api/rpg/new-game", tags=["rpg-session"], responses=documented(RpgLaunchResponse))
    async def rpg_new_game(
        http_request: Request, request_body: RpgNewGameRequestBody,
    ) -> dict[str, Any]:
        raw_payload = request_body.model_dump(exclude_unset=True, by_alias=True)
        request = RpgNewGameRequest.model_validate(raw_payload)
        return await asyncio.to_thread(
            lambda: _with_rpg_response_surface(
                _create_new_game_from_payload(raw_payload, request)
            )
        )

    @router.post(
        "/api/rpg/sessions/{session_id}/continue",
        tags=["rpg-session"],
        responses=documented(RpgLaunchResponse),
    )
    def rpg_continue_session(session_id: str) -> dict[str, Any]:
        return _with_rpg_response_surface(
            _raise_for_error(
                continue_rpg_session(session_id),
                not_found_errors={"session_not_found"},
            )
        )

    @router.post(
        "/api/rpg/sessions/{session_id}/turn",
        tags=["rpg-session"],
        responses={200: {"model": RpgTurnResponse, "description": "The turn's rpg_turn_response_v2 contract."}},
    )
    async def rpg_apply_turn(
        session_id: str,
        http_request: Request, request_body: RpgApplyTurnRequestBody,
    ) -> Any:
        raw_payload = request_body.model_dump(exclude_unset=True, by_alias=True)
        card = raw_payload.pop("card", None)
        preference = raw_payload.pop("preference", None)
        command = _foreground_turn_command(raw_payload)
        if isinstance(preference, dict) and preference:
            return await execute_foreground_rpg_turn(
                session_id=session_id, command=command, request=http_request,
                action={"turn_kind": "structured_action", "type": "preference",
                        "kind": str(preference.get("kind") or ""), "value": str(preference.get("value") or "")})
        if isinstance(card, dict) and card:
            return await execute_foreground_rpg_turn(
                session_id=session_id, command=command, request=http_request,
                action={"turn_kind": "structured_action", "type": "card", "card": card})
        return await execute_foreground_rpg_turn(
            session_id=session_id,
            command=command,
            request=http_request,
        )

    @router.post(
        "/api/rpg/sessions/{session_id}/resume",
        tags=["rpg-session"],
        responses={200: {"model": RpgTurnResponse, "description": "The world_tick turn's rpg_turn_response_v2 contract."}},
    )
    async def rpg_resume_session(
        session_id: str,
        http_request: Request, request_body: RpgResumeRequestBody,
    ) -> Any:
        """The player returns after time away: the world moves on, as a world_tick turn with a recap (RQ-2.7)."""
        return await execute_foreground_rpg_turn(
            session_id=session_id,
            command="",
            request=http_request,
            action={"turn_kind": "world_tick", "elapsed_seconds": request_body.elapsed_seconds},
        )

    @router.post(
        "/api/rpg/sessions/{session_id}/rewind",
        tags=["rpg-session"],
        responses={200: {"model": RpgTurnResponse, "description": "The rewind turn's rpg_turn_response_v2 contract."}},
    )
    async def rpg_rewind_session(
        session_id: str,
        http_request: Request, request_body: RpgRewindRequestBody,
    ) -> Any:
        """Undo the last turn, or return to a save point, as a new revision (rewind.md)."""
        name = (request_body.save_point or "").strip()
        return await execute_foreground_rpg_turn(
            session_id=session_id,
            command=f"I return to {name}." if name else "I undo my last turn.",
            request=http_request,
            action={"turn_kind": "structured_action", "type": "rewind", "save_point": name},
        )

    @router.get("/api/rpg/sessions/{session_id}/save-points", tags=["rpg-session"],
                responses=documented(RpgSavePointsResponse))
    def rpg_list_save_points(session_id: str) -> dict[str, Any]:
        return {"ok": True, "session_id": session_id, "save_points": _save_points(session_id)}

    @router.post("/api/rpg/sessions/{session_id}/save-points", tags=["rpg-session"],
                 responses=documented(RpgSavePointsResponse))
    def rpg_create_save_point(session_id: str, request_body: RpgSavePointRequestBody) -> dict[str, Any]:
        """Name this moment a save point: the campaign's current state, pinned (no turn, no change to the game)."""
        return _create_save_point(session_id, request_body.name.strip())

    @router.delete("/api/rpg/sessions/{session_id}/save-points/{name}", tags=["rpg-session"],
                   responses=documented(RpgSavePointsResponse))
    def rpg_delete_save_point(session_id: str, name: str) -> dict[str, Any]:
        from app.persistence.unit_of_work import unit_of_work
        from app.runtime.tenant_context import current_tenant

        _session_or_404(session_id)
        with unit_of_work() as work:
            deleted = work.rpg.delete_save_point(current_tenant(), campaign_id=session_id, name=name)
            work.commit()
        if not deleted:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "save_point_not_found"})
        return {"ok": True, "session_id": session_id, "save_points": _save_points(session_id)}

    @router.get(
        "/api/rpg/sessions/{session_id}/turn-draft",
        tags=["rpg-session"],
        responses=documented(RpgTurnDraftResponse),
    )
    def rpg_turn_draft(session_id: str, submission_id: str = Query(min_length=1, max_length=200)) -> dict[str, Any]:
        """The narration so far of the caller's own turn in progress, named by its submission id."""
        from app.apps.rpg.narration.narration_drafts import read_narration_draft

        return read_narration_draft(session_id, submission_id)

    @router.get(
        "/api/rpg/sessions/{session_id}/submissions/{submission_id}/stream",
        tags=["rpg-session"],
        include_in_schema=False,
        responses=TURN_STREAM,
    )
    def rpg_turn_stream(session_id: str, submission_id: str, request: Request,
                        after: int | None = Query(default=None, ge=-1)) -> StreamingResponse:
        """The caller's own turn as it happens (RQ-6.2, roadmap §4.7): ``accepted``, ``committed``, ``outcome``,
        ``narration.delta``, ``narration.final`` or ``error``; ``Last-Event-ID`` (or ``after``) resumes."""
        from app.apps.rpg.foundation import turn_stream

        header = str(request.headers.get("last-event-id") or "").strip()
        try:
            cursor = int(header) if header else int(after if after is not None else -1)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"ok": False, "error": "invalid_turn_stream_cursor"}) from exc
        key = turn_stream.stream_key(session_id, submission_id)
        if key is None:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "turn_stream_not_found"})

        def frames():
            import json
            import time

            deadline = time.monotonic() + STREAM_APPEAR_SECONDS
            while not turn_stream.has_stream(key) and time.monotonic() < deadline:
                time.sleep(0.05)
            if not turn_stream.has_stream(key):
                # Another process took the turn, or its stream has expired: the campaign holds what happened.
                yield "event: error\ndata: " + json.dumps({"error": "turn_stream_not_found"}) + "\n\n"
                return
            for index, name, data in turn_stream.events(key, cursor):
                yield f"id: {index}\nevent: {name}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"

        return StreamingResponse(frames(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @router.post(
        "/api/rpg/local-qualification/dialogue-fixture",
        tags=["rpg-session"],
        responses=documented(RpgLocalDialogueFixtureResponse),
    )
    async def rpg_local_dialogue_fixture(http_request: Request, request_body: RpgLocalDialogueFixtureRequestBody) -> dict[str, Any]:
        _require_local_dialogue_fixture_request(http_request)
        payload = request_body.model_dump(exclude_unset=True, by_alias=True)
        from app.apps.rpg.edge.local_dialogue_quality_fixtures import (
            dialogue_benchmark_case,
            provision_local_dialogue_fixture,
        )

        try:
            case = dialogue_benchmark_case(str(payload.get("case_id") or ""))
            return await asyncio.to_thread(
                lambda: provision_local_dialogue_fixture(
                    case=case,
                    run_id=str(payload.get("run_id") or ""),
                    session_id=str(payload.get("session_id") or "").strip() or None,
                )
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"ok": False, "error": str(exc)},
            ) from exc

    @router.post(
        "/api/rpg/sessions/{session_id}/rename",
        tags=["rpg-session"],
        responses=documented(RpgSessionMutationResponse),
    )
    def rpg_rename_session(
        session_id: str,
        request: RpgRenameSessionRequest,
    ) -> dict[str, Any]:
        name = request.name.strip()
        if not name:
            raise HTTPException(
                status_code=400,
                detail={
                    "ok": False,
                    "error": "missing_session_name",
                    "session_id": session_id,
                },
            )
        return _raise_for_error(
            rename_rpg_session(session_id, name),
            not_found_errors={"session_not_found"},
        )

    @router.post(
        "/api/rpg/sessions/{session_id}/delete",
        tags=["rpg-session"],
        responses=documented(RpgSessionMutationResponse),
    )
    def rpg_delete_session(session_id: str) -> dict[str, Any]:
        return _raise_for_error(
            delete_rpg_session(session_id),
            not_found_errors={"session_not_found"},
        )

    @router.get(
        "/api/rpg/sessions/{session_id}/export",
        tags=["rpg-session"],
        responses=documented(RpgCampaignPackage),
    )
    def rpg_export_session(session_id: str) -> JSONResponse:
        from app.apps.rpg.session.persistence.campaign_transfer import export_campaign

        try:
            package = export_campaign(session_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail={"ok": False, "error": "session_not_found", "session_id": session_id},
            ) from exc
        title = str(dict(dict(package.get("campaign") or {}).get("document") or {}).get("manifest", {}).get("title")
                    or session_id)
        filename = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in title).strip() or "campaign"
        return JSONResponse(package, headers={
            "Content-Disposition": f'attachment; filename="{filename}.omnix-campaign.json"',
        })

    @router.post(
        "/api/rpg/sessions/import",
        tags=["rpg-session"],
        responses=documented(RpgCampaignImportResponse),
    )
    def rpg_import_session(package: RpgCampaignImportBody) -> dict[str, Any]:
        from app.apps.rpg.session.persistence.campaign_transfer import CampaignTransferRefused, import_campaign

        try:
            return import_campaign(package.root)
        except CampaignTransferRefused as exc:
            code, _, subject = str(exc).partition(":")
            message = {
                "rpg_campaign_already_in_library": "This campaign is already in your library.",
                "rpg_campaign_world_not_installed": "Its world is not installed here: import the world first.",
                "rpg_campaign_world_not_adopted": "Its world was made elsewhere: adopt it in the world library first.",
                "rpg_campaign_package_without_campaign": "This file holds no campaign.",
            }.get(code, "This campaign could not be imported.")
            raise HTTPException(
                status_code=409, detail={"ok": False, "error": code, "subject": subject, "message": message},
            ) from exc
        except ValueError as exc:  # not a save package this Omnix reads
            raise HTTPException(status_code=422, detail={
                "ok": False, "error": "rpg_campaign_package_invalid", "message": "This file is not an Omnix campaign.",
            }) from exc

    @router.post(
        "/api/rpg/sessions/{session_id}/loadout-action",
        tags=["rpg-session"],
        responses=documented(RpgLoadoutActionResponse),
    )
    def rpg_loadout_action(
        session_id: str,
        request: RpgLoadoutActionRequest,
    ) -> dict[str, Any]:
        return _with_environment_snapshot(_loadout_turn(session_id, request))
