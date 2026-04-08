"""Unit tests for Phase 7.4 — NPC Agency & Social Response.

Covers models roundtrip, relationship/faction builders, decision policy,
response builder, and agency engine deterministic behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.rpg.npc_agency.agency_engine import NPCAgencyEngine
from app.rpg.npc_agency.decision_policy import NPCDecisionPolicy
from app.rpg.npc_agency.faction_context import FactionContextBuilder
from app.rpg.npc_agency.models import (
    FactionAlignmentView,
    NPCDecisionContext,
    NPCDecisionResult,
    NPCRelationshipView,
)
from app.rpg.npc_agency.relationship_state import RelationshipStateBuilder
from app.rpg.npc_agency.response_builder import (
    SUPPORTED_NPC_EVENT_TYPES,
    NPCResponseBuilder,
)

# ===========================================================================
# Test Helpers / Fakes
# ===========================================================================

@dataclass
class FakeFact:
    fact_id: str = ""
    subject: str = ""
    predicate: str = ""
    value: Any = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "fact_id": self.fact_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "value": self.value,
            "metadata": self.metadata,
        }


@dataclass
class FakeConsequence:
    consequence_id: str = ""
    entity_ids: list = field(default_factory=list)
    consequence_type: str = ""

    def to_dict(self) -> dict:
        return {
            "consequence_id": self.consequence_id,
            "entity_ids": self.entity_ids,
            "consequence_type": self.consequence_type,
        }


@dataclass
class FakeCommitment:
    commitment_id: str = ""
    actor_id: str = ""
    target_id: str = ""
    kind: str = ""
    text: str = ""
    status: str = "active"

    def to_dict(self) -> dict:
        return {
            "commitment_id": self.commitment_id,
            "actor_id": self.actor_id,
            "target_id": self.target_id,
            "kind": self.kind,
            "text": self.text,
            "status": self.status,
        }


@dataclass
class FakeState:
    stable_world_facts: dict = field(default_factory=dict)
    commitments: dict = field(default_factory=dict)
    recent_consequences: list = field(default_factory=list)


class FakeCoherenceCore:
    def __init__(
        self,
        facts: dict | None = None,
        commitments: dict | None = None,
        consequences: list | None = None,
        scene: dict | None = None,
    ):
        self._state = FakeState(
            stable_world_facts=facts or {},
            commitments=commitments or {},
            recent_consequences=consequences or [],
        )
        self._scene = scene or {}

    def get_state(self) -> FakeState:
        return self._state

    def get_scene_summary(self) -> dict:
        return self._scene

    def get_unresolved_threads(self) -> list[dict]:
        return []


class FakeGMState:
    def __init__(self, focus_target: str | None = None):
        self._focus_target = focus_target

    def get_focus_target(self) -> str | None:
        return self._focus_target

    def find_directives_for_npc(self, npc_id: str) -> list:
        return []


# ===========================================================================
# Model Roundtrip Tests
# ===========================================================================

class TestModelsRoundtrip:

    def test_relationship_view_roundtrip(self):
        view = NPCRelationshipView(
            npc_id="npc_a",
            target_id="player",
            trust=0.5,
            fear=0.1,
            hostility=0.2,
            respect=0.3,
            metadata={"source": "test"},
        )
        data = view.to_dict()
        restored = NPCRelationshipView.from_dict(data)
        assert restored.npc_id == "npc_a"
        assert restored.target_id == "player"
        assert restored.trust == 0.5
        assert restored.fear == 0.1
        assert restored.hostility == 0.2
        assert restored.respect == 0.3
        assert restored.metadata == {"source": "test"}

    def test_faction_alignment_view_roundtrip(self):
        view = FactionAlignmentView(
            npc_id="npc_b",
            faction_id="thieves_guild",
            alignment="aligned",
            metadata={"rank": "member"},
        )
        data = view.to_dict()
        restored = FactionAlignmentView.from_dict(data)
        assert restored.npc_id == "npc_b"
        assert restored.faction_id == "thieves_guild"
        assert restored.alignment == "aligned"
        assert restored.metadata == {"rank": "member"}

    def test_decision_context_roundtrip(self):
        ctx = NPCDecisionContext(
            npc_id="npc_c",
            intent_type="talk_to_npc",
            target_id="npc_c",
            scene_summary={"location": "tavern"},
            known_facts={"name": "Guard"},
            commitments=[{"commitment_id": "c1"}],
            recent_consequences=[{"consequence_id": "cons1"}],
            relationship=NPCRelationshipView(npc_id="npc_c", trust=0.5),
            faction_alignment=FactionAlignmentView(npc_id="npc_c", faction_id="guard_faction"),
            pacing={"social_pressure": 0.3},
            gm_context={"focus_target": "npc_c"},
            metadata={"test": True},
        )
        data = ctx.to_dict()
        restored = NPCDecisionContext.from_dict(data)
        assert restored.npc_id == "npc_c"
        assert restored.relationship.trust == 0.5
        assert restored.faction_alignment.faction_id == "guard_faction"
        assert restored.pacing == {"social_pressure": 0.3}

    def test_decision_result_roundtrip(self):
        result = NPCDecisionResult(
            npc_id="npc_d",
            outcome="agree",
            response_type="social_agreement",
            summary="NPC npc_d agreed",
            emitted_event_types=["npc_response_agreed"],
            modifiers=["trusting"],
            metadata={"x": 1},
        )
        data = result.to_dict()
        restored = NPCDecisionResult.from_dict(data)
        assert restored.npc_id == "npc_d"
        assert restored.outcome == "agree"
        assert restored.response_type == "social_agreement"
        assert restored.emitted_event_types == ["npc_response_agreed"]

    def test_decision_context_roundtrip_without_optional_fields(self):
        ctx = NPCDecisionContext(
            npc_id="npc_e",
            intent_type="talk_to_npc",
        )
        data = ctx.to_dict()
        restored = NPCDecisionContext.from_dict(data)
        assert restored.npc_id == "npc_e"
        assert restored.relationship is None
        assert restored.faction_alignment is None


# ===========================================================================
# RelationshipStateBuilder Tests
# ===========================================================================

class TestRelationshipStateBuilder:

    def test_defaults_for_unknown_npc(self):
        builder = RelationshipStateBuilder()
        cc = FakeCoherenceCore()
        view = builder.build("npc_unknown", None, cc)
        assert view.trust == 0.0
        assert view.fear == 0.0
        assert view.hostility == 0.0
        assert view.respect == 0.0

    def test_relationship_from_fact(self):
        facts = {
            "rel:npc_a:player": FakeFact(
                fact_id="rel:npc_a:player",
                subject="npc_a",
                predicate="relationship:player",
                value={"trust": 0.6, "fear": 0.1, "hostility": 0.0, "respect": 0.4},
            ),
        }
        cc = FakeCoherenceCore(facts=facts)
        builder = RelationshipStateBuilder()
        view = builder.build("npc_a", "player", cc)
        assert view.trust == 0.6
        assert view.respect == 0.4

    def test_consequences_increase_hostility(self):
        consequences = [
            FakeConsequence(
                consequence_id="c1",
                entity_ids=["npc_hostile"],
                consequence_type="npc_response_threatened",
            ),
        ]
        cc = FakeCoherenceCore(consequences=consequences)
        builder = RelationshipStateBuilder()
        view = builder.build("npc_hostile", None, cc)
        assert view.hostility > 0.0
        assert view.fear > 0.0

    def test_positive_consequences_increase_trust(self):
        consequences = [
            FakeConsequence(
                consequence_id="c1",
                entity_ids=["npc_friendly"],
                consequence_type="npc_response_agreed",
            ),
        ]
        cc = FakeCoherenceCore(consequences=consequences)
        builder = RelationshipStateBuilder()
        view = builder.build("npc_friendly", None, cc)
        assert view.trust > 0.0
        assert view.respect > 0.0


# ===========================================================================
# FactionContextBuilder Tests
# ===========================================================================

class TestFactionContextBuilder:

    def test_defaults_for_no_faction(self):
        cc = FakeCoherenceCore()
        builder = FactionContextBuilder()
        view = builder.build("npc_no_faction", cc)
        assert view.faction_id is None
        assert view.alignment == "neutral"

    def test_faction_from_fact(self):
        facts = {
            "npc_a:faction": FakeFact(
                fact_id="npc_a:faction",
                subject="npc_a",
                predicate="faction",
                value="thieves_guild",
            ),
            "faction:thieves_guild": FakeFact(
                fact_id="faction:thieves_guild",
                subject="thieves_guild",
                predicate="exists",
                value=True,
                metadata={"alignment": "chaotic"},
            ),
        }
        cc = FakeCoherenceCore(facts=facts)
        builder = FactionContextBuilder()
        view = builder.build("npc_a", cc)
        assert view.faction_id == "thieves_guild"
        assert view.alignment == "chaotic"


# ===========================================================================
# NPCDecisionPolicy Tests
# ===========================================================================

class TestNPCDecisionPolicy:

    def test_agrees_for_positive_relationship(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_friend",
            intent_type="talk_to_npc",
            relationship=NPCRelationshipView(npc_id="npc_friend", trust=0.5, respect=0.1),
        )
        result = policy.decide(ctx)
        assert result.outcome == "agree"

    def test_refuses_for_hostile_relationship(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_enemy",
            intent_type="talk_to_npc",
            relationship=NPCRelationshipView(npc_id="npc_enemy", hostility=0.6),
        )
        result = policy.decide(ctx)
        assert result.outcome == "refuse"

    def test_threatens_for_high_fear_and_hostility(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_angry",
            intent_type="talk_to_npc",
            relationship=NPCRelationshipView(npc_id="npc_angry", hostility=0.5, fear=0.5),
        )
        result = policy.decide(ctx)
        assert result.outcome == "threaten"

    def test_delays_for_fearful_npc(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_scared",
            intent_type="talk_to_npc",
            relationship=NPCRelationshipView(npc_id="npc_scared", fear=0.5),
        )
        result = policy.decide(ctx)
        assert result.outcome == "delay"

    def test_assists_for_trusted_and_respected(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_ally",
            intent_type="talk_to_npc",
            relationship=NPCRelationshipView(npc_id="npc_ally", trust=0.5, respect=0.5),
        )
        result = policy.decide(ctx)
        assert result.outcome == "assist"

    def test_neutral_npc_agrees_by_default(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_neutral",
            intent_type="talk_to_npc",
        )
        result = policy.decide(ctx)
        assert result.outcome == "agree"

    def test_gm_focus_redirects_refusal(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_focused",
            intent_type="talk_to_npc",
            relationship=NPCRelationshipView(npc_id="npc_focused", hostility=0.5),
            gm_context={"focus_target": "npc_focused"},
        )
        result = policy.decide(ctx)
        assert result.outcome == "redirect"

    def test_high_social_pressure_delays(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_pressured",
            intent_type="talk_to_npc",
            relationship=NPCRelationshipView(npc_id="npc_pressured", trust=0.1),
            pacing={"social_pressure": 0.6},
        )
        result = policy.decide(ctx)
        assert result.outcome == "delay"

    def test_default_result_for_non_social_intent(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_x",
            intent_type="other_action",
        )
        result = policy.decide(ctx)
        assert result.outcome == "agree"
        assert "default" in result.modifiers

    def test_result_has_correct_response_type(self):
        policy = NPCDecisionPolicy()
        ctx = NPCDecisionContext(
            npc_id="npc_r",
            intent_type="talk_to_npc",
            relationship=NPCRelationshipView(npc_id="npc_r", hostility=0.5, fear=0.5),
        )
        result = policy.decide(ctx)
        assert result.response_type == "social_threat"


# ===========================================================================
# NPCResponseBuilder Tests
# ===========================================================================

class TestNPCResponseBuilder:

    def test_builds_agree_events(self):
        builder = NPCResponseBuilder()
        decision = NPCDecisionResult(
            npc_id="npc_a",
            outcome="agree",
            response_type="social_agreement",
            summary="NPC npc_a agreed",
        )
        events = builder.build_events(decision, {"target_id": "npc_a"})
        assert len(events) == 2
        assert events[0]["type"] == "npc_interaction_started"
        assert events[1]["type"] == "npc_response_agreed"

    def test_builds_refusal_event(self):
        builder = NPCResponseBuilder()
        decision = NPCDecisionResult(
            npc_id="npc_b",
            outcome="refuse",
            response_type="social_refusal",
            summary="NPC npc_b refused",
        )
        events = builder.build_events(decision, {"target_id": "npc_b"})
        assert len(events) == 2
        assert events[1]["type"] == "npc_response_refused"

    def test_builds_delay_events(self):
        builder = NPCResponseBuilder()
        decision = NPCDecisionResult(
            npc_id="npc_c",
            outcome="delay",
            response_type="social_delay",
            summary="NPC npc_c delayed",
        )
        events = builder.build_events(decision, {"target_id": "npc_c"})
        assert events[1]["type"] == "npc_response_delayed"

    def test_builds_threat_events(self):
        builder = NPCResponseBuilder()
        decision = NPCDecisionResult(
            npc_id="npc_d",
            outcome="threaten",
            response_type="social_threat",
            summary="NPC npc_d threatened",
        )
        events = builder.build_events(decision, {"target_id": "npc_d"})
        assert events[1]["type"] == "npc_response_threatened"

    def test_builds_redirect_events(self):
        builder = NPCResponseBuilder()
        decision = NPCDecisionResult(
            npc_id="npc_e",
            outcome="redirect",
            response_type="social_redirect",
            summary="NPC npc_e redirected",
        )
        events = builder.build_events(decision, {"target_id": "npc_e"})
        assert events[1]["type"] == "npc_response_redirected"

    def test_builds_assist_events(self):
        builder = NPCResponseBuilder()
        decision = NPCDecisionResult(
            npc_id="npc_f",
            outcome="assist",
            response_type="social_offer",
            summary="NPC npc_f assisted",
        )
        events = builder.build_events(decision, {"target_id": "npc_f"})
        assert events[1]["type"] == "npc_response_agreed"

    def test_builds_suspicious_events_as_delayed(self):
        builder = NPCResponseBuilder()
        decision = NPCDecisionResult(
            npc_id="npc_g",
            outcome="suspicious",
            response_type="social_delay",
            summary="NPC npc_g is suspicious",
        )
        events = builder.build_events(decision, {"target_id": "npc_g"})
        assert events[1]["type"] == "npc_response_delayed"

    def test_all_emitted_event_types_are_supported(self):
        builder = NPCResponseBuilder()
        for outcome in ["agree", "refuse", "delay", "threaten", "assist", "redirect", "suspicious"]:
            decision = NPCDecisionResult(
                npc_id="npc_test",
                outcome=outcome,
                response_type="test",
                summary="test",
            )
            events = builder.build_events(decision, {"target_id": "npc_test"})
            for event in events:
                assert event["type"] in SUPPORTED_NPC_EVENT_TYPES, (
                    f"Event type {event['type']} from outcome '{outcome}' not in SUPPORTED_NPC_EVENT_TYPES"
                )


# ===========================================================================
# NPCAgencyEngine Tests
# ===========================================================================

class TestNPCAgencyEngine:

    def test_resolves_social_interaction_deterministically(self):
        cc = FakeCoherenceCore()
        gm = FakeGMState()
        engine = NPCAgencyEngine()
        mapped_action = {
            "intent_type": "talk_to_npc",
            "resolution_type": "social_contact",
            "target_id": "npc_test",
            "summary": "Talk to NPC npc_test",
        }
        result = engine.resolve_social_interaction(mapped_action, cc, gm)
        assert "context" in result
        assert "decision" in result
        assert "events" in result
        assert result["decision"]["npc_id"] == "npc_test"
        assert len(result["events"]) >= 1

    def test_deterministic_same_input_same_output(self):
        cc = FakeCoherenceCore()
        gm = FakeGMState()
        engine = NPCAgencyEngine()
        mapped_action = {
            "intent_type": "talk_to_npc",
            "resolution_type": "social_contact",
            "target_id": "npc_stable",
            "summary": "Talk to NPC npc_stable",
        }
        result1 = engine.resolve_social_interaction(mapped_action, cc, gm)
        result2 = engine.resolve_social_interaction(mapped_action, cc, gm)
        assert result1["decision"] == result2["decision"]
        assert result1["events"] == result2["events"]

    def test_hostile_npc_produces_refusal(self):
        consequences = [
            FakeConsequence(
                consequence_id="c1",
                entity_ids=["npc_hostile"],
                consequence_type="npc_response_threatened",
            ),
            FakeConsequence(
                consequence_id="c2",
                entity_ids=["npc_hostile"],
                consequence_type="npc_response_threatened",
            ),
            FakeConsequence(
                consequence_id="c3",
                entity_ids=["npc_hostile"],
                consequence_type="npc_response_refused",
            ),
        ]
        cc = FakeCoherenceCore(consequences=consequences)
        gm = FakeGMState()
        engine = NPCAgencyEngine()
        mapped_action = {
            "intent_type": "talk_to_npc",
            "resolution_type": "social_contact",
            "target_id": "npc_hostile",
            "summary": "Talk to NPC npc_hostile",
        }
        result = engine.resolve_social_interaction(mapped_action, cc, gm)
        outcome = result["decision"]["outcome"]
        # With multiple hostile consequences, the NPC should refuse, threaten, or delay
        assert outcome in ("refuse", "threaten", "delay"), f"Expected hostile outcome, got {outcome}"

    def test_context_includes_gm_focus(self):
        cc = FakeCoherenceCore()
        gm = FakeGMState(focus_target="npc_focused")
        engine = NPCAgencyEngine()
        mapped_action = {
            "intent_type": "talk_to_npc",
            "resolution_type": "social_contact",
            "target_id": "npc_focused",
            "summary": "Talk to NPC npc_focused",
        }
        result = engine.resolve_social_interaction(mapped_action, cc, gm)
        context = result["context"]
        assert context["gm_context"].get("focus_target") == "npc_focused"

    def test_unknown_npc_falls_back_safely(self):
        cc = FakeCoherenceCore()
        gm = FakeGMState()
        engine = NPCAgencyEngine()
        mapped_action = {
            "intent_type": "talk_to_npc",
            "resolution_type": "social_contact",
            "target_id": None,
            "summary": "Talk to unknown NPC",
        }
        result = engine.resolve_social_interaction(mapped_action, cc, gm)
        assert result["decision"]["npc_id"] == "unknown_npc"
        assert result["decision"]["outcome"] == "agree"
