from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.rpg.response_generation.baseline import (
    BaselineObservation,
    evaluate_baseline,
    load_baseline_scenarios,
)


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
BASELINE_PATH = FIXTURE_ROOT / "response_generation_baseline_v1.json"
HOLDOUT_MANIFEST_PATH = FIXTURE_ROOT / "response_generation_holdout_manifest_v1.json"


def _perfect_observation(scenario, index: int) -> BaselineObservation:
    return BaselineObservation(
        scenario_id=scenario.scenario_id,
        final_visible_text=f"A grounded response for {scenario.scenario_id}.",
        selected_affordance=scenario.expected_affordances[0],
        truth_classes=(scenario.allowed_truth_classes[0],),
        forward_outcome=(
            "clarification"
            if scenario.clarification_required
            else scenario.allowed_forward_outcomes[0]
        ),
        candidate_source="deterministic_stub_provider",
        grounding_decision="eligible",
        latency_ms=float((index + 1) * 10),
        local_retrieval_hit=scenario.category in {"unknown_lore", "broad_world_question"},
    )


def test_phase0_baseline_fixture_covers_required_categories():
    scenarios = load_baseline_scenarios(BASELINE_PATH)
    categories = {scenario.category for scenario in scenarios}

    assert len(scenarios) >= 12
    assert {
        "supported_action",
        "unknown_lore",
        "invented_entity",
        "unsupported_spell",
        "impossible_technology",
        "ambiguous_social_action",
        "contradictory_player_claim",
        "failed_purchase",
        "invalid_travel",
        "combat_edge_case",
        "agency_sensitive_recovery",
        "broad_world_question",
    }.issubset(categories)


def test_phase0_fixture_labels_are_versioned_and_complete():
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    scenarios = load_baseline_scenarios(BASELINE_PATH)

    assert payload["format_version"] == "rpg_response_baseline_v1"
    assert all(scenario.expected_affordances for scenario in scenarios)
    assert all(scenario.allowed_truth_classes for scenario in scenarios)
    assert all(scenario.allowed_forward_outcomes for scenario in scenarios)


def test_phase0_deterministic_metrics_do_not_depend_on_live_wording():
    scenarios = load_baseline_scenarios(BASELINE_PATH)
    observations = tuple(
        _perfect_observation(scenario, index)
        for index, scenario in enumerate(scenarios)
    )

    metrics = evaluate_baseline(scenarios, observations)

    assert metrics.scenario_count == len(scenarios)
    assert metrics.observation_count == len(scenarios)
    assert metrics.labeled_outcome_compliance_rate == 1.0
    assert metrics.current_turn_answer_rate == 1.0
    assert metrics.forward_motion_rate == 1.0
    assert metrics.generic_fallback_rate == 0.0
    assert metrics.agency_violation_rate == 0.0
    assert metrics.unsupported_hard_state_claim_rate == 0.0
    assert metrics.hidden_information_leakage_rate == 0.0
    assert metrics.p50_latency_ms == 65.0
    assert metrics.p95_latency_ms == 114.5


def test_phase0_metrics_record_failures_without_model_calls():
    scenarios = load_baseline_scenarios(BASELINE_PATH)
    scenario = scenarios[0]
    observation = BaselineObservation(
        scenario_id=scenario.scenario_id,
        final_visible_text="You cannot do that.",
        selected_affordance="generic",
        truth_classes=("generated_proposal",),
        forward_outcome="none",
        fallback_reason="generic",
        hard_state_claims=("quest.completed",),
        hidden_fact_leaks=("director.hidden_ambush",),
        agency_violation=True,
        repeated_content=True,
        stale_response_selected=True,
        hermes_status="timeout",
    )

    metrics = evaluate_baseline((scenario,), (observation,))

    assert metrics.labeled_outcome_compliance_rate == 0.0
    assert metrics.current_turn_answer_rate == 0.0
    assert metrics.forward_motion_rate == 0.0
    assert metrics.generic_fallback_rate == 1.0
    assert metrics.agency_violation_rate == 1.0
    assert metrics.unsupported_hard_state_claim_rate == 1.0
    assert metrics.hidden_information_leakage_rate == 1.0
    assert metrics.repeated_content_rate == 1.0
    assert metrics.stale_response_selection_rate == 1.0
    assert metrics.hermes_invocation_rate == 1.0
    assert metrics.hermes_timeout_rate == 1.0
    assert metrics.evaluations[0].compliant is False


def test_phase0_unknown_and_duplicate_observations_fail_closed():
    scenarios = load_baseline_scenarios(BASELINE_PATH)
    observation = _perfect_observation(scenarios[0], 0)

    with pytest.raises(ValueError, match="duplicate observation"):
        evaluate_baseline((scenarios[0],), (observation, observation))

    unknown = BaselineObservation(
        scenario_id="unknown",
        final_visible_text="Unknown.",
        selected_affordance="clarification",
        truth_classes=("inference",),
        forward_outcome="clarification",
    )
    with pytest.raises(ValueError, match="unknown scenario observation"):
        evaluate_baseline((scenarios[0],), (unknown,))


def test_phase0_holdout_manifest_contains_no_prompt_or_label_content():
    manifest = json.loads(HOLDOUT_MANIFEST_PATH.read_text(encoding="utf-8"))
    serialized = json.dumps(manifest, sort_keys=True).casefold()

    assert manifest["format_version"] == "rpg_response_holdout_manifest_v1"
    assert manifest["scenario_hash_algorithm"] == "sha256"
    assert len(manifest["scenario_hashes"]) >= 4
    assert all(len(value) == 64 for value in manifest["scenario_hashes"])
    assert all(int(value, 16) >= 0 for value in manifest["scenario_hashes"])
    assert manifest["policy"]["contents_committed_to_repository"] is False
    assert "player_input" not in serialized
    assert "expected_affordances" not in serialized


def test_phase0_public_fixture_ids_are_not_raw_holdout_hash_inputs():
    scenarios = load_baseline_scenarios(BASELINE_PATH)
    manifest = json.loads(HOLDOUT_MANIFEST_PATH.read_text(encoding="utf-8"))
    holdout_hashes = set(manifest["scenario_hashes"])

    public_hashes = {
        hashlib.sha256(scenario.scenario_id.encode("utf-8")).hexdigest()
        for scenario in scenarios
    }
    assert public_hashes.isdisjoint(holdout_hashes)
