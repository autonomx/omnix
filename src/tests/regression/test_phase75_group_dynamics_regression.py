"""Regression tests for Phase 7.5 — Multi-Actor Interaction & Group Dynamics.

Covers determinism, event-path-only behavior, whitelisted event types,
and no phantom participants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.rpg.coherence.reducers import REDUCERS
from app.rpg.group_dynamics.group_engine import (
    SUPPORTED_GROUP_EVENT_TYPES,
    GroupDynamicsEngine,
)
from app.rpg.group_dynamics.models import (
    CrowdStateView,
    InteractionParticipant,
    SecondaryReaction,
)
from app.rpg.group_dynamics.participant_finder import ParticipantFinder

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
    ):
        self._state = FakeState(
            stable_world_facts=facts or {},
            scene_anchors=scene_anchors or [],
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
) -> FakeCoherenceCore:
    anchor = {
        "present_actors": present_actors,
        "active_tensions": active_tensions or [],
    }
    return FakeCoherenceCore(
        facts=facts or {},
        scene_anchors=[anchor],
    )


# ===========================================================================
# Regression Tests
# ===========================================================================

class TestGroupDynamicsDeterminism:

    def test_group_dynamics_resolution_is_deterministic(self):
        """Same scene + same NPC interaction must yield identical group result."""
        core = _build_scene_coherence(
            present_actors=["npc_a", "npc_b", "npc_c"],
        )
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}

        results = [
            engine.resolve_group_dynamics("npc_a", decision, core)
            for _ in range(5)
        ]

        for r in results[1:]:
            assert r == results[0], "Group dynamics must be deterministic"


class TestGroupDynamicsEventPath:

    def test_group_dynamics_uses_event_path_only(self):
        """Group dynamics must not produce direct coherence mutations.
        It should only produce events (dicts with 'type' and 'payload')."""
        core = _build_scene_coherence(
            present_actors=["npc_a", "npc_b"],
        )
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)

        # result must be a dict with event list, not mutation list
        assert isinstance(result, dict)
        assert "events" in result
        for event in result["events"]:
            assert isinstance(event, dict)
            assert "type" in event
            assert "payload" in event
            # Events must not contain CoherenceMutation references
            assert "action" not in event, "Event should not be a CoherenceMutation"
            assert "target" not in event or event.get("type"), \
                "Event should have type, not mutation target"


class TestGroupEngineEmitsOnlySupportedTypes:

    def test_group_engine_emits_only_supported_group_event_types(self):
        """All events from group engine must be in the supported set."""
        core = _build_scene_coherence(
            present_actors=["npc_a", "npc_b", "npc_c"],
            active_tensions=["t1", "t2", "t3", "t4"],
        )
        engine = GroupDynamicsEngine()
        decision = {"npc_id": "npc_a", "outcome": "agree"}
        result = engine.resolve_group_dynamics("npc_a", decision, core)

        for event in result["events"]:
            assert event["type"] in SUPPORTED_GROUP_EVENT_TYPES, \
                f"Event type {event['type']} is not in supported group event types"

    def test_all_group_event_types_have_reducers(self):
        """Every supported group event type must have a registered reducer."""
        for event_type in SUPPORTED_GROUP_EVENT_TYPES:
            assert event_type in REDUCERS, \
                f"Group event type '{event_type}' has no registered reducer"


class TestParticipantFinderNoPhantoms:

    def test_participant_finder_does_not_invent_absent_npcs(self):
        """ParticipantFinder must not introduce NPCs that are not in the scene."""
        scene_actors = ["npc_a", "npc_b"]
        core = _build_scene_coherence(present_actors=scene_actors)
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)

        npc_ids = {p.npc_id for p in participants}
        # All participants must be either the primary or in the scene
        for npc_id in npc_ids:
            assert npc_id in scene_actors or npc_id == "npc_a", \
                f"Phantom NPC '{npc_id}' was introduced"

    def test_participant_finder_with_no_scene_actors(self):
        """When there are no scene actors, only the primary should exist."""
        core = _build_scene_coherence(present_actors=[])
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)
        assert len(participants) == 1
        assert participants[0].npc_id == "npc_a"
        assert participants[0].role == "primary"

    def test_participant_finder_with_primary_not_in_scene(self):
        """When primary NPC is not in the scene actor list, they should still
        be included as primary (they're the interaction target)."""
        core = _build_scene_coherence(present_actors=["npc_b", "npc_c"])
        finder = ParticipantFinder()
        participants = finder.find("npc_a", core)
        npc_ids = {p.npc_id for p in participants}
        assert "npc_a" in npc_ids
        roles = {p.npc_id: p.role for p in participants}
        assert roles["npc_a"] == "primary"
