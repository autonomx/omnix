"""Versioned migration layer for durable RPG session payloads."""
from __future__ import annotations

from typing import Any, Dict

from app.rpg.session.legacy_interaction_migration import migrate_legacy_interactions

_CURRENT_SAVE_VERSION = "1.0"
_CURRENT_SCHEMA_VERSION = 5


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 1) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def migrate_session_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate wrapped or direct session payloads to the current schema.

    Durable files use ``{"save_version": ..., "session": {...}}`` while several
    callers pass the session dictionary directly. Both shapes are migrated so a
    legacy on-disk transcript cannot bypass interaction conversion.
    """

    payload = _safe_dict(payload)
    nested = payload.get("session")
    if isinstance(nested, dict):
        payload["session"] = _migrate_session_dict(nested)
    return _migrate_session_dict(payload)


def _migrate_session_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    manifest = _safe_dict(payload.get("manifest"))
    version = _safe_int(manifest.get("schema_version"), 1)

    if not manifest.get("id"):
        manifest["id"] = str(manifest.get("session_id") or "session:unknown")
    if not manifest.get("session_id") and manifest.get("id") != "session:unknown":
        manifest["session_id"] = manifest.get("id")

    simulation_state = _safe_dict(payload.get("simulation_state"))
    simulation_state["presentation_state"] = _safe_dict(
        simulation_state.get("presentation_state")
    )
    simulation_state["memory_state"] = _safe_dict(simulation_state.get("memory_state"))
    payload["simulation_state"] = simulation_state

    runtime_state = _safe_dict(payload.get("runtime_state"))
    if version < 4:
        runtime_state.setdefault("ambient_queue", [])
        runtime_state.setdefault("ambient_seq", 0)
        runtime_state.setdefault("last_idle_tick_at", "")
        runtime_state.setdefault("last_player_turn_at", "")
        runtime_state.setdefault("idle_streak", 0)
        runtime_state.setdefault("ambient_cooldowns", {})
        runtime_state.setdefault("recent_ambient_ids", [])
        runtime_state.setdefault("pending_interrupt", None)
        runtime_state.setdefault("subscription_state", {"last_polled_seq": 0})
        runtime_state.setdefault(
            "ambient_metrics",
            {"emitted": 0, "suppressed": 0, "coalesced": 0},
        )
    payload["runtime_state"] = runtime_state
    payload["manifest"] = manifest

    payload = migrate_legacy_interactions(payload)
    manifest = _safe_dict(payload.get("manifest"))
    manifest["schema_version"] = max(
        _safe_int(manifest.get("schema_version"), version),
        _CURRENT_SCHEMA_VERSION,
    )
    payload["manifest"] = manifest
    return payload
