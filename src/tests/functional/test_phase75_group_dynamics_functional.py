"""Functional tests for Phase 7.5 — Multi-Actor Interaction & Group Dynamics.

Covers social interaction yielding primary + secondary events,
group dynamics payload in action resolution, coherence recording
secondary/group consequences, and presenter UI-safe group output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.rpg.coherence.reducers import REDUCERS, reduce_event
from app.rpg.creator.presenters import CreatorStatePresenter
from app.rpg.group_dynamics.group_engine import (
    SUPPORTED_GROUP_EVENT_TYPES,
    GroupDynamicsEngine,
)
from app.rpg.group_dynamics.models import (
    CrowdStateView,
    InteractionParticipant,
    SecondaryReaction,
)
from app.rpg.npc_agency.agency_engine import NPCAgencyEngine

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
        scene: dict | None = None,
    ):
        self._state = FakeState(
            stable_world_facts=facts or {},
            scene_anchors=scene_anchors or [],
            recent_consequences=consequences or [],
        )
        self._scene = scene or {}

    def get_state(self) -> FakeState:
        return self._state

    def get_scene_summary(self) -> dict:
        return self._scene

    def get_unresolved_threads(self) -> list[dict]:
        return []

    def get_entity_facts(self, entity_id: str) -> dict | None:
        result = {}
        for fid, fact in self._state.stable_world_facts.items():
            if getattr(fact, "subject", "") == entity_id:
                result[fid] = fact
        return result if result else {}


class FakeGMState:
    def __init__(self, focus_target: str | None = None):
        self._focus_target = focus_target

    def get_focus_target(self) -> str | None:
        return self._focus_target

    def find_directives_for_npc(self, npc_id: str) -> list:
        return []


def _build_scene_coherence(
    present_actors: list[str],
    active_tensions: list[str] | None = None,
    facts: dict | None = None,
) -> FakeCoherenceCore:
    anchor = {
        "present_actors": present_actors,
        "active_tensions": active_tensions or [],
    }
    npc_facts = dict(facts or {})
    for actor in present_actors:
        if actor != "player":
            key = f"npc:{actor}:name"
            if key not in npc_facts:
                npc_facts[key] = FakeFact(
                    fact_id=key, subject=actor, predicate="name", value=actor,
                )
    return FakeCoherenceCore(
        facts=npc_facts,
        scene_anchors=[anchor],
    )


# ===========================================================================
# Functional Tests
# ===========================================================================

class TestSocialInteractionWithGroupEvents:

    def test_social_interaction_with_multiple_scene_npcs_emits_group_events(self):
        """A social interaction with multiple NPCs in the scene should
        produce both primary NPC events and secondary group events."""
        core = _build_scene_coherence(present_actors=["npc_a", "npc_b", "npc_c"])
        gm = FakeGMState()

        engine = NPCAgencyEngine(
            group_dynamics_engine=GroupDynamicsEngine(),
        )
        mapped_action = {
            "target_id": "npc_a",
            "intent_type": "talk_to_npc",
            "resolution_type": "social_contact",
            "summary": "Talk to NPC A",
        }
        result = engine.resolve_social_interaction(mapped_action, core, gm)

        # Must have primary events
        assert len(result["events"]) > 0

        # Must have group dynamics result
        assert "group" in result
        group = result["group"]
        assert len(group["participants"]) >= 1

        # Events should include group event types
        event_types = {e.get("type") for e in result["events"]}
        primary_types = {"npc_interaction_started", "npc_response_agreed"}
        group_types = SUPPORTED_GROUP_EVENT_TYPES
        assert event_types & primary_types, "Should have primary NPC events"
        assert event_types & group_types, "Should have group dynamics events"


class TestActionResolutionGroupMetadata:

    def test_action_resolution_includes_group_dynamics_metadata(self):
        """When a social contact is resolved through the full resolver,
        group dynamics metadata should appear in resolved action metadata."""
        from app.rpg.execution.resolver import ActionResolver

        core = _build_scene_coherence(present_actors=["npc_a", "npc_b"])
        gm = FakeGMState()

        agency = NPCAgencyEngine(group_dynamics_engine=GroupDynamicsEngine())
        resolver = ActionResolver(npc_agency_engine=agency)

        option = {
            "option_id": "opt_1",
            "intent_type": "talk_to_npc",
            "target_id": "npc_a",
            "resolution_type": "social_contact",
            "summary": "Chat with NPC A",
            "constraints": [],
        }

        result = resolver.resolve_choice(option, core, gm)
        resolved_dict = result.to_dict()
        metadata = resolved_dict["resolved_action"]["metadata"]
        assert "group_dynamics" in metadata
        assert "participants" in metadata["group_dynamics"]
        assert "crowd_state" in metadata["group_dynamics"]


class TestRumorSeedConsequence:

    def test_rumor_seed_event_records_consequence(self):
        """A rumor_seeded event should produce a coherence consequence mutation."""
        event = {
            "type": "rumor_seeded",
            "payload": {
                "rumor_id": "rumor:npc_b:npc_a",
                "source_npc_id": "npc_b",
                "subject_id": "npc_a",
                "rumor_type": "interaction_outcome",
                "summary": "NPC B spreads a rumor about NPC A.",
                "location": "tavern",
                "source": "group_dynamics",
            },
            "event_id": "evt_100",
            "tick": 42,
            "source": "group_dynamics",
        }
        state = FakeState()
        mutations = reduce_event(state, event)
        assert len(mutations) == 1
        assert mutations[0].action == "record_consequence"
        assert mutations[0].data["consequence_type"] == "rumor_seeded"
        assert "npc_b" in mutations[0].data["entity_ids"]
        assert "npc_a" in mutations[0].data["entity_ids"]


class TestPresentGroupDynamics:

    def test_present_group_dynamics_returns_ui_safe_shape(self):
        """Presenter should return a clean, UI-safe group dynamics dict."""
        presenter = CreatorStatePresenter()
        group = {
            "participants": [
                {"npc_id": "npc_a", "role": "primary", "faction_id": None},
                {"npc_id": "npc_b", "role": "witness", "faction_id": "guild_1"},
            ],
            "crowd_state": {
                "mood": "uneasy",
                "tension": "medium",
                "support_level": "mixed",
            },
            "secondary_reactions": [
                {
                    "npc_id": "npc_b",
                    "reaction_type": "observe",
                    "summary": "NPC B observes.",
                    "modifiers": ["passive_observer"],
                }
            ],
            "rumor_seeds": [
                {
                    "rumor_id": "rumor:npc_b:npc_a",
                    "rumor_type": "interaction_outcome",
                    "summary": "Some rumor.",
                }
            ],
        }
        result = presenter.present_group_dynamics(group)
        assert "participants" in result
        assert "crowd_state" in result
        assert "secondary_reactions" in result
        assert "rumor_seeds" in result
        assert result["crowd_state"]["mood"] == "uneasy"
        assert result["participants"][0]["npc_id"] == "npc_a"
        assert result["secondary_reactions"][0]["reaction_type"] == "observe"
        assert result["rumor_seeds"][0]["rumor_id"] == "rumor:npc_b:npc_a"

    def test_present_action_resolution_with_group_dynamics(self):
        """present_action_resolution should include group_dynamics when present in metadata."""
        presenter = CreatorStatePresenter()
        resolution = {
            "resolved_action": {
                "action_id": "action:talk_to_npc:opt_1:npc_a",
                "option_id": "opt_1",
                "intent_type": "talk_to_npc",
                "target_id": "npc_a",
                "summary": "Talk",
                "consequences": [],
                "transition": None,
                "metadata": {
                    "npc_decision": {
                        "npc_id": "npc_a",
                        "outcome": "agree",
                        "response_type": "agree",
                        "summary": "Agreed",
                        "modifiers": [],
                    },
                    "group_dynamics": {
                        "participants": [
                            {"npc_id": "npc_a", "role": "primary", "faction_id": None},
                        ],
                        "crowd_state": {"mood": "neutral", "tension": "low", "support_level": "mixed"},
                        "secondary_reactions": [],
                        "rumor_seeds": [],
                    },
                },
            },
            "events": [],
        }
        result = presenter.present_action_resolution(resolution)
        assert "group_dynamics" in result
        assert result["group_dynamics"]["crowd_state"]["mood"] == "neutral"
