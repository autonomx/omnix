from __future__ import annotations

from app.rpg.response_generation.hermes_adapter import (
    HermesCircuitBreaker,
    RpgHermesRecoveryAdapter,
)
from app.rpg.response_generation.recovery import LocalRecoveryCoordinator
from app.rpg.response_generation.retrieval import EvidenceRecord, build_retrieval_sources


class FakeHermesClient:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result or {}
        self.error = error
        self.calls = []

    def plan(self, payload, *, timeout_seconds):
        self.calls.append((payload, timeout_seconds))
        if self.error is not None:
            raise self.error
        return self.result


def _unknown_analysis():
    return LocalRecoveryCoordinator().analyze(
        "Where is the Moonwell?",
        retrieval_sources=build_retrieval_sources(),
    )


def test_phase6_local_answer_skips_hermes_entirely():
    analysis = LocalRecoveryCoordinator().analyze(
        "Where is the Moonwell?",
        retrieval_sources=build_retrieval_sources(
            lorebook=[EvidenceRecord("lore-1", "lorebook", "Moonwell is an old name for Silver Spring.")]
        ),
    )
    client = FakeHermesClient({"inferences": ["unused"]})

    result = RpgHermesRecoveryAdapter(client).research("Moonwell", analysis)

    assert result.status == "not_needed"
    assert client.calls == []


def test_phase6_request_is_compact_visible_proposal_only_and_non_executing():
    analysis = _unknown_analysis()
    client = FakeHermesClient(
        {
            "evidence": [{"evidence_id": "research-1", "source": "lore", "content": "No confirmed entry.", "confidence": 0.8}],
            "inferences": ["A northern scholar may recognize the name."],
            "uncertainty": ["The place is unconfirmed."],
            "forward_strategies": ["offer_scholar_lead"],
            "proposals": [{"proposal_id": "p1", "proposal_type": "rumor_lead", "summary": "Ask the northern scholar.", "risk": "medium", "lifetime": "scene"}],
        }
    )
    adapter = RpgHermesRecoveryAdapter(client, timeout_seconds=3.5)

    result = adapter.research(
        "Where is the Moonwell?",
        analysis,
        campaign_version="campaign-7",
        lore_version="lore-2",
    )
    payload, timeout = client.calls[0]

    assert result.status == "success"
    assert result.executes is False
    assert result.state_mutation_allowed is False
    assert result.proposal_only is True
    assert timeout == 3.5
    assert payload["constraints"] == {
        "proposal_only": True,
        "review_required": True,
        "executes": False,
        "state_mutation_allowed": False,
        "hidden_information_forbidden": True,
        "player_choice_must_not_be_taken": True,
    }
    assert "simulation_state" not in payload
    assert "save_state" not in payload
    assert result.proposals[0].proposal_type == "rumor_lead"
    assert result.proposals[0].lifetime == "scene"


def test_phase6_forbidden_mutation_or_execution_result_fails_closed():
    analysis = _unknown_analysis()
    client = FakeHermesClient(
        {
            "inferences": ["Unsafe"],
            "nested": {"quest_delta": {"completed": True}},
            "proposals": [],
        }
    )

    result = RpgHermesRecoveryAdapter(client).research("Moonwell", analysis)

    assert result.status == "rejected"
    assert "quest_delta" in result.error
    assert result.proposals == ()
    assert result.state_mutation_allowed is False


def test_phase6_timeout_and_unavailable_results_preserve_local_fallback():
    analysis = _unknown_analysis()
    timeout_result = RpgHermesRecoveryAdapter(
        FakeHermesClient(error=TimeoutError())
    ).research("Moonwell", analysis)
    unavailable_result = RpgHermesRecoveryAdapter(
        FakeHermesClient(error=RuntimeError("offline"))
    ).research("Moonwell", analysis)

    assert timeout_result.status == "timeout"
    assert timeout_result.proposals == ()
    assert unavailable_result.status == "unavailable"
    assert unavailable_result.error == "offline"
    assert analysis.reason == "local_evidence_insufficient"


def test_phase6_success_results_are_cached_by_query_and_world_versions():
    analysis = _unknown_analysis()
    client = FakeHermesClient({"inferences": ["Try Elara."], "forward_strategies": ["offer_lead"]})
    adapter = RpgHermesRecoveryAdapter(client)

    first = adapter.research("Moonwell", analysis, campaign_version="c1", lore_version="l1")
    second = adapter.research("  MOONWELL ", analysis, campaign_version="c1", lore_version="l1")
    third = adapter.research("Moonwell", analysis, campaign_version="c2", lore_version="l1")

    assert first.status == second.status == third.status == "success"
    assert second.cache_hit is True
    assert len(client.calls) == 2


def test_phase6_circuit_breaker_opens_after_bounded_failures():
    analysis = _unknown_analysis()
    breaker = HermesCircuitBreaker(failure_threshold=2)
    client = FakeHermesClient(error=RuntimeError("offline"))
    adapter = RpgHermesRecoveryAdapter(client, circuit_breaker=breaker)

    assert adapter.research("first", analysis).status == "unavailable"
    assert adapter.research("second", analysis).status == "unavailable"
    third = adapter.research("third", analysis)

    assert breaker.open is True
    assert third.status == "unavailable"
    assert third.error == "circuit_open"
    assert len(client.calls) == 2


def test_phase6_cancellation_prevents_or_discards_agent_result():
    analysis = _unknown_analysis()
    client = FakeHermesClient({"inferences": ["unused"]})
    adapter = RpgHermesRecoveryAdapter(client)

    before = adapter.research("Moonwell", analysis, cancelled=lambda: True)
    states = iter((False, True))
    after = adapter.research("Moonwell two", analysis, cancelled=lambda: next(states))

    assert before.status == "cancelled"
    assert after.status == "cancelled"
    assert len(client.calls) == 1
