from __future__ import annotations

from dataclasses import replace

import pytest

from app.rpg.response_generation.contracts import (
    CandidateSource,
    ResponseCandidate,
    ResponseMode,
    ResponseRequest,
    SectionType,
    SemanticResponsePlan,
    SemanticSection,
)
from app.rpg.response_generation.legacy_bridge import narrate_scene_canonical
from app.rpg.response_generation import legacy_bridge
from app.rpg.response_generation.orchestration import RpgResponseGenerator
from app.rpg.response_generation.performance import (
    LatencyTrace,
    VersionedResponseCache,
    blocking_path_decision,
    evaluate_latency_benchmark,
)
from app.rpg.response_generation.profiled_generator import ProfiledRpgResponseGenerator
from app.rpg.response_generation.profiles import (
    DeliveryMode,
    ResponseProfileRegistry,
    validate_response_profile,
)
from app.rpg.response_generation.validated_delivery import (
    DeliveryState,
    ValidatedDeliverySession,
    validate_publishable_response,
)


def _candidate(mode: ResponseMode, text: str = "The approved response arrives. Another sentence follows."):
    return ResponseCandidate(
        candidate_id=f"candidate-{mode.value}",
        source=CandidateSource.DETERMINISTIC,
        current_turn_relevance=1.0,
        forward_motion=1.0,
        specificity=1.0,
        naturalness=1.0,
        plan=SemanticResponsePlan(
            mode=mode,
            sections=(
                SemanticSection(
                    section_id="approved-section",
                    section_type=SectionType.NARRATION,
                    text=text,
                ),
            ),
        ),
    )


def _profiled(mode: ResponseMode, *, policy=None, result=None):
    base = RpgResponseGenerator(candidate_adapter=lambda _request: (_candidate(mode),))
    generator = ProfiledRpgResponseGenerator(base)
    request = ResponseRequest(
        turn_id=f"turn-{mode.value}",
        player_input="Continue.",
        authoritative_turn_result={"response_mode": mode.value, **(result or {})},
        provider_policy=policy or {},
        runtime_mode="supported_mechanic" if result and result.get("mechanic_resolved") else "canonical",
    )
    return generator, request, generator.generate(request)


def test_phase9_registry_is_authoritative_and_ignores_runtime_model_overrides():
    registry = ResponseProfileRegistry()
    profile, ignored = registry.resolve_from_request(
        ResponseMode.DIALOGUE,
        {
            "provider": "untrusted-provider",
            "model": "untrusted-model",
            "timeout_seconds": 99,
            "retry_count": 8,
            "high_value": True,
        },
    )

    assert profile.provider == "lmstudio"
    assert profile.model == "story-local"
    assert profile.timeout_seconds <= 12
    assert profile.retry_count <= 1
    assert set(ignored) == {"provider", "model", "timeout_seconds", "retry_count"}
    assert validate_response_profile(profile) == ()


def test_phase9_utility_and_supported_actions_avoid_hermes_and_heavy_generation():
    registry = ResponseProfileRegistry()
    utility = registry.resolve(ResponseMode.UTILITY)
    action = registry.resolve(ResponseMode.ACTION)
    utility_path = blocking_path_decision(
        ResponseMode.UTILITY,
        utility,
        supported_mechanic=True,
        recovery_needed=False,
    )
    action_path = blocking_path_decision(
        ResponseMode.ACTION,
        action,
        supported_mechanic=True,
        recovery_needed=False,
    )

    assert utility.use_provider is False
    assert utility_path.action == "deterministic"
    assert utility_path.use_hermes is False
    assert action_path.use_hermes is False


def test_phase9_hermes_is_allowed_only_for_recovery_after_local_routing():
    registry = ResponseProfileRegistry()
    normal = registry.resolve(ResponseMode.DIALOGUE, recovery_needed=False)
    recovery = registry.resolve(ResponseMode.RECOVERY, recovery_needed=True)
    investigation = registry.resolve(ResponseMode.INVESTIGATION, recovery_needed=True)

    assert normal.allow_hermes is False
    assert recovery.allow_hermes is True
    assert investigation.allow_hermes is True
    assert recovery.timeout_seconds <= 6


def test_phase9_profiled_generator_records_authoritative_policy():
    _, _, rendered = _profiled(
        ResponseMode.RECOVERY,
        policy={"provider": "ignored", "timeout_seconds": 99},
        result={"recovery_needed": True},
    )

    profile = rendered.metadata["response_profile"]
    path = rendered.metadata["blocking_path"]
    assert profile["mode"] == "recovery"
    assert profile["allow_hermes"] is True
    assert profile["timeout_seconds"] <= 6
    assert rendered.metadata["ignored_runtime_profile_overrides"] == [
        "provider",
        "timeout_seconds",
    ]
    assert path["action"] == "recover"
    assert path["use_hermes"] is True
    assert rendered.metadata["validation_complete"] is True


