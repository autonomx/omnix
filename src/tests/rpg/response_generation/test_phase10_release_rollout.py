from __future__ import annotations

import hashlib
import json

from app.rpg.response_generation import legacy_bridge
from app.rpg.response_generation.contracts import (
    CandidateSource,
    ResponseCandidate,
    ResponseMode,
    ResponseRequest,
    SectionType,
    SemanticResponsePlan,
    SemanticSection,
)
from app.rpg.response_generation.orchestration import RpgResponseGenerator
from app.rpg.response_generation.profiled_generator import ProfiledRpgResponseGenerator
from app.rpg.response_generation.proposal_policy import (
    ProposalBudget,
    ProposalPolicy,
    ProposalStore,
    WorldProposal,
)
from app.rpg.response_generation.release_gate import (
    CampaignEvidenceRow,
    ResponseReleaseMetrics,
    evaluate_response_release_gate,
    metrics_from_campaign_rows,
)
from app.rpg.response_generation.rollout import (
    ResponseRolloutController,
    RolloutEvidence,
    RolloutStage,
)
from app.rpg.response_generation.telemetry import (
    build_response_trace,
    player_state_change_indicators,
)
from app.rpg.response_generation.truth_lifetime import TruthLifetime


def _rendered_response():
    candidate = ResponseCandidate(
        candidate_id="trace-candidate",
        source=CandidateSource.DETERMINISTIC,
        current_turn_relevance=1.0,
        forward_motion=1.0,
        specificity=1.0,
        naturalness=1.0,
        plan=SemanticResponsePlan(
            mode=ResponseMode.ACTION,
            sections=(
                SemanticSection(
                    section_id="trace-section",
                    section_type=SectionType.NARRATION,
                    text="You open the door.",
                ),
            ),
        ),
    )
    request = ResponseRequest(
        turn_id="turn-trace",
        player_input="Open the door.",
        authoritative_turn_result={"state_delta": {"location": "room"}},
    )
    rendered = ProfiledRpgResponseGenerator(
        RpgResponseGenerator(candidate_adapter=lambda _request: (candidate,))
    ).generate(request)
    return request, rendered


def test_phase10_trace_is_complete_auditable_and_private_by_default():
    request, rendered = _rendered_response()
    trace = build_response_trace(
        request,
        rendered,
        interpreted_intents=({"intent": "open", "confidence": 1.0},),
        selected_affordance="resolved_action",
        resolver_result={
            "mechanic_resolved": True,
            "raw_prompt": "never expose this",
            "hidden_fact": "secret route",
        },
        retrieval_sources=(
            {"evidence_id": "visible", "source": "scene"},
            {"evidence_id": "hidden", "visibility": "hidden", "content": "secret"},
        ),
        visibility_decisions=({"evidence_id": "hidden", "decision": "excluded"},),
        hermes={"status": "not_invoked"},
        recovery_plan={"forward_strategy": "answer_directly"},
        claim_ledger={"allowed_claim_refs": []},
        semantic_plan={"mode": "action", "sections": []},
        candidate_ranking=({"candidate_id": "trace-candidate", "rank": 1},),
        latency={"resolver_ms": 1, "validation_ms": 2},
        rollout={"stage": "canonical_default"},
        extra={"private_memory": "never expose this either"},
    )
    payload = trace.as_dict()
    serialized = json.dumps(payload, sort_keys=True).casefold()

    assert payload["trace_version"] == "rpg_response_trace_v1"
    assert payload["raw_player_input"] == "Open the door."
    assert payload["selected_affordance"] == "resolved_action"
    assert payload["hard_gates"]
    assert payload["quality"]["ok"] is True
    assert payload["profile"]["mode"] == "action"
    assert payload["final_visible_response"] == "You open the door."
    assert "never expose" not in serialized
    assert "secret route" not in serialized
    assert "raw_prompt" not in serialized
    assert "private_memory" not in serialized


def test_phase10_player_indicators_expose_changes_without_debug_payloads():
    indicators = player_state_change_indicators(
        {
            "currency_delta": {"silver": -5},
            "quest_log_delta": {"quest": "advanced"},
            "discovery_delta": {"clue": "found"},
        }
    )

    assert indicators == (
        {"kind": "currency", "label": "Currency updated"},
        {"kind": "discovery", "label": "New clue discovered"},
        {"kind": "quest_log", "label": "Journal updated"},
    )
    assert "silver" not in json.dumps(indicators)


def test_phase10_rollout_flags_are_cumulative_and_every_stage_rolls_back():
    controller = ResponseRolloutController()
    previous_flags: set[str] = set()
    for stage in RolloutStage:
        config = controller.config(stage)
        current_flags = set(config.enabled_flags)
        assert previous_flags.issubset(current_flags)
        if stage is RolloutStage.SHADOW:
            assert config.publishes_canonical is False
        else:
            assert config.publishes_canonical is True
            rolled_back = controller.rollback(config)
            assert rolled_back.stage == RolloutStage(int(stage) - 1)
        previous_flags = current_flags

    final = controller.config(RolloutStage.LEGACY_REMOVED)
    assert final.legacy_available is False
    assert "validated_delivery" in final.enabled_flags
    assert "canonical_default" in final.enabled_flags


def test_phase10_legacy_removal_requires_production_and_release_evidence():
    controller = ResponseRolloutController()
    insufficient = RolloutEvidence(
        production_turns=99,
        exact_head_checks_passed=True,
        release_gate_passed=True,
        shadow_mismatch_rate=0.0,
        rollback_tested=True,
    )
    sufficient = RolloutEvidence(
        production_turns=100,
        exact_head_checks_passed=True,
        release_gate_passed=True,
        shadow_mismatch_rate=0.05,
        rollback_tested=True,
    )

    assert controller.may_remove_legacy(insufficient) is False
    assert controller.may_remove_legacy(sufficient) is True


