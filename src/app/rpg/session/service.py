"""Phase 15.3 — Canonical session service."""
from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.core.determinism import rng_seed_from_session_id
from app.rpg.map_package_bridge import attach_map_state_to_package, restore_map_state_from_package
from app.rpg.map_persistence import ensure_session_map_state
from app.rpg.session.ambient_builder import (
    ensure_ambient_runtime_state,
    normalize_ambient_state,
)
from app.rpg.session.durable_store import (
    archive_session_on_disk,
    list_sessions_from_disk,
    load_session_from_disk,
    save_session_to_disk,
)
from app.rpg.session.environment import ensure_session_environment_seed_state
from app.rpg.session.list_summaries import list_session_summaries_from_disk
from app.rpg.session.migrations import migrate_session_payload
from app.rpg.session.package_bridge import package_to_session, session_to_package
from app.rpg.session.published_opening_progress import (
    ensure_published_opening_progress,
)
from app.rpg.session.survival_persistence import normalize_session_survival_for_persistence
from app.rpg.validation.integrity import (
    assert_package_integrity,
    assert_session_integrity,
    validate_session_integrity,
)
from app.rpg.performance_trace import rpg_pipeline_span_if_active


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def create_or_normalize_session(session: Dict[str, Any]) -> Dict[str, Any]:
    session = _safe_dict(session)
    session = migrate_session_payload(session)
    manifest = _safe_dict(session.get("manifest"))
    session["manifest"] = manifest
    session.setdefault("installed_packs", [])
    session.setdefault("simulation_state", {})
    simulation_state = dict(_safe_dict(session.get("simulation_state")))
    rng_seed = simulation_state.get("rng_seed")
    if (
        not isinstance(rng_seed, int)
        or isinstance(rng_seed, bool)
        or not 0 <= rng_seed < 2**64
    ):
        manifest = _safe_dict(session.get("manifest"))
        session_id = str(
            session.get("session_id")
            or session.get("id")
            or manifest.get("session_id")
            or manifest.get("id")
            or ""
        )
        rng_seed = rng_seed_from_session_id(session_id)
        simulation_state["rng_seed"] = rng_seed
    session["simulation_state"] = simulation_state
    session = ensure_session_environment_seed_state(session)
    session = normalize_session_survival_for_persistence(session)
    session = ensure_session_map_state(session)
    # Living-world: ensure ambient runtime state exists and is bounded
    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_state = ensure_ambient_runtime_state(runtime_state)
    runtime_state = normalize_ambient_state(runtime_state)
    session["runtime_state"] = runtime_state
    return ensure_published_opening_progress(session)


def save_session(session: Dict[str, Any], *, compact: bool = False) -> Dict[str, Any]:
    manifest = _safe_dict(_safe_dict(session).get("manifest"))
    session_id = str(
        manifest.get("session_id")
        or manifest.get("id")
        or _safe_dict(session).get("session_id")
        or _safe_dict(session).get("id")
        or ""
    )
    with rpg_pipeline_span_if_active(
        "session.save_total",
        fields={"session_id": session_id, "compact": compact},
    ) as span:
        saved = _save_session(session, compact=compact)
        if span is not None:
            saved_manifest = _safe_dict(saved.get("manifest"))
            runtime_state = _safe_dict(saved.get("runtime_state"))
            span["session_id"] = str(
                saved_manifest.get("session_id")
                or saved_manifest.get("id")
                or session_id
            )
            span["interaction_seq"] = runtime_state.get("interaction_seq")
            span["state_revision"] = runtime_state.get("state_revision")
        return saved