def test_phase9_no_delivery_unit_exists_before_full_validation():
    generator, request, rendered = _profiled(ResponseMode.ACTION)
    profile = generator.resolve_profile(request, rendered.mode)
    invalid_quality = replace(rendered, quality_report={"ok": False})
    invalid_gate = replace(
        rendered,
        metadata={
            **dict(rendered.metadata),
            "hard_gate_decisions": [{"gate": "state_claims", "passed": False}],
        },
    )

    with pytest.raises(ValueError, match="quality_not_approved"):
        ValidatedDeliverySession.prepare(invalid_quality, profile)
    with pytest.raises(ValueError, match="hard_gate_failed"):
        ValidatedDeliverySession.prepare(invalid_gate, profile)
    assert validate_publishable_response(rendered) == ()


def test_phase9_delivery_streams_only_approved_sentence_units_in_order():
    generator, request, rendered = _profiled(ResponseMode.ACTION)
    profile = generator.resolve_profile(request, rendered.mode)
    assert profile.delivery_mode is DeliveryMode.SENTENCE
    session = ValidatedDeliverySession.prepare(rendered, profile)

    first = session.next_unit()
    assert first is not None and first.approved is True
    assert first.text == "The approved response arrives."
    session.acknowledge(first)
    second = session.next_unit()
    assert second is not None and second.text == "Another sentence follows."
    session.acknowledge(second)

    assert session.state is DeliveryState.COMPLETED
    assert session.next_unit() is None
    assert session.checkpoint().delivered_text == rendered.text


def test_phase9_interruption_and_restore_never_deliver_unheard_suffix():
    generator, request, rendered = _profiled(ResponseMode.DIALOGUE)
    profile = generator.resolve_profile(request, rendered.mode)
    session = ValidatedDeliverySession.prepare(rendered, profile)
    first = session.next_unit()
    assert first is not None
    session.acknowledge(first)
    checkpoint = session.interrupt("player_spoke")

    assert checkpoint.state is DeliveryState.INTERRUPTED
    assert checkpoint.delivered_text == first.text
    assert session.next_unit() is None

    restored = ValidatedDeliverySession.prepare(rendered, profile)
    restored.restore(checkpoint)
    assert restored.next_unit() is None
    assert restored.checkpoint() == checkpoint


def test_phase9_legacy_bridge_buffers_raw_chunks_until_canonical_approval(monkeypatch):
    raw_chunks: list[str] = []
    delivered: list[str] = []

    def fake_legacy(*args, **kwargs):
        assert kwargs["on_chunk"] is None
        raw_chunks.append("RAW UNVALIDATED TOKEN")
        return {
            "narration": "Result: The door opens. The door opens.",
            "narration_json": {
                "narration": "Result: The door opens. The door opens.",
                "action": "",
                "npc": {},
            },
        }

    monkeypatch.setattr(legacy_bridge, "_legacy_narrate_scene", fake_legacy)
    result = narrate_scene_canonical(
        {"scene_id": "room"},
        {"turn_id": "turn-delivery", "player_input": "Open the door."},
        on_chunk=delivered.append,
    )

    assert raw_chunks == ["RAW UNVALIDATED TOKEN"]
    assert delivered == ["The door opens."]
    assert "RAW UNVALIDATED TOKEN" not in delivered
    assert result["canonical_response"]["delivery_checkpoint"]["state"] == "completed"


def test_phase9_versioned_cache_and_latency_benchmark_are_deterministic():
    cache: VersionedResponseCache[dict] = VersionedResponseCache()
    calls = []
    first, first_hit = cache.get_or_create(
        "entity-card", "npc_bran", ("world-v1", "npc-v2"),
        lambda: calls.append(1) or {"name": "Bran"},
    )
    second, second_hit = cache.get_or_create(
        "entity-card", "npc_bran", ("world-v1", "npc-v2"),
        lambda: calls.append(2) or {"name": "Wrong"},
    )
    changed, changed_hit = cache.get_or_create(
        "entity-card", "npc_bran", ("world-v1", "npc-v3"),
        lambda: {"name": "Bran updated"},
    )
    benchmark = evaluate_latency_benchmark(
        tuple(float(index * 100) for index in range(1, 21)),
        p95_budget_ms=1950,
    )
    trace = LatencyTrace()
    trace.record("resolver", 10)
    trace.record("validation", 5)
    trace.first_approved_delivery_ms = 18

    assert first == second == {"name": "Bran"}
    assert first_hit is False and second_hit is True
    assert calls == [1]
    assert changed_hit is False and changed["name"] == "Bran updated"
    assert benchmark.sample_count == 20
    assert benchmark.p95_ms == 1905.0
    assert benchmark.passed is True
    assert trace.total_ms == 15.0
    assert trace.as_dict()["first_approved_delivery_ms"] == 18
