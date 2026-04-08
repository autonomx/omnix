"""Unit tests for Phase 7.5 — Multi-Actor Interaction & Group Dynamics.

Covers model roundtrips, participant finder classification, alliance logic
support/oppose rules, crowd state builder defaults, group reaction policy
deterministic reactions, rumor seed builder output, and group engine event
generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.rpg.group_dynamics.alliance_logic import AllianceLogic
from app.rpg.group_dynamics.crowd_state import CrowdStateBuilder
from app.rpg.group_dynamics.group_engine import (
    SUPPORTED_GROUP_EVENT_TYPES,
    GroupDynamicsEngine,
)
from app.rpg.group_dynamics.models import (
    CrowdStateView,
    InteractionParticipant,
    RumorSeed,
    SecondaryReaction,
)
from app.rpg.group_dynamics.participant_finder import ParticipantFinder
from app.rpg.group_dynamics.reaction_policy import GroupReactionPolicy
from app.rpg.group_dynamics.rumor_seed_builder import RumorSeedBuilder

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
class FakeState:
    stable_world_facts: dict = field(default_factory=dict)
    commitments: dict = field(default_factory=dict)
    recent_consequences: list = field(default_factory=list)
    scene_anchors: list = field(default_factory=list)
    unresolved_threads: dict = field(default_factory=dict)


class FakeCoherenceCore:
    def __init__(
        self,
        facts: dict | None = None,
        scene_anchors: list | None = None,
        consequences: list | None = None,
    ):
        self._state = FakeState(
            stable_world_facts=facts or {},
            scene_anchors=scene_anchors or [],
            recent_consequences=consequences or [],
        )

    def get_state(self) -> FakeState:
        return self._state

    def get_scene_summary(self) -> dict:
        return {}

    def get_unresolved_threads(self) -> list[dict]:
        return []


def _build_scene_coherence(
    present_actors: list[str],
    active_tensions: list[str] | None = None,
    facts: dict | None = None,
    consequences: list | None = None,
) -> FakeCoherenceCore:
    """Build a FakeCoherenceCore with a scene anchor."""
    anchor = {
        "present_actors": present_actors,
        "active_tensions": active_tensions or [],
    }
    return FakeCoherenceCore(
        facts=facts or {},
        scene_anchors=[anchor],
        consequences=consequences or [],
    )


# ===========================================================================
# Model Roundtrip Tests
# ===========================================================================

class TestInteractionParticipantRoundtrip:

    def test_interaction_participant_roundtrip(self):
        p = InteractionParticipant(
            npc_id="npc_a",
            role="ally",
            faction_id="guild_1",
            relationship_to_primary="friendly",
            relationship_to_player="neutral",
            metadata={"source": "test"},
        )
        data = p.to_dict()
        restored = InteractionParticipant.from_dict(data)
        assert restored.npc_id == "npc_a"
        assert restored.role == "ally"
        assert restored.faction_id == "guild_1"
        assert restored.relationship_to_primary == "friendly"
        assert restored.relationship_to_player == "neutral"
        assert restored.metadata == {"source": "test"}

    def test_defaults(self):
        p = InteractionParticipant(npc_id="npc_b", role="witness")
        assert p.faction_id is None
        assert p.relationship_to_primary == "neutral"
        assert p.relationship_to_player == "neutral"
        assert p.metadata == {}


class TestSecondaryReactionRoundtrip:

    def test_secondary_reaction_roundtrip(self):
        r = SecondaryReaction(
            npc_id="npc_c",
            reaction_type="support_primary",
            summary="NPC C supports the primary NPC.",
            emitted_event_types=["npc_secondary_supported"],
            modifiers=["ally_support"],
            metadata={"crowd_tension": "low"},
        )
        data = r.to_dict()
        restored = SecondaryReaction.from_dict(data)
        assert restored.npc_id == "npc_c"
        assert restored.reaction_type == "support_primary"
        assert restored.summary == "NPC C supports the primary NPC."
        assert restored.emitted_event_types == ["npc_secondary_supported"]
        assert restored.modifiers == ["ally_support"]
        assert restored.metadata == {"crowd_tension": "low"}

    def test_defaults(self):
        r = SecondaryReaction(npc_id="npc_d", reaction_type="observe", summary="Observing")
        assert r.emitted_event_types == []
        assert r.modifiers == []
        assert r.metadata == {}


class TestCrowdStateViewRoundtrip:

    def test_crowd_state_view_roundtrip(self):
        c = CrowdStateView(
            mood="uneasy",
            tension="high",
            support_level="hostile",
            present_npc_ids=["npc_a", "npc_b"],
            metadata={"source": "test"},
        )
        data = c.to_dict()
        restored = CrowdStateView.from_dict(data)
        assert restored.mood == "uneasy"
        assert restored.tension == "high"
        assert restored.support_level == "hostile"
        assert restored.present_npc_ids == ["npc_a", "npc_b"]
        assert restored.metadata == {"source": "test"}

    def test_defaults(self):
        c = CrowdStateView()
        assert c.mood == "neutral"
        assert c.tension == "low"
        assert c.support_level == "mixed"
        assert c.present_npc_ids == []


class TestRumorSeedRoundtrip:

    def test_rumor_seed_roundtrip(self):
        s = RumorSeed(
            rumor_id="rumor:npc_a:npc_b",
            source_npc_id="npc_a",
            subject_id="npc_b",
            rumor_type="interaction_outcome",
            summary="NPC A spreads word about NPC B.",
            location="tavern",
            metadata={"primary_outcome": "agree"},
        )
        data = s.to_dict()
        restored = RumorSeed.from_dict(data)
        assert restored.rumor_id == "rumor:npc_a:npc_b"
        assert restored.source_npc_id == "npc_a"
        assert restored.subject_id == "npc_b"
        assert restored.rumor_type == "interaction_outcome"
        assert restored.summary == "NPC A spreads word about NPC B."
        assert restored.location == "tavern"
        assert restored.metadata == {"primary_outcome": "agree"}

    def test_defaults(self):
        s = RumorSeed(
            rumor_id="r1",
            source_npc_id=None,
            subject_id=None,
            rumor_type="gossip",
            summary="Some gossip",
        )
        assert s.location is None
        assert s.metadata == {}


# ===========================================================================
# Participant Finder Tests
# ===========================================================================

class TestParticipantFinder:

    def test_primary_is_always_first(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b", "npc_c"])
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)
        assert participants[0].npc_id == "npc_a"
        assert participants[0].role == "primary"

    def test_participant_finder_marks_primary_and_witnesses(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b", "npc_c"])
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)
        roles = {p.npc_id: p.role for p in participants}
        assert roles["npc_a"] == "primary"
        assert roles["npc_b"] == "witness"
        assert roles["npc_c"] == "witness"

    def test_excludes_player(self):
        core = _build_scene_coherence(present_actors=["npc_a", "player", "npc_b"])
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)
        npc_ids = [p.npc_id for p in participants]
        assert "player" not in npc_ids

    def test_same_faction_classified_as_ally(self):
        facts = {
            "f1": FakeFact(fact_id="f1", subject="npc_a", predicate="faction", value="guild_1"),
            "f2": FakeFact(fact_id="f2", subject="npc_b", predicate="faction", value="guild_1"),
        }
        core = _build_scene_coherence(
            present_actors=["npc_a", "npc_b"], facts=facts
        )
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)
        npc_b = [p for p in participants if p.npc_id == "npc_b"][0]
        assert npc_b.role == "ally"

    def test_hostile_relationship_classified_as_rival(self):
        facts = {
            "f1": FakeFact(
                fact_id="f1",
                subject="npc_b",
                predicate="relationship",
                value={"target": "npc_a", "stance": "hostile"},
            ),
        }
        core = _build_scene_coherence(
            present_actors=["npc_a", "npc_b"], facts=facts
        )
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)
        npc_b = [p for p in participants if p.npc_id == "npc_b"][0]
        assert npc_b.role == "rival"

    def test_empty_scene_returns_primary_only(self):
        core = _build_scene_coherence(present_actors=[])
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)
        assert len(participants) == 1
        assert participants[0].npc_id == "npc_a"
        assert participants[0].role == "primary"

    def test_no_scene_anchors_returns_primary_only(self):
        core = FakeCoherenceCore()
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)
        assert len(participants) == 1
        assert participants[0].role == "primary"


# ===========================================================================
# Alliance Logic Tests
# ===========================================================================

class TestAllianceLogic:

    def test_alliance_logic_supports_same_faction_ally(self):
        facts = {
            "f1": FakeFact(fact_id="f1", subject="npc_a", predicate="faction", value="guild_1"),
        }
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"], facts=facts)
        logic = AllianceLogic()
        participant = InteractionParticipant(
            npc_id="npc_b", role="ally", faction_id="guild_1"
        )
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        assert logic.supports_primary(participant, decision, core) is True

    def test_ally_supports_even_without_faction(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        logic = AllianceLogic()
        participant = InteractionParticipant(npc_id="npc_b", role="ally")
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        assert logic.supports_primary(participant, decision, core) is True

    def test_rival_opposes(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        logic = AllianceLogic()
        participant = InteractionParticipant(npc_id="npc_b", role="rival")
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        assert logic.opposes_primary(participant, decision, core) is True

    def test_hostile_relationship_opposes(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        logic = AllianceLogic()
        participant = InteractionParticipant(
            npc_id="npc_b", role="witness", relationship_to_primary="hostile"
        )
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        assert logic.opposes_primary(participant, decision, core) is True

    def test_primary_does_not_support_self(self):
        core = _build_scene_coherence(present_actors=["npc_a"])
        logic = AllianceLogic()
        participant = InteractionParticipant(npc_id="npc_a", role="primary")
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        assert logic.supports_primary(participant, decision, core) is False

    def test_witness_does_not_support(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        logic = AllianceLogic()
        participant = InteractionParticipant(npc_id="npc_b", role="witness")
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        assert logic.supports_primary(participant, decision, core) is False


# ===========================================================================
# Crowd State Builder Tests
# ===========================================================================

class TestCrowdStateBuilder:

    def test_defaults_with_empty_scene(self):
        core = FakeCoherenceCore()
        builder = CrowdStateBuilder()
        crowd = builder.build(core)
        assert crowd.mood == "neutral"
        assert crowd.tension == "low"
        assert crowd.support_level == "mixed"
        assert crowd.present_npc_ids == []

    def test_mood_uneasy_with_tensions(self):
        core = _build_scene_coherence(
            present_actors=["npc_a"], active_tensions=["war_brewing"]
        )
        builder = CrowdStateBuilder()
        crowd = builder.build(core)
        assert crowd.mood == "uneasy"

    def test_tension_medium_with_two_tensions(self):
        core = _build_scene_coherence(
            present_actors=["npc_a"],
            active_tensions=["tension_1", "tension_2"],
        )
        builder = CrowdStateBuilder()
        crowd = builder.build(core)
        assert crowd.tension == "medium"

    def test_tension_high_with_many_consequences(self):
        @dataclass
        class FakeCons:
            consequence_id: str = "c1"
            def to_dict(self): return {}

        core = _build_scene_coherence(
            present_actors=["npc_a"],
            active_tensions=["t1", "t2"],
            consequences=[FakeCons(), FakeCons()],
        )
        builder = CrowdStateBuilder()
        crowd = builder.build(core)
        assert crowd.tension == "high"

    def test_present_npcs_from_anchor(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        builder = CrowdStateBuilder()
        crowd = builder.build(core)
        assert crowd.present_npc_ids == ["npc_a", "npc_b"]


# ===========================================================================
# Group Reaction Policy Tests
# ===========================================================================

class TestGroupReactionPolicy:

    def test_group_reaction_policy_generates_support_reaction(self):
        policy = GroupReactionPolicy()
        participants = [
            InteractionParticipant(npc_id="npc_a", role="primary"),
            InteractionParticipant(npc_id="npc_b", role="ally"),
        ]
        crowd = CrowdStateView()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        reactions = policy.decide(participants, decision, crowd, None)
        assert len(reactions) == 1
        assert reactions[0].npc_id == "npc_b"
        assert reactions[0].reaction_type == "support_primary"

    def test_rival_produces_oppose_reaction(self):
        policy = GroupReactionPolicy()
        participants = [
            InteractionParticipant(npc_id="npc_a", role="primary"),
            InteractionParticipant(npc_id="npc_b", role="rival"),
        ]
        crowd = CrowdStateView()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        reactions = policy.decide(participants, decision, crowd, None)
        assert len(reactions) == 1
        assert reactions[0].reaction_type == "oppose_primary"

    def test_witness_produces_observe_reaction(self):
        policy = GroupReactionPolicy()
        participants = [
            InteractionParticipant(npc_id="npc_a", role="primary"),
            InteractionParticipant(npc_id="npc_b", role="witness"),
        ]
        crowd = CrowdStateView()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        reactions = policy.decide(participants, decision, crowd, None)
        assert len(reactions) == 1
        assert reactions[0].reaction_type == "observe"

    def test_witness_in_high_tension_spreads_rumor(self):
        policy = GroupReactionPolicy()
        participants = [
            InteractionParticipant(npc_id="npc_a", role="primary"),
            InteractionParticipant(npc_id="npc_b", role="witness"),
        ]
        crowd = CrowdStateView(tension="high")
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        reactions = policy.decide(participants, decision, crowd, None)
        assert len(reactions) == 1
        assert reactions[0].reaction_type == "spread_rumor"

    def test_crowd_member_observes(self):
        policy = GroupReactionPolicy()
        participants = [
            InteractionParticipant(npc_id="npc_a", role="primary"),
            InteractionParticipant(npc_id="npc_b", role="crowd"),
        ]
        crowd = CrowdStateView()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        reactions = policy.decide(participants, decision, crowd, None)
        assert len(reactions) == 1
        assert reactions[0].reaction_type == "observe"

    def test_primary_excluded_from_reactions(self):
        policy = GroupReactionPolicy()
        participants = [
            InteractionParticipant(npc_id="npc_a", role="primary"),
        ]
        crowd = CrowdStateView()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        reactions = policy.decide(participants, decision, crowd, None)
        assert len(reactions) == 0

    def test_mixed_participants_produce_multiple_reactions(self):
        policy = GroupReactionPolicy()
        participants = [
            InteractionParticipant(npc_id="npc_a", role="primary"),
            InteractionParticipant(npc_id="npc_b", role="ally"),
            InteractionParticipant(npc_id="npc_c", role="rival"),
            InteractionParticipant(npc_id="npc_d", role="witness"),
        ]
        crowd = CrowdStateView()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        reactions = policy.decide(participants, decision, crowd, None)
        assert len(reactions) == 3
        types = {r.reaction_type for r in reactions}
        assert "support_primary" in types
        assert "oppose_primary" in types
        assert "observe" in types


# ===========================================================================
# Rumor Seed Builder Tests
# ===========================================================================

class TestRumorSeedBuilder:

    def test_rumor_seed_builder_creates_seed_from_spread_rumor_reaction(self):
        builder = RumorSeedBuilder()
        reactions = [
            SecondaryReaction(
                npc_id="npc_b",
                reaction_type="spread_rumor",
                summary="NPC B spreads a rumor.",
                emitted_event_types=["rumor_seeded"],
            ),
        ]
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        core = FakeCoherenceCore()
        seeds = builder.build(reactions, decision, core)
        assert len(seeds) == 1
        assert seeds[0].source_npc_id == "npc_b"
        assert seeds[0].subject_id == "npc_a"
        assert seeds[0].rumor_type == "interaction_outcome"

    def test_non_rumor_reaction_produces_no_seed(self):
        builder = RumorSeedBuilder()
        reactions = [
            SecondaryReaction(
                npc_id="npc_b",
                reaction_type="support_primary",
                summary="NPC B supports.",
            ),
        ]
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        core = FakeCoherenceCore()
        seeds = builder.build(reactions, decision, core)
        assert len(seeds) == 0

    def test_multiple_rumor_reactions_produce_multiple_seeds(self):
        builder = RumorSeedBuilder()
        reactions = [
            SecondaryReaction(
                npc_id="npc_b", reaction_type="spread_rumor", summary="Rumor 1"
            ),
            SecondaryReaction(
                npc_id="npc_c", reaction_type="spread_rumor", summary="Rumor 2"
            ),
        ]
        decision = {"npc_id": "npc_a", "outcome": "refuse"}
        core = FakeCoherenceCore()
        seeds = builder.build(reactions, decision, core)
        assert len(seeds) == 2
        source_ids = {s.source_npc_id for s in seeds}
        assert source_ids == {"npc_b", "npc_c"}

    def test_location_from_coherence(self):
        facts = {
            "scene:location": FakeFact(
                fact_id="scene:location", subject="scene", predicate="location", value="tavern"
            ),
        }
        core = FakeCoherenceCore(facts=facts)
        builder = RumorSeedBuilder()
        reactions = [
            SecondaryReaction(
                npc_id="npc_b", reaction_type="spread_rumor", summary="Rumor"
            ),
        ]
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        seeds = builder.build(reactions, decision, core)
        assert seeds[0].location == "tavern"


# ===========================================================================
# Group Dynamics Engine Tests
# ===========================================================================

class TestGroupDynamicsEngine:

    def test_group_engine_builds_group_events_deterministically(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b", "npc_c"])
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)

        assert "participants" in result
        assert "crowd_state" in result
        assert "secondary_reactions" in result
        assert "rumor_seeds" in result
        assert "events" in result

    def test_deterministic_same_input_same_output(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result1 = engine.resolve_group_dynamics("npc_a", decision, core)
        result2 = engine.resolve_group_dynamics("npc_a", decision, core)
        assert result1 == result2

    def test_events_have_correct_types(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)
        for event in result["events"]:
            assert event["type"] in SUPPORTED_GROUP_EVENT_TYPES

    def test_primary_always_in_participants(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)
        roles = {p["npc_id"]: p["role"] for p in result["participants"]}
        assert roles["npc_a"] == "primary"

    def test_ally_generates_support_event(self):
        facts = {
            "f1": FakeFact(fact_id="f1", subject="npc_a", predicate="faction", value="guild_1"),
            "f2": FakeFact(fact_id="f2", subject="npc_b", predicate="faction", value="guild_1"),
        }
        core = _build_scene_coherence(
            present_actors=["npc_a", "npc_b"], facts=facts
        )
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)
        event_types = [e["type"] for e in result["events"]]
        assert "npc_secondary_supported" in event_types

    def test_rival_generates_oppose_event(self):
        facts = {
            "f1": FakeFact(
                fact_id="f1",
                subject="npc_b",
                predicate="relationship",
                value={"target": "npc_a", "stance": "hostile"},
            ),
        }
        core = _build_scene_coherence(
            present_actors=["npc_a", "npc_b"], facts=facts
        )
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)
        event_types = [e["type"] for e in result["events"]]
        assert "npc_secondary_opposed" in event_types

    def test_witness_generates_observe_event(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)
        event_types = [e["type"] for e in result["events"]]
        assert "npc_secondary_observed" in event_types

    def test_high_tension_generates_rumor_event(self):
        core = _build_scene_coherence(
            present_actors=["npc_a", "npc_b"],
            active_tensions=["t1", "t2", "t3", "t4"],
        )
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)
        event_types = [e["type"] for e in result["events"]]
        assert "rumor_seeded" in event_types

    def test_empty_scene_produces_no_secondary_events(self):
        core = _build_scene_coherence(present_actors=[])
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)
        assert result["secondary_reactions"] == []
        # Only the primary participant
        assert len(result["participants"]) == 1

    def test_events_payload_includes_source(self):
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)
        for event in result["events"]:
            assert event["payload"]["source"] == "group_dynamics"
