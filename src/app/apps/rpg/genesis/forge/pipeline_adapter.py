"""Genesis compiler/bootstrap and World Forge launch pipeline adapter."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, cast

from .bootstrap import bootstrap_session_from_compiled_genesis
from .compiler import compile_campaign_genesis
from .contract import CampaignGenesisContract
from .legacy_adapter import (
    adapt_genesis_payload_to_new_game_payload,
    attach_genesis_to_created_session,
)
from app.apps.rpg.foundation.safe_values import dict_copy as _safe_dict

if TYPE_CHECKING:
    from app.apps.rpg.genesis.contracts import CampaignSessions


class _TruthyZero(int):
    """Preserve explicit seed=0 through legacy truthiness checks."""

    def __new__(cls) -> "_TruthyZero":
        return int.__new__(cls, 0)

    def __bool__(self) -> bool:
        return True


def _preserve_seed_zero(request: Any) -> Any:
    if getattr(request, "seed", None) == 0 and not bool(getattr(request, "seed")):
        object.__setattr__(request, "seed", _TruthyZero())
    return request


def attach_compiled_genesis_to_session(
    result: dict[str, Any],
    compiled: dict[str, Any],
    bootstrap: dict[str, Any],
    *,
    sessions: CampaignSessions,
    compact_save: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    if result.get("ok") is not True:
        return result
    session_id = str(result.get("session_id") or "")
    if not session_id:
        return result
    session = raw_session if isinstance(raw_session := result.get("session"), dict) else None
    if session is None:
        session = sessions.load(session_id)
    if not session:
        return result
    state = _safe_dict(session.get("state"))
    metadata = _safe_dict(state.get("metadata"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    setup_payload = _safe_dict(session.get("setup_payload"))
    manifest = _safe_dict(session.get("manifest"))
    state["active_goals"] = list(bootstrap.get("active_goals") or [])
    state["decision_biases"] = dict(bootstrap.get("decision_biases") or {})
    state["world_traits"] = list(bootstrap.get("world_traits") or [])
    metadata["compiler_version"] = compiled.get("compiler_version")
    state["metadata"] = metadata
    # One copy each, which saving moves out of the document into the campaign's artifacts (RQ-1.1).
    setup_payload["compiled_genesis"] = dict(compiled)
    setup_payload["bootstrap_snapshot"] = dict(bootstrap)
    manifest["compiler_version"] = compiled.get("compiler_version")
    session.update(
        {
            "state": state,
            "setup_payload": setup_payload,
            "runtime_state": runtime_state,
            "manifest": manifest,
        }
    )
    if persist:
        saved = sessions.save(session, compact=compact_save)
    else:
        saved = session
    return {
        **result,
        "session": saved,
        "game": saved.get("state", result.get("game", {})),
    }


def _result_from_unsaved_session(session: dict[str, Any]) -> dict[str, Any]:
    manifest = _safe_dict(session.get("manifest"))
    session_id = str(manifest.get("session_id") or manifest.get("id") or "")
    return {
        "ok": True,
        "session_id": session_id,
        "status": "generating_world",
        "session": session,
        "game": session.get("state", {}),
    }


def _attach_creation_progress(result: dict[str, Any], *, error: str = "") -> dict[str, Any]:
    """The creation's job and progress as the play screen reads them, on the result and its session."""
    session_id = str(result.get("session_id") or "")
    from app.apps.rpg.genesis.creation_progress import (
        attach_creation_metadata,
        build_creation_job,
        build_creation_progress_snapshot,
    )

    status = "completed" if not error and result.get("ok") is True else "failed"
    job = build_creation_job(session_id=session_id, status=cast(Any, status), error=error)
    progress = build_creation_progress_snapshot(session_id=session_id, status=cast(Any, status), error=error)
    session = result.get("session")
    if isinstance(session, dict):
        session = attach_creation_metadata(session, job, progress)
        result = {**result, "session": session, "game": session.get("state", result.get("game", {}))}
    return {**result, "creation_job": job, "creation_progress": progress}


def prepare_new_game_session_from_compiled_genesis(
    *,
    sessions: CampaignSessions,
    bootstrap: dict[str, Any],
    compiled: dict[str, Any],
    contract: CampaignGenesisContract,
    legacy: dict[str, Any],
) -> dict[str, Any]:
    """Build the deterministic blocked shell shared by sync and async launch paths."""

    legacy_request = _preserve_seed_zero(sessions.new_game_request(legacy))
    result = _result_from_unsaved_session(sessions.build_new_game(legacy_request))
    result = attach_genesis_to_created_session(result, contract, persist=False, sessions=sessions)
    return attach_compiled_genesis_to_session(
        result,
        compiled,
        bootstrap,
        persist=False,
        sessions=sessions,
    )


def _launch_in_starter_world(
    *,
    sessions: CampaignSessions,
    bootstrap: dict[str, Any],
    compiled: dict[str, Any],
    contract: CampaignGenesisContract,
    legacy: dict[str, Any],
) -> dict[str, Any]:
    """No World Forge: the wizard's hero sets out in the starter world, from its opening for the chosen starting
    place and hook (roadmap §4.4: every campaign plays from a world), with the genesis the wizard made attached."""
    from app.apps.rpg.genesis.worlds.builtin_worlds import launch_starter

    def with_genesis(session: dict[str, Any]) -> dict[str, Any]:
        built = {"ok": True, "session_id": str(_safe_dict(session.get("manifest")).get("session_id") or ""),
                 "session": session}
        built = attach_genesis_to_created_session(built, contract, persist=False, sessions=sessions)
        return attach_compiled_genesis_to_session(built, compiled, bootstrap, persist=False, sessions=sessions)["session"]

    request = _preserve_seed_zero(sessions.new_game_request(legacy))
    result = launch_starter(request, sessions=sessions, opening_hook=str(contract.story_options.opening_hook or ""),
                            prepare=with_genesis)
    return _attach_creation_progress(result)


