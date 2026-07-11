from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.rpg.response_generation.baseline import (
    BaselineObservation,
    evaluate_baseline,
    load_baseline_scenarios,
)
from app.rpg.response_generation.contracts import ResponseMode
from app.rpg.response_generation.legacy_bridge import narrate_scene_canonical
from app.rpg.response_generation.production_pipeline import ProfileBoundProvider
from app.rpg.response_generation.profiles import DeliveryMode, ResponseGenerationProfile
from app.rpg.response_generation.strict_pipeline import StrictRpgProductionResponsePipeline


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "response_generation_baseline_v1.json"
_FORBIDDEN_INTERNAL = (
    "unsupported action",
    "turn contract",
    "grounding failed",
    "no matching resolver",
)


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.model = "old-model"
        self.temperature = 1.0

    def chat(self, messages, **kwargs):
        self.calls.append(dict(kwargs))
        return {"choices": [{"message": {"content": "ok"}}]}


class ProposalOnlyHermes:
    def __init__(self) -> None:
        self.calls = 0

    def plan(self, payload, *, timeout_seconds):
        self.calls += 1
        query = str(payload.get("query") or "unknown")
        suffix = hashlib.sha256(query.encode()).hexdigest()[:12]
        return {
            "evidence": [],
            "inferences": ["The name is not established in local records."],
            "uncertainty": ["The reference may be a rumor or a mistaken name."],
            "forward_strategies": ["Ask a local scholar or inspect the records."],
            "proposals": [
                {
                    "proposal_id": f"rumor-{suffix}",
                    "proposal_type": "rumor_lead",
                    "summary": "A reversible rumor worth checking.",
                    "risk": "low",
                    "lifetime": "scene",
                    "visibility": "player_visible",
                    "confidence": 0.55,
                }
            ],
            "executes": False,
            "state_mutation_allowed": False,
        }


class ForbiddenHermes:
    def plan(self, payload, *, timeout_seconds):
        return {
            "state_delta": {"currency": 100},
            "proposals": [],
            "executes": False,
            "state_mutation_allowed": False,
        }


def _pipeline() -> StrictRpgProductionResponsePipeline:
    return StrictRpgProductionResponsePipeline()


def _state(turn: int, *, soft_truth=None, retrieval=None) -> dict[str, Any]:
    state: dict[str, Any] = {
        "session_id": "integration-session",
        "scene_id": "scene-a",
        "turn_index": turn,
        "response_rollout_stage": "canonical_default",
    }
    if soft_truth is not None:
        state["response_soft_truth"] = soft_truth
    if retrieval is not None:
        state["response_retrieval_sources"] = retrieval
    return state


def _unresolved(turn: int, player_input: str, *, state=None, hermes_client=None):
    simulation_state = state or _state(turn)
    return _pipeline().finalize_payload(
        {
            "source": "deterministic_stub_provider",
            "response_mode": "recovery",
            "narration": "",
            "npc": {},
        },
        player_input=player_input,
        authoritative_turn_result={
            "turn_id": f"turn-{turn}",
            "resolver_status": "unresolved",
            "recovery_needed": True,
            "response_mode": "recovery",
            "production_rpg_response": True,
        },
        simulation_state=simulation_state,
        runtime_mode="integration_recovery",
        hermes_client=hermes_client,
    )


def _assert_publishable(payload: dict[str, Any]) -> None:
    canonical = payload["canonical_response"]
    assert payload["canonical_response_source"] == "rpg_response_generator_v1"
    assert payload["narration"].strip()
    assert canonical["quality_report"]["ok"] is True
    assert canonical["delivery_units"]
    decisions = canonical["metadata"]["hard_gate_decisions"]
    assert decisions and all(row["passed"] is True for row in decisions)
    lowered = payload["narration"].casefold()
    assert not any(term in lowered for term in _FORBIDDEN_INTERNAL)