def test_phase10_bridge_supports_shadow_comparison_and_canonical_default(monkeypatch):
    monkeypatch.setattr(
        legacy_bridge,
        "_legacy_narrate_scene",
        lambda *args, **kwargs: {
            "narration": "Legacy result: You open the door.",
            "narration_json": {
                "narration": "Result: You open the door. You open the door.",
                "action": "",
                "npc": {},
            },
        },
    )
    shadow = legacy_bridge.narrate_scene_canonical(
        {"scene_id": "room"},
        {
            "turn_id": "shadow-turn",
            "player_input": "Open the door.",
            "response_rollout_stage": "shadow",
        },
    )
    canonical = legacy_bridge.narrate_scene_canonical(
        {"scene_id": "room"},
        {
            "turn_id": "canonical-turn",
            "player_input": "Open the door.",
            "response_rollout_stage": "canonical_default",
        },
    )

    assert shadow["narration"] == "Legacy result: You open the door."
    assert shadow["rollout_comparison"]["visible_text_changed"] is True
    assert shadow["canonical_response"]["rollout"]["stage"] == "shadow"
    assert canonical["narration"] == "You open the door."
    assert canonical["canonical_response"]["developer_trace"]["quality"]["ok"] is True


def test_phase10_100_turn_release_evidence_passes_all_deterministic_gates():
    rows = tuple(
        CampaignEvidenceRow(
            turn_id=f"turn-{index}",
            allowed_forward_outcome=True,
            normal_turn_latency_ms=1000 + index,
        )
        for index in range(100)
    )
    metrics = metrics_from_campaign_rows(
        rows,
        replay_hash_stable=True,
        persistent_proposal_peak=4,
        persistent_proposal_budget=64,
        exact_head_checks_passed=True,
        p95_budget_ms=5000,
    )
    result = evaluate_response_release_gate(metrics)

    assert metrics.forward_outcome_rate == 1.0
    assert metrics.generic_fallback_rate == 0.0
    assert result.passed is True
    assert result.issues == ()
    assert result.metrics["latency"]["passed"] is True


def test_phase10_release_gate_fails_each_nonnegotiable_boundary():
    metrics = ResponseReleaseMetrics(
        scenario_count=100,
        allowed_forward_outcome_count=94,
        generic_inert_fallback_count=1,
        unsupported_hard_state_claim_count=1,
        direct_mutation_path_count=1,
        hidden_fact_leak_count=1,
        player_agency_violation_count=1,
        repeated_action_duplication_count=1,
        unvalidated_delivery_count=1,
        replay_hash_stable=False,
        persistent_proposal_peak=65,
        persistent_proposal_budget=64,
        normal_turn_latency_ms=(6000.0,),
        expected_normal_turn_p95_ms=5000.0,
        exact_head_checks_passed=False,
    )
    result = evaluate_response_release_gate(metrics)

    assert result.passed is False
    assert {
        "forward_outcome_rate_below_threshold",
        "generic_fallback_rate_not_below_threshold",
        "unsupported_hard_state_claims",
        "direct_mutation_paths",
        "hidden_fact_leaks",
        "player_agency_violations",
        "repeated_action_duplication",
        "unvalidated_delivery",
        "replay_hash_unstable",
        "persistent_proposal_growth_unbounded",
        "normal_turn_p95_latency_exceeded",
        "exact_head_checks_not_passed",
    }.issubset(result.issues)


def _run_1000_turn_proposal_endurance() -> tuple[str, int, int]:
    policy = ProposalPolicy(ProposalBudget(max_turn=4, max_scene=12, max_persistent=8))
    store = ProposalStore()
    peak_total = 0
    peak_persistent = 0
    for turn in range(1, 1001):
        scene_id = f"scene-{turn // 25}"
        store.garbage_collect(current_turn=turn, scene_id=scene_id)
        ephemeral = WorldProposal(
            proposal_id=f"ephemeral-{turn}",
            proposal_type="ambient_detail",
            summary=f"Ambient detail {turn}",
            scene_id=scene_id,
            created_turn=turn,
            created_turn_id=f"turn-{turn}",
            seed="endurance-seed",
        )
        store.apply(
            policy.evaluate(
                ephemeral,
                existing=store.truths.values(),
                turn_id=f"turn-{turn}",
            )
        )
        if turn % 100 == 0:
            persistent = WorldProposal(
                proposal_id=f"persistent-{turn}",
                proposal_type="rumor_lead",
                summary=f"Persistent lead {turn}",
                requested_lifetime=TruthLifetime.PERSISTENT,
                player_interactions=1,
                scene_id=scene_id,
                created_turn=turn,
                created_turn_id=f"turn-{turn}",
                seed="endurance-seed",
            )
            store.apply(
                policy.evaluate(
                    persistent,
                    existing=store.truths.values(),
                    turn_id=f"turn-{turn}",
                )
            )
        peak_total = max(peak_total, len(store.truths))
        peak_persistent = max(
            peak_persistent,
            sum(row.persistent for row in store.truths.values()),
        )
    serialized = json.dumps(store.as_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest(), peak_total, peak_persistent


def test_phase10_1000_turn_endurance_is_bounded_and_replay_stable():
    first = _run_1000_turn_proposal_endurance()
    second = _run_1000_turn_proposal_endurance()

    assert first == second
    assert first[1] <= 9
    assert first[2] <= 8