def launch_wizard_opening(
    opening: Mapping[str, Any],
    *,
    sessions: CampaignSessions,
    campaign_id: str,
    bootstrap: dict[str, Any],
    compiled: dict[str, Any],
    contract: CampaignGenesisContract,
    legacy: dict[str, Any],
) -> dict[str, Any]:
    """World Forge on: the wizard's hero sets out from an opening of the world made for the campaign (roadmap §4.4,
    ``wizard_world.py``), under the campaign id the wizard gave the player, with the genesis it made attached."""
    from app.apps.rpg.genesis.forge.wizard_world import opening_document
    from app.apps.rpg.genesis.worlds.published_launch import launch_published_scenario

    def with_genesis(session: dict[str, Any]) -> dict[str, Any]:
        built = {"ok": True, "session_id": campaign_id, "session": session}
        built = attach_genesis_to_created_session(built, contract, persist=False, sessions=sessions)
        return attach_compiled_genesis_to_session(built, compiled, bootstrap, persist=False, sessions=sessions)["session"]

    document = opening_document(opening)
    made = _preserve_seed_zero(sessions.new_game_request(legacy)).model_dump(mode="json", exclude={"starting_location"})
    return launch_published_scenario(
        sessions=sessions,
        world_id=str(document["world_id"]),
        world_revision=int(document["world_revision"]),
        world_release=int(document["compatible_release"]),
        scenario_id=str(document["scenario_id"]),
        scenario_revision=int(document["revision"]),
        player=made.get("player"),
        gameplay={key: made.get(key) for key in ("difficulty", "world_activity", "economy_pressure",
                                                 "combat_lethality", "companions_enabled", "permadeath")},
        features=made.get("features"),
        new_game=made,
        prepare=with_genesis,
        session_id=campaign_id,
    )


def create_new_game_session_from_compiled_genesis(
    *,
    sessions: CampaignSessions,
    bootstrap: dict[str, Any],
    compiled: dict[str, Any],
    contract: CampaignGenesisContract,
    legacy: dict[str, Any],
    prepared_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A new game the wizard made, set out at once: in the starter world without World Forge. With World Forge, the
    campaign's world is made in the library by the genesis job (``wizard_world.py``), which needs the durable queue;
    without it there is no world to make, so the request is refused rather than played without one."""
    if not contract.world_forge.enabled:
        return _launch_in_starter_world(sessions=sessions, bootstrap=bootstrap, compiled=compiled, contract=contract,
                                        legacy=legacy)
    return {**dict(prepared_result or {}), "ok": False, "status": "failed",
            "error": "campaign_world_forge_requires_queue",
            "detail": "World Forge makes the campaign's world in the library, which needs the database's job queue."}


def create_new_game_from_genesis_payload(payload: dict[str, Any], *, sessions: CampaignSessions) -> dict[str, Any]:
    raw = _safe_dict(payload.get("request") or payload)
    contract_payload = _safe_dict(raw.get("genesis") or raw)
    if "world_forge" not in contract_payload:
        # Older typed Genesis clients predate World Forge. Preserve their fast,
        # single-save behavior; current wizard clients opt in explicitly.
        contract_payload["world_forge"] = {"enabled": False}
    contract = CampaignGenesisContract.model_validate(contract_payload)
    legacy = adapt_genesis_payload_to_new_game_payload(
        {"request": {"genesis": contract.model_dump(mode="json")}}
    )
    compiled = compile_campaign_genesis(contract)
    bootstrap = bootstrap_session_from_compiled_genesis(compiled)
    prepared = None
    if contract.world_forge.enabled:
        prepared = prepare_new_game_session_from_compiled_genesis(
            bootstrap=bootstrap,
            compiled=compiled,
            contract=contract,
            legacy=legacy,
            sessions=sessions,
        )
        from .async_coordinator import (
            campaign_genesis_async_enabled,
            campaign_genesis_sync_fallback_allowed,
            enqueue_campaign_genesis,
        )

        if campaign_genesis_async_enabled():
            enqueued = enqueue_campaign_genesis(
                prepared,
                contract=contract,
                compiled=compiled,
                bootstrap=bootstrap,
                legacy=legacy,
                sessions=sessions,
            )
            if (
                enqueued.get("error") != "campaign_genesis_enqueue_failed"
                or not campaign_genesis_sync_fallback_allowed()
            ):
                return enqueued
            # Local/portable launches must remain usable when the optional durable
            # PostgreSQL queue is unavailable. Rebuild a clean in-memory shell so
            # queued/failed metadata from the attempted enqueue cannot leak into
            # the synchronous result.
            prepared = prepare_new_game_session_from_compiled_genesis(
                bootstrap=bootstrap,
                compiled=compiled,
                contract=contract,
                legacy=legacy,
                sessions=sessions,
            )
            prepared["campaign_genesis_async_fallback"] = {
                "used": True,
                "reason": str(enqueued.get("detail") or enqueued.get("error") or ""),
            }
    return create_new_game_session_from_compiled_genesis(
        bootstrap=bootstrap,
        compiled=compiled,
        contract=contract,
        legacy=legacy,
        prepared_result=prepared,
        sessions=sessions,
    )
