"""Explicit RPG session API and responsibility-module ownership metadata."""

from .action_execution import (
    build_frontend_bootstrap_payload as build_frontend_bootstrap_payload,
)

from .session_runtime_store import (
    load_runtime_session as load_runtime_session,
    save_runtime_session as save_runtime_session,
)

from .narration_jobs import (
    process_next_narration_job as process_next_narration_job,
)

from .idle_narration_delivery import (
    apply_idle_ticks as apply_idle_ticks,
    apply_resume_catchup as apply_resume_catchup,
)

from .turn_response_composition import (
    apply_turn as apply_turn,
)


_RUNTIME_WRAPPER_MANIFEST = {
    "runtime_modules": [
        "visible_response_selection",
        "companion_turn_runtime",
        "narration_queue_runtime",
        "semantic_interaction_runtime",
        "player_activity_runtime",
        "world_consequence_runtime",
        "semantic_state_changes",
        "combat_intent",
        "action_execution",
        "session_runtime_store",
        "combat_result_reconciliation",
        "combat_action_reconciliation",
        "combat_turn_actions",
        "special_combat_turns",
        "combat_action_runtime",
        "turn_apply",
        "narration_jobs",
        "companion_turn_enrichment",
        "player_turn_execution",
        "idle_resume_runtime",
        "idle_narration_delivery",
        "combat_xp_projection",
        "attack_reward_runtime",
        "combat_reward_narrative",
        "combat_quest_progress",
        "combat_quest_narrative",
        "turn_payload_projection",
        "visible_narration_fallback",
        "travel_panel_response",
        "complete_narration_fallback",
        "llm_narration_projection",
        "deferred_narration_persistence",
        "visible_response_sync",
        "narration_payload_validation",
        "semantic_response_projection",
        "semantic_response_identity",
        "turn_bound_narration",
        "semantic_direct_response",
        "turn_authoritative_guards",
        "turn_response_composition",
        "visible_response_core",
        "turn_action_resolution",
        "turn_combat_resolution",
        "turn_world_resolution",
        "turn_finalization",
        "state_normalization",
    ],
    "final_apply_turn_authoritative_module": "app.rpg.session.turn_authoritative_guards",
    "final_apply_attack_combat_action_module": "app.rpg.session.attack_reward_runtime",
    "combat_contract_modules": [
        "combat_xp_projection",
        "attack_reward_runtime",
        "combat_reward_narrative",
        "combat_quest_progress",
        "combat_quest_narrative",
    ],
}

_EXPECTED_RUNTIME_WRAPPER_MANIFEST = {
    "runtime_modules": [
        "visible_response_selection",
        "companion_turn_runtime",
        "narration_queue_runtime",
        "semantic_interaction_runtime",
        "player_activity_runtime",
        "world_consequence_runtime",
        "semantic_state_changes",
        "combat_intent",
        "action_execution",
        "session_runtime_store",
        "combat_result_reconciliation",
        "combat_action_reconciliation",
        "combat_turn_actions",
        "special_combat_turns",
        "combat_action_runtime",
        "turn_apply",
        "narration_jobs",
        "companion_turn_enrichment",
        "player_turn_execution",
        "idle_resume_runtime",
        "idle_narration_delivery",
        "combat_xp_projection",
        "attack_reward_runtime",
        "combat_reward_narrative",
        "combat_quest_progress",
        "combat_quest_narrative",
        "turn_payload_projection",
        "visible_narration_fallback",
        "travel_panel_response",
        "complete_narration_fallback",
        "llm_narration_projection",
        "deferred_narration_persistence",
        "visible_response_sync",
        "narration_payload_validation",
        "semantic_response_projection",
        "semantic_response_identity",
        "turn_bound_narration",
        "semantic_direct_response",
        "turn_authoritative_guards",
        "turn_response_composition",
        "visible_response_core",
        "turn_action_resolution",
        "turn_combat_resolution",
        "turn_world_resolution",
        "turn_finalization",
        "state_normalization",
    ],
    "final_apply_turn_authoritative_module": "app.rpg.session.turn_authoritative_guards",
    "final_apply_attack_combat_action_module": "app.rpg.session.attack_reward_runtime",
    "combat_contract_modules": [
        "combat_xp_projection",
        "attack_reward_runtime",
        "combat_reward_narrative",
        "combat_quest_progress",
        "combat_quest_narrative",
    ],
}


def get_runtime_wrapper_manifest(_manifest: dict = _RUNTIME_WRAPPER_MANIFEST) -> dict:
    """Return the static responsibility-module and wrapper ownership manifest."""
    return {
        "runtime_modules": list(_manifest["runtime_modules"]),
        "final_apply_turn_authoritative_module": _manifest[
            "final_apply_turn_authoritative_module"
        ],
        "final_apply_attack_combat_action_module": _manifest[
            "final_apply_attack_combat_action_module"
        ],
        "combat_contract_modules": list(_manifest["combat_contract_modules"]),
    }


def get_runtime_wrapper_drift_report(
    _manifest: dict = _RUNTIME_WRAPPER_MANIFEST,
    _expected: dict = _EXPECTED_RUNTIME_WRAPPER_MANIFEST,
) -> dict:
    """Compare explicit RPG wrapper ownership with the recorded architecture contract."""
    actual = get_runtime_wrapper_manifest(_manifest)
    expected = get_runtime_wrapper_manifest(_expected)
    actual_modules = list(actual["combat_contract_modules"])
    expected_modules = list(expected["combat_contract_modules"])
    return {
        "ok": actual == expected,
        "expected_runtime_modules": expected["runtime_modules"],
        "actual_runtime_modules": actual["runtime_modules"],
        "missing_runtime_modules": [
            item
            for item in expected["runtime_modules"]
            if item not in actual["runtime_modules"]
        ],
        "unexpected_runtime_modules": [
            item
            for item in actual["runtime_modules"]
            if item not in expected["runtime_modules"]
        ],
        "expected_combat_contract_modules": expected_modules,
        "actual_combat_contract_modules": actual_modules,
        "missing_combat_contract_modules": [
            item for item in expected_modules if item not in actual_modules
        ],
        "unexpected_combat_contract_modules": [
            item for item in actual_modules if item not in expected_modules
        ],
        "final_apply_turn_authoritative_module": actual[
            "final_apply_turn_authoritative_module"
        ],
        "expected_final_apply_turn_authoritative_module": expected[
            "final_apply_turn_authoritative_module"
        ],
        "final_apply_attack_combat_action_module": actual[
            "final_apply_attack_combat_action_module"
        ],
        "expected_final_apply_attack_combat_action_module": expected[
            "final_apply_attack_combat_action_module"
        ],
    }


__all__ = [
    "apply_idle_ticks",
    "apply_resume_catchup",
    "apply_turn",
    "build_frontend_bootstrap_payload",
    "get_runtime_wrapper_drift_report",
    "get_runtime_wrapper_manifest",
    "load_runtime_session",
    "process_next_narration_job",
    "save_runtime_session",
]
