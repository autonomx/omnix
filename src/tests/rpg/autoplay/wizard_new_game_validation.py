"""Validation helpers for Campaign Genesis RPG autoplay campaigns."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SOURCE = "campaign_genesis_validation_v2"
LEGACY_SOURCE = "wizard_new_game_validation_v1"
GENESIS_CONTRACT_VERSION = "rpg_genesis_v2"
GENESIS_COMPILER_VERSION = "rpg_genesis_compiler_v1"
MANDATORY_TURN_THRESHOLD = 100

REQUIRED_STATE_KEYS = (
    "contract_version",
    "metadata",
    "player",
    "narrative_affordances",
    "mechanics",
    "quick_actions",
)
GENESIS_REQUIRED_KEYS = (
    "genesis_snapshot",
    "compiled_genesis_snapshot",
    "bootstrap_snapshot",
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


def _snapshot(state: Mapping[str, object], runtime: Mapping[str, object], setup: Mapping[str, object], key: str) -> dict[str, Any]:
    for source in (state, runtime, setup):
        value = _mapping(source.get(key))
        if value:
            return value
    if key == "compiled_genesis_snapshot":
        return _mapping(setup.get("compiled_genesis"))
    return {}


def _legacy_detected(
    state: Mapping[str, object],
    runtime: Mapping[str, object],
    manifest: Mapping[str, object],
) -> bool:
    kind = str(_mapping(state.get("metadata")).get("kind") or manifest.get("kind") or "")
    created_from = str(runtime.get("created_from") or _mapping(state.get("metadata")).get("created_from") or "")
    return (
        state.get("contract_version") == "rpg_new_game_v1"
        or kind == "new_game"
        or created_from == "new_game"
    )


def _effective_required(required: bool, turns_requested: int | None) -> bool:
    if required:
        return True
    if turns_requested is None:
        return False
    return int(turns_requested) >= MANDATORY_TURN_THRESHOLD


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


def _genesis_checks(
    state: Mapping[str, object],
    runtime: Mapping[str, object],
    setup_payload: Mapping[str, object],
    manifest: Mapping[str, object],
) -> dict[str, bool]:
    genesis = _snapshot(state, runtime, setup_payload, "genesis_snapshot")
    compiled = _snapshot(state, runtime, setup_payload, "compiled_genesis_snapshot")
    bootstrap = _snapshot(state, runtime, setup_payload, "bootstrap_snapshot")
    compiled_provenance = _mapping(compiled.get("compiled_provenance"))
    bootstrap_provenance = _mapping(bootstrap.get("provenance"))
    contract_hash = (
        compiled_provenance.get("contract_hash")
        or bootstrap_provenance.get("contract_hash")
        or manifest.get("contract_hash")
    )
    return {
        "genesis_snapshot_present": bool(genesis),
        "compiled_genesis_snapshot_present": bool(compiled),
        "bootstrap_snapshot_present": bool(bootstrap),
        "contract_version_v2": genesis.get("contract_version") == GENESIS_CONTRACT_VERSION,
        "compiler_version_v1": compiled.get("compiler_version") == GENESIS_COMPILER_VERSION,
        "contract_hash_present": isinstance(contract_hash, str) and contract_hash.startswith("sha256:"),
        "compiled_goals_present": bool(compiled.get("compiled_goals")),
        "compiled_preferences_present": isinstance(compiled.get("compiled_decision_biases"), Mapping),
        "compiled_world_traits_present": bool(compiled.get("compiled_world_traits")),
        "compiled_intents_present": bool(compiled.get("compiled_gear_intents")),
        "compiled_loadout_present": bool(compiled.get("compiled_starter_loadout")),
        "bootstrap_goals_present": bool(bootstrap.get("active_goals")),
        "bootstrap_preferences_present": isinstance(bootstrap.get("decision_biases"), Mapping),
        "bootstrap_world_traits_present": bool(bootstrap.get("world_traits")),
        "bootstrap_intents_present": bool(bootstrap.get("gear_intents")),
        "bootstrap_loadout_present": bool(bootstrap.get("starter_loadout")),
    }


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
    effective_required = _effective_required(required, turns_requested)
    missing_state_keys = [key for key in REQUIRED_STATE_KEYS if key not in state]
    missing_genesis_keys = [key for key in GENESIS_REQUIRED_KEYS if not _snapshot(state, runtime_state, setup_payload, key)]
    genesis_checks = _genesis_checks(state, runtime_state, setup_payload, manifest)
    genesis_detected = bool(genesis_checks["genesis_snapshot_present"] or genesis_checks["compiled_genesis_snapshot_present"])
    legacy_detected = _legacy_detected(state, runtime_state, manifest)
    legacy_checks = {
        "new_game_contract": state.get("contract_version") == "rpg_new_game_v1",
        "setup_payload_present": bool(setup_payload),
        "initial_stats_present": _has_initial_stats(metadata, setup_payload),
        "starter_loadout_present": _has_starter_loadout(state, metadata),
        "setting_effects_present": _has_setting_effects(state),
        "opening_story_present": isinstance(narrative.get("opening_story"), Mapping),
        "quick_actions_present": bool(state.get("quick_actions")),
        "no_missing_state_keys": not missing_state_keys,
    }
    checks = dict(genesis_checks if genesis_detected else legacy_checks)
    failed_checks = [key for key, ok in checks.items() if not ok]
    detected = genesis_detected or legacy_detected
    status = "validated" if detected and not failed_checks else "not_detected"
    if effective_required and (not genesis_detected or failed_checks):
        status = "failed"
    return {
        "ok": status != "failed",
        "source": SOURCE if genesis_detected else LEGACY_SOURCE,
        "status": status,
        "required": bool(effective_required),
        "explicitly_required": bool(required),
        "mandatory_turn_threshold": MANDATORY_TURN_THRESHOLD,
        "detected": bool(detected),
        "genesis_detected": bool(genesis_detected),
        "legacy_detected": bool(legacy_detected),
        "checks": checks,
        "failed_checks": failed_checks,
        "missing_state_keys": missing_state_keys,
        "missing_genesis_keys": missing_genesis_keys,
        "session_id": prepared_map.get("session_id") or state.get("session_id") or manifest.get("session_id"),
        "turns_requested": turns_requested,
        "metadata": {
            "kind": metadata.get("kind") or manifest.get("kind") or None,
            "created_from": runtime_state.get("created_from") or metadata.get("created_from") or None,
            "contract_version": genesis_checks.get("contract_version_v2") and GENESIS_CONTRACT_VERSION,
            "compiler_version": genesis_checks.get("compiler_version_v1") and GENESIS_COMPILER_VERSION,
            "campaign_template": metadata.get("campaign_template") or setup_payload.get("campaign_template"),
            "difficulty": metadata.get("difficulty") or setup_payload.get("difficulty"),
            "world_activity": metadata.get("world_activity") or setup_payload.get("world_activity"),
            "economy_pressure": metadata.get("economy_pressure") or setup_payload.get("economy_pressure"),
            "combat_lethality": metadata.get("combat_lethality") or setup_payload.get("combat_lethality"),
            "seed": metadata.get("seed") or setup_payload.get("seed"),
        },
    }