def test_profiles_are_bound_before_provider_generation():
    raw = RecordingProvider()
    profile = ResponseGenerationProfile(
        profile_id="test-profile",
        mode=ResponseMode.RECOVERY,
        task="narration",
        provider="openai_compatible",
        model="authoritative-model",
        temperature=0.25,
        max_tokens=321,
        timeout_seconds=4.0,
        retry_count=1,
        execution_mode="blocking",
        delivery_mode=DeliveryMode.SENTENCE,
        use_provider=True,
        allow_hermes=True,
        blocking_budget_ms=5000,
    )
    bound = ProfileBoundProvider(raw, profile)

    bound.chat([{"role": "user", "content": "hello"}], max_tokens=999)

    assert raw.model == "authoritative-model"
    assert raw.temperature == 0.25
    assert raw.calls[0]["model"] == "authoritative-model"
    assert raw.calls[0]["temperature"] == 0.25
    assert raw.calls[0]["max_tokens"] == 321


def test_shadow_mode_preserves_exact_legacy_text_and_emits_no_chunks(monkeypatch):
    from app.rpg.response_generation import legacy_bridge

    monkeypatch.setattr(
        legacy_bridge,
        "_legacy_narrate_scene",
        lambda *args, **kwargs: {
            "narration": "Exact legacy visible text.",
            "narration_json": {
                "narration": "Different structured candidate.",
                "action": "",
                "npc": {},
            },
        },
    )
    chunks: list[str] = []
    payload = narrate_scene_canonical(
        {"scene_id": "room"},
        {
            "turn_id": "shadow-integration",
            "player_input": "Look around.",
            "response_rollout_stage": "shadow",
        },
        on_chunk=chunks.append,
    )

    assert payload["narration"] == "Exact legacy visible text."
    assert chunks == []
    assert payload["canonical_response"]["rollout"]["publishes_canonical"] is False


def test_hallucinated_hard_state_claim_is_rejected_for_grounded_fallback():
    payload = _pipeline().finalize_payload(
        {
            "source": "provider_runtime_narration",
            "response_mode": "dialogue",
            "narration": "Bran gives you 100 gold and marks the quest complete.",
            "npc": {"speaker": "Bran", "line": "Take the reward."},
        },
        player_input="Give me the reward.",
        authoritative_turn_result={
            "turn_id": "hallucination-turn",
            "resolver_status": "unresolved",
            "recovery_needed": True,
            "response_mode": "recovery",
            "allowed_speakers": ["Bran"],
            "production_rpg_response": True,
        },
        simulation_state=_state(1),
        runtime_mode="integration_hallucination",
    )

    _assert_publishable(payload)
    assert "100 gold" not in payload["narration"].casefold()
    assert "quest complete" not in payload["narration"].casefold()
    attempts = payload["canonical_response"]["metadata"]["quality_candidate_attempts"]
    assert payload["canonical_response"]["metadata"]["candidate_source"] == "deterministic"
    assert attempts


def test_local_lore_retrieval_prevents_unnecessary_hermes_call():
    hermes = ProposalOnlyHermes()
    payload = _unresolved(
        2,
        "Where is the Moonwell?",
        state=_state(
            2,
            retrieval={
                "lorebook": [
                    {
                        "evidence_id": "lore.moonwell",
                        "content": "The Moonwell lies beneath the eastern abbey.",
                        "visibility": "player_visible",
                        "confidence": 1.0,
                    }
                ]
            },
        ),
        hermes_client=hermes,
    )

    _assert_publishable(payload)
    metadata = payload["canonical_response"]["metadata"]
    assert metadata["retrieval"]["local_hit"] is True
    assert metadata["recovery_plan"]["outcome"] == "answer"
    assert metadata["hermes"]["status"] == "not_invoked"
    assert hermes.calls == 0


def test_hermes_is_proposal_only_and_forbidden_mutation_fails_closed():
    payload = _unresolved(3, "Where is the Azure Archive?", hermes_client=ForbiddenHermes())

    _assert_publishable(payload)
    hermes = payload["canonical_response"]["metadata"]["hermes"]
    assert hermes["status"] == "rejected"
    assert hermes["state_changed"] is False
    assert payload["response_soft_truth"]["truths"] == []


