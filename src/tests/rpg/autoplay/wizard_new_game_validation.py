"""Validation helpers for wizard-created RPG autoplay campaigns."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SOURCE = "wizard_new_game_validation_v1"

REQUIRED_STATE_KEYS = (
    "contract_version",
    "metadata",
    "player",
    "narrative_affordances",
    "mechanics",
    "quick_actions",
)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _session_state(prepared: Mapping[str, object]) -> dict[str, Any]:
    for key in ("game", "state"):
        value = prepared.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    session = _mapping(prepared.get("session"))
    state = session.get("state")
    if isinstance(state, Mapping):
        return dict(state)
    return _mapping(prepared.get("simulation_state"))


def _runtime_state(prepared: Mapping[str, object]) -> dict[str, Any]:
    direct = _mapping(prepared.get("runtime_state"))
    if direct:
        return direct
    session = _mapping(prepared.get("session"))
    return _mapping(session.get("runtime_state"))


def _manifest(prepared: Mapping[str, object]) -> dict[str, Any]:
    direct = _mapping(prepared.get("manifest"))
    if direct:
        return direct
    session = _mapping(prepared.get("session"))
    return _mapping(session.get("manifest"))


def _setup_payload(prepared: Mapping[str, object]) -> dict[str, Any]:
    direct = _mapping(prepared.get("setup_payload"))
    if direct:
        return direct
    session = _mapping(prepared.get("session"))
    return _mapping(session.get("setup_payload"))


def _metadata(state: Mapping[str, object], manifest: Mapping[str, object]) -> dict[str, Any]:
    metadata = _mapping(state.get("metadata"))
    if metadata:
        return metadata
    return _mapping(manifest)


def _has_initial_stats(metadata: Mapping[str, object], setup_payload: Mapping[str, object]) -> bool:
    if isinstance(metadata.get("initial_stats"), Mapping) and bool(metadata.get("initial_stats")):
        return True
    summary = str(setup_payload.get("generated_class_summary") or "")
    return "Stats:" in summary


def _has_starter_loadout(state: Mapping[str, object], metadata: Mapping[str, object]) -> bool:
    if isinstance(metadata.get("starter_gear"), list) and bool(metadata.get("starter_gear")):
        return True
    player = _mapping(state.get("player"))
    return bool(player.get("inventory")) and isinstance(player.get("currency"), Mapping)


def _has_setting_effects(state: Mapping[str, object]) -> bool:
    mechanics = _mapping(state.get("mechanics"))
    effects = mechanics.get("setup_effects")
    return isinstance(effects, list) and bool(effects)


def build_wizard_new_game_validation(
    prepared: Mapping[str, object] | None,
    *,
    required: bool = False,
    turns_requested: int | None = None,
) -> dict[str, Any]:
    """Return a deterministic validation snapshot for autoplay setup provenance."""

    prepared_map = _mapping(prepared)
    state = _session_state(prepared_map)
    runtime_state = _runtime_state(prepared_map)
    manifest = _manifest(prepared_map)
    setup_payload = _setup_payload(prepared_map)
    metadata = _metadata(state, manifest)
    narrative = _mapping(state.get("narrative_affordances"))
    missing_state_keys = [key for key in REQUIRED_STATE_KEYS if key not in state]
    kind = str(metadata.get("kind") or manifest.get("kind") or "")
    created_from = str(runtime_state.get("created_from") or metadata.get("created_from") or "")
    detected = (
        state.get("contract_version") == "rpg_new_game_v1"
        or kind == "new_game"
        or created_from == "new_game"
    )
    checks = {
        "new_game_contract": state.get("contract_version") == "rpg_new_game_v1",
        "new_game_kind": kind == "new_game",
        "created_from_new_game": created_from == "new_game",
        "setup_payload_present": bool(setup_payload),
        "initial_stats_present": _has_initial_stats(metadata, setup_payload),
        "starter_loadout_present": _has_starter_loadout(state, metadata),
        "setting_effects_present": _has_setting_effects(state),
        "opening_story_present": isinstance(narrative.get("opening_story"), Mapping),
        "quick_actions_present": bool(state.get("quick_actions")),
        "no_missing_state_keys": not missing_state_keys,
    }
    failed_checks = [key for key, ok in checks.items() if not ok]
    status = "validated" if detected and not failed_checks else "not_detected"
    if required and (not detected or failed_checks):
        status = "failed"
    return {
        "ok": status != "failed",
        "source": SOURCE,
        "status": status,
        "required": bool(required),
        "detected": bool(detected),
        "checks": checks,
        "failed_checks": failed_checks,
        "missing_state_keys": missing_state_keys,
        "session_id": prepared_map.get("session_id") or state.get("session_id") or manifest.get("session_id"),
        "turns_requested": turns_requested,
        "metadata": {
            "kind": kind or None,
            "created_from": created_from or None,
            "campaign_template": metadata.get("campaign_template") or setup_payload.get("campaign_template"),
            "difficulty": metadata.get("difficulty") or setup_payload.get("difficulty"),
            "world_activity": metadata.get("world_activity") or setup_payload.get("world_activity"),
            "economy_pressure": metadata.get("economy_pressure") or setup_payload.get("economy_pressure"),
            "combat_lethality": metadata.get("combat_lethality") or setup_payload.get("combat_lethality"),
            "seed": metadata.get("seed") or setup_payload.get("seed"),
        },
    }