def _save_session(session: Dict[str, Any], *, compact: bool = False) -> Dict[str, Any]:
    session = _safe_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    session_id = str(
        session.get("session_id")
        or session.get("id")
        or manifest.get("session_id")
        or manifest.get("id")
        or ""
    )
    if session_id:
        previous = load_session_from_disk(session_id)
        if previous is not None:
            previous_state = _safe_dict(previous.get("simulation_state"))
            previous_seed = previous_state.get("rng_seed")
            if (
                not isinstance(previous_seed, int)
                or isinstance(previous_seed, bool)
                or not 0 <= previous_seed < 2**64
            ):
                previous_seed = rng_seed_from_session_id(session_id)
            simulation_state = dict(_safe_dict(session.get("simulation_state")))
            submitted_seed = simulation_state.get("rng_seed")
            if (
                isinstance(submitted_seed, int)
                and not isinstance(submitted_seed, bool)
                and submitted_seed != previous_seed
            ):
                raise ValueError("RPG session rng_seed is immutable")
            simulation_state["rng_seed"] = previous_seed
            session["simulation_state"] = simulation_state
    session = create_or_normalize_session(session)
    assert_session_integrity(session)
    return save_session_to_disk(session, compact=compact)


def load_session(session_id: str) -> Dict[str, Any]:
    with rpg_pipeline_span_if_active(
        "session.load_total",
        fields={"session_id": session_id},
    ) as span:
        session = _load_session(session_id)
        if not isinstance(session, dict):
            return session
        from .interaction_event_store import load_and_replay_interaction_events

        session = load_and_replay_interaction_events(session_id, session)
        from .interaction_lifecycle import recover_pending_interaction_narration

        try:
            recovered = recover_pending_interaction_narration(session_id, session)
        except Exception as exc:
            from app.rpg.debug_logging import log_rpg_event

            log_rpg_event(
                "turn.stage.degraded",
                category="performance",
                level="warning",
                session_id=session_id,
                fields={
                    "metric": "rpg_turn_stage_degraded",
                    "stage": "interaction_narration_recovery",
                    "degraded_stage_count": 1,
                    "error_type": type(exc).__name__,
                },
                error=exc,
            )
        else:
            if span is not None:
                span["pending_narration_recovered"] = recovered
        if span is not None:
            manifest = _safe_dict(session.get("manifest"))
            runtime_state = _safe_dict(session.get("runtime_state"))
            span["session_id"] = str(
                manifest.get("session_id")
                or manifest.get("id")
                or session_id
            )
            span["interaction_seq"] = runtime_state.get("interaction_seq")
            span["state_revision"] = runtime_state.get("state_revision")
        return session


def _load_session(session_id: str) -> Dict[str, Any]:
    session = load_session_from_disk(session_id)
    if session is None:
        return None
    # Fix #2: soft validation on load — allow recovery / migration of older sessions
    session = create_or_normalize_session(session)
    validate_session_integrity(session)  # log but don't fail
    return session


def list_sessions() -> List[Dict[str, Any]]:
    sessions = list_sessions_from_disk()
    out = []
    for item in sessions:
        item = create_or_normalize_session(item)
        # Fix #3: attach integrity info instead of hiding invalid sessions
        integrity = validate_session_integrity(item)
        item["_integrity"] = integrity
        out.append(item)
    return out


def list_session_summaries(*, limit: int | None = None) -> List[Dict[str, Any]]:
    """Return bounded session list rows without normalizing full payloads."""

    with rpg_pipeline_span_if_active(
        "session.list_summaries_total",
        fields={"operation": "list_session_summaries"},
    ) as span:
        out = _list_session_summaries(limit=limit)
        if span is not None:
            span["result_count"] = len(out)
        return out


def _list_session_summaries(*, limit: int | None = None) -> List[Dict[str, Any]]:
    out = []
    for item in list_session_summaries_from_disk(limit=limit):
        integrity = validate_session_integrity(item)
        item["_integrity"] = integrity
        out.append(item)
    return out


def archive_session(session_id: str) -> Dict[str, Any]:
    return archive_session_on_disk(session_id)


def export_session_as_package(session: Dict[str, Any]) -> Dict[str, Any]:
    session = create_or_normalize_session(session)
    assert_session_integrity(session)
    package = session_to_package(session)
    return attach_map_state_to_package(package, session)


def import_session_from_package(package_payload: Dict[str, Any]) -> Dict[str, Any]:
    assert_package_integrity(package_payload)
    result = package_to_session(package_payload)
    if not result.get("ok"):
        return result
    session = restore_map_state_from_package(_safe_dict(result.get("session")), package_payload)
    session = create_or_normalize_session(session)
    assert_session_integrity(session)
    return {"ok": True, "session": session}