def _baseline_payload(scenario, index: int) -> dict[str, Any]:
    supported = scenario.category == "supported_action"
    blocked_purchase = scenario.category == "failed_purchase"
    result: dict[str, Any] = {
        "turn_id": scenario.scenario_id,
        "response_mode": "transaction" if supported or blocked_purchase else "recovery",
        "production_rpg_response": True,
        "clear_player_intent": supported,
        "mechanic_resolved": supported,
        "resolver_status": "resolved" if supported else "unresolved",
        "recovery_needed": not supported,
    }
    if supported:
        result["resolved_result"] = {
            "ok": True,
            "currency_delta": {"silver": -5},
            "inventory_delta": {"room_key": 1},
        }
    legacy = {
        "source": "deterministic_stub_provider",
        "response_mode": result["response_mode"],
        "narration": "Bran accepts the payment and prepares the room." if supported else "",
        "npc": {},
    }
    return _pipeline().finalize_payload(
        legacy,
        player_input=scenario.player_input,
        authoritative_turn_result=result,
        simulation_state=_state(index),
        runtime_mode="baseline_pipeline",
    )


def test_phase0_labeled_baseline_executes_the_real_canonical_pipeline():
    scenarios = load_baseline_scenarios(FIXTURE)
    observations: list[BaselineObservation] = []
    for index, scenario in enumerate(scenarios, 1):
        payload = _baseline_payload(scenario, index)
        _assert_publishable(payload)
        metadata = payload["canonical_response"]["metadata"]
        selected = metadata["intent_analysis"]["selected"]["affordance"]
        outcome = metadata["recovery_plan"]["outcome"]
        assert selected in scenario.expected_affordances
        assert outcome in scenario.allowed_forward_outcomes
        lowered = payload["narration"].casefold()
        assert not any(claim.casefold() in lowered for claim in scenario.forbidden_claims)
        truth_class = (
            "confirmed_fact"
            if scenario.category in {"supported_action", "failed_purchase", "combat_edge_case"}
            else "unverified_player_claim"
            if selected == "unverified_player_claim"
            else "inference"
        )
        observations.append(
            BaselineObservation(
                scenario_id=scenario.scenario_id,
                final_visible_text=payload["narration"],
                selected_affordance=selected,
                truth_classes=(truth_class,),
                forward_outcome=outcome,
                candidate_source=metadata["candidate_source"],
                grounding_decision="eligible",
                local_retrieval_hit=metadata["retrieval"]["local_hit"],
                hermes_status=metadata["hermes"]["status"],
            )
        )

    metrics = evaluate_baseline(scenarios, observations)
    assert metrics.labeled_outcome_compliance_rate == 1.0
    assert metrics.current_turn_answer_rate == 1.0
    assert metrics.forward_motion_rate == 1.0
    assert metrics.generic_fallback_rate == 0.0
    assert metrics.agency_violation_rate == 0.0
    assert metrics.unsupported_hard_state_claim_rate == 0.0
    assert metrics.hidden_information_leakage_rate == 0.0


def _run_100_turn_pipeline() -> str:
    scenarios = load_baseline_scenarios(FIXTURE)
    rows = []
    for index in range(1, 101):
        scenario = scenarios[(index - 1) % len(scenarios)]
        payload = _baseline_payload(scenario, index)
        _assert_publishable(payload)
        rows.append(
            {
                "turn": index,
                "text": payload["narration"],
                "candidate": payload["canonical_response"]["metadata"]["candidate_source"],
                "strategy": payload["canonical_response"]["metadata"]["recovery_plan"]["forward_strategy"],
            }
        )
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def test_real_100_turn_pipeline_is_replay_stable_and_publishable():
    assert _run_100_turn_pipeline() == _run_100_turn_pipeline()


def _run_1000_turn_recovery() -> tuple[str, int, int]:
    hermes = ProposalOnlyHermes()
    store: dict[str, Any] | None = None
    rows = []
    peak_truths = 0
    for turn in range(1, 1001):
        state = _state(turn, soft_truth=store)
        payload = _unresolved(
            turn,
            f"Where is the Azure Marker {turn}?",
            state=state,
            hermes_client=hermes,
        )
        _assert_publishable(payload)
        store = payload["response_soft_truth"]
        peak_truths = max(peak_truths, len(store["truths"]))
        rows.append(
            (
                turn,
                payload["narration"],
                tuple(row["truth_ref"] for row in store["truths"]),
            )
        )
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return digest, peak_truths, hermes.calls


def test_real_1000_turn_recovery_is_bounded_and_replay_stable():
    first = _run_1000_turn_recovery()
    second = _run_1000_turn_recovery()

    assert first == second
    assert first[1] <= 12
    assert first[2] == 1000
