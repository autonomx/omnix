"""Phase 7.3 — Scene Execution Layer — Unit Tests.

Covers:
- Action model roundtrip (to_dict / from_dict)
- Intent mapping for each supported option type
- Consequence generation for thread/NPC/location/recap options
- Transition generation for location travel
- Resolver emits deterministic event list
- Stable resolved action IDs
"""

from __future__ import annotations

import pytest

from app.rpg.execution.models import (
    ActionConsequence,
    ActionResolutionResult,
    ResolvedAction,
    SceneTransition,
)
from app.rpg.execution.intent_mapping import ActionIntentMapper
from app.rpg.execution.consequences import ConsequenceBuilder
from app.rpg.execution.transitions import SceneTransitionBuilder
from app.rpg.execution.resolver import ActionResolver, SUPPORTED_EVENT_TYPES


# ==================================================================
# Helpers / fixtures
# ==================================================================

class FakeCoherenceCore:
    """Minimal stand-in for CoherenceCore in tests."""

    def __init__(self, location: str | None = "town_square", threads: list | None = None):
        self._location = location
        self._threads = threads or []

    def get_scene_summary(self) -> dict:
        return {"location": self._location, "present_actors": ["npc_1"]}

    def get_unresolved_threads(self) -> list:
        return self._threads

    def get_state(self):
        class _S:
            stable_world_facts = {}
            unresolved_threads = {}
        return _S()


class FakeGMState:
    """Minimal stand-in for GMDirectiveState."""
    pass


def _make_option_dict(
    option_id: str = "opt1",
    intent_type: str = "investigate_thread",
    target_id: str | None = "thread_x",
    resolution_type: str | None = "thread_progress",
) -> dict:
    return {
        "option_id": option_id,
        "label": f"Test: {intent_type}",
        "intent_type": intent_type,
        "summary": f"Do {intent_type}",
        "target_id": target_id,
        "tags": [],
        "constraints": [],
        "priority": 0.5,
        "selected": False,
        "resolution_type": resolution_type,
        "metadata": {},
    }


# ==================================================================
# Model roundtrip tests
# ==================================================================

class TestActionConsequenceRoundtrip:
    def test_action_consequence_roundtrip(self):
        c = ActionConsequence(
            consequence_id="c1",
            consequence_type="thread_progressed",
            summary="Progressed thread X",
            event_type="thread_progressed",
            payload={"thread_id": "x"},
            metadata={"foo": "bar"},
        )
        d = c.to_dict()
        c2 = ActionConsequence.from_dict(d)
        assert c2.consequence_id == "c1"
        assert c2.consequence_type == "thread_progressed"
        assert c2.event_type == "thread_progressed"
        assert c2.payload == {"thread_id": "x"}
        assert c2.metadata == {"foo": "bar"}
        assert c2.to_dict() == d


class TestSceneTransitionRoundtrip:
    def test_scene_transition_roundtrip(self):
        t = SceneTransition(
            transition_id="t1",
            transition_type="location_travel",
            from_location="town",
            to_location="forest",
            summary="Travel from town to forest",
            metadata={"key": "val"},
        )
        d = t.to_dict()
        t2 = SceneTransition.from_dict(d)
        assert t2.transition_id == "t1"
        assert t2.from_location == "town"
        assert t2.to_location == "forest"
        assert t2.to_dict() == d

    def test_scene_transition_none_locations(self):
        t = SceneTransition(
            transition_id="t2",
            transition_type="location_travel",
        )
        d = t.to_dict()
        assert d["from_location"] is None
        assert d["to_location"] is None
        t2 = SceneTransition.from_dict(d)
        assert t2.from_location is None


class TestResolvedActionRoundtrip:
    def test_resolved_action_roundtrip(self):
        consequence = ActionConsequence(
            consequence_id="c1",
            consequence_type="thread_progressed",
            summary="ok",
            event_type="thread_progressed",
        )
        transition = SceneTransition(
            transition_id="t1",
            transition_type="location_travel",
            from_location="a",
            to_location="b",
        )
        ra = ResolvedAction(
            action_id="a1",
            option_id="opt1",
            intent_type="investigate_thread",
            target_id="thread_x",
            summary="Investigating",
            consequences=[consequence],
            transition=transition,
            metadata={"debug": True},
        )
        d = ra.to_dict()
        ra2 = ResolvedAction.from_dict(d)
        assert ra2.action_id == "a1"
        assert len(ra2.consequences) == 1
        assert ra2.transition is not None
        assert ra2.transition.to_location == "b"
        assert ra2.to_dict() == d

    def test_resolved_action_no_transition(self):
        ra = ResolvedAction(
            action_id="a2",
            option_id="opt2",
            intent_type="request_recap",
        )
        d = ra.to_dict()
        assert d["transition"] is None
        ra2 = ResolvedAction.from_dict(d)
        assert ra2.transition is None


class TestActionResolutionResultRoundtrip:
    def test_full_roundtrip(self):
        result = ActionResolutionResult(
            resolved_action=ResolvedAction(
                action_id="a1",
                option_id="opt1",
                intent_type="investigate_thread",
            ),
            events=[{"type": "thread_progressed", "payload": {"thread_id": "t1"}}],
            trace={"mapped_action": {"intent_type": "investigate_thread"}},
        )
        d = result.to_dict()
        r2 = ActionResolutionResult.from_dict(d)
        assert r2.resolved_action.action_id == "a1"
        assert len(r2.events) == 1
        assert r2.trace["mapped_action"]["intent_type"] == "investigate_thread"


# ==================================================================
# Intent mapping tests
# ==================================================================

class TestActionIntentMapper:
    def setup_method(self):
        self.mapper = ActionIntentMapper()

    def test_intent_mapper_maps_thread_option(self):
        option = _make_option_dict(intent_type="investigate_thread", target_id="thread_x")
        result = self.mapper.map_option(option)
        assert result["intent_type"] == "investigate_thread"
        assert result["resolution_type"] == "thread_progress"
        assert result["target_id"] == "thread_x"

    def test_intent_mapper_maps_npc_option(self):
        option = _make_option_dict(intent_type="talk_to_npc", target_id="npc_1")
        result = self.mapper.map_option(option)
        assert result["intent_type"] == "talk_to_npc"
        assert result["resolution_type"] == "social_contact"
        assert result["target_id"] == "npc_1"

    def test_intent_mapper_maps_location_option(self):
        option = _make_option_dict(intent_type="travel_to_location", target_id="forest")
        result = self.mapper.map_option(option)
        assert result["intent_type"] == "travel_to_location"
        assert result["resolution_type"] == "location_travel"
        assert result["target_id"] == "forest"

    def test_intent_mapper_maps_recap_option(self):
        option = _make_option_dict(intent_type="request_recap", target_id=None)
        result = self.mapper.map_option(option)
        assert result["intent_type"] == "request_recap"
        assert result["resolution_type"] == "recap"
        assert result["target_id"] is None

    def test_intent_mapper_maps_unknown_option(self):
        option = _make_option_dict(intent_type="custom_action", target_id="x", resolution_type=None)
        result = self.mapper.map_option(option)
        assert result["intent_type"] == "custom_action"
        assert result["resolution_type"] == "custom_action"

    def test_intent_mapper_handles_object_option(self):
        """Mapper works with object-based options (not just dicts)."""
        from app.rpg.control.models import ChoiceOption
        opt = ChoiceOption(
            option_id="opt1",
            label="Investigate",
            intent_type="investigate_thread",
            summary="Investigate thread_x",
            target_id="thread_x",
        )
        result = self.mapper.map_option(opt)
        assert result["intent_type"] == "investigate_thread"
        assert result["target_id"] == "thread_x"


# ==================================================================
# Consequence builder tests
# ==================================================================

class TestConsequenceBuilder:
    def setup_method(self):
        self.builder = ConsequenceBuilder()
        self.cc = FakeCoherenceCore()
        self.gm = FakeGMState()

    def test_consequence_builder_creates_thread_progress_event(self):
        mapped = {"resolution_type": "thread_progress", "target_id": "thread_x"}
        consequences = self.builder.build(mapped, self.cc, self.gm)
        assert len(consequences) == 1
        c = consequences[0]
        assert c.event_type == "thread_progressed"
        assert c.payload["thread_id"] == "thread_x"

    def test_consequence_builder_creates_npc_interaction_event(self):
        mapped = {"resolution_type": "social_contact", "target_id": "npc_1"}
        consequences = self.builder.build(mapped, self.cc, self.gm)
        assert len(consequences) == 1
        c = consequences[0]
        assert c.event_type == "npc_interaction_started"
        assert c.payload["npc_id"] == "npc_1"

    def test_consequence_builder_creates_location_travel_event(self):
        mapped = {"resolution_type": "location_travel", "target_id": "forest"}
        consequences = self.builder.build(mapped, self.cc, self.gm)
        assert len(consequences) == 1
        c = consequences[0]
        assert c.event_type == "scene_transition_requested"
        assert c.payload["location"] == "forest"

    def test_consequence_builder_creates_recap_event(self):
        mapped = {"resolution_type": "recap", "target_id": None}
        consequences = self.builder.build(mapped, self.cc, self.gm)
        assert len(consequences) == 1
        c = consequences[0]
        assert c.event_type == "recap_requested"

    def test_consequence_builder_unknown_type_returns_empty(self):
        mapped = {"resolution_type": "unknown_type", "target_id": "x"}
        consequences = self.builder.build(mapped, self.cc, self.gm)
        assert consequences == []


# ==================================================================
# Transition builder tests
# ==================================================================

class TestSceneTransitionBuilder:
    def setup_method(self):
        self.builder = SceneTransitionBuilder()

    def test_transition_builder_creates_location_transition(self):
        cc = FakeCoherenceCore(location="town")
        mapped = {"resolution_type": "location_travel", "target_id": "forest"}
        transition = self.builder.build(mapped, cc)
        assert transition is not None
        assert transition.transition_type == "location_travel"
        assert transition.from_location == "town"
        assert transition.to_location == "forest"

    def test_transition_builder_returns_none_for_non_travel(self):
        cc = FakeCoherenceCore()
        mapped = {"resolution_type": "thread_progress", "target_id": "t1"}
        transition = self.builder.build(mapped, cc)
        assert transition is None

    def test_transition_builder_handles_no_current_location(self):
        cc = FakeCoherenceCore(location=None)
        mapped = {"resolution_type": "location_travel", "target_id": "forest"}
        transition = self.builder.build(mapped, cc)
        assert transition is not None
        assert transition.from_location is None
        assert transition.to_location == "forest"


# ==================================================================
# ActionResolver tests
# ==================================================================

class TestActionResolver:
    def setup_method(self):
        self.resolver = ActionResolver()
        self.cc = FakeCoherenceCore()
        self.gm = FakeGMState()

    def test_action_resolver_builds_deterministic_events(self):
        option = _make_option_dict(
            option_id="investigate_thread:thread_x",
            intent_type="investigate_thread",
            target_id="thread_x",
        )
        result = self.resolver.resolve_choice(option, self.cc, self.gm)
        assert len(result.events) >= 1
        assert result.events[0]["type"] == "thread_progressed"
        assert result.events[0]["payload"]["thread_id"] == "thread_x"

    def test_action_resolver_stable_action_id(self):
        option = _make_option_dict(
            option_id="investigate_thread:t1",
            intent_type="investigate_thread",
            target_id="t1",
        )
        result1 = self.resolver.resolve_choice(option, self.cc, self.gm)
        result2 = self.resolver.resolve_choice(option, self.cc, self.gm)
        assert result1.resolved_action.action_id == result2.resolved_action.action_id

    def test_action_resolver_travel_emits_two_events(self):
        """Travel emits consequence event + transition event."""
        option = _make_option_dict(
            option_id="explore:forest",
            intent_type="travel_to_location",
            target_id="forest",
        )
        result = self.resolver.resolve_choice(option, self.cc, self.gm)
        types = [e["type"] for e in result.events]
        assert "scene_transition_requested" in types
        assert len(result.events) >= 1

    def test_action_resolver_recap_emits_recap_event(self):
        option = _make_option_dict(
            option_id="request_recap",
            intent_type="request_recap",
            target_id=None,
        )
        result = self.resolver.resolve_choice(option, self.cc, self.gm)
        assert len(result.events) == 1
        assert result.events[0]["type"] == "recap_requested"

    def test_action_resolver_npc_emits_interaction_event(self):
        option = _make_option_dict(
            option_id="talk_to_npc:npc_1",
            intent_type="talk_to_npc",
            target_id="npc_1",
        )
        result = self.resolver.resolve_choice(option, self.cc, self.gm)
        assert len(result.events) == 1
        assert result.events[0]["type"] == "npc_interaction_started"

    def test_action_resolver_result_has_trace(self):
        option = _make_option_dict()
        result = self.resolver.resolve_choice(option, self.cc, self.gm)
        assert "mapped_action" in result.trace
        assert "consequence_count" in result.trace

    def test_action_resolver_emits_only_supported_event_types(self):
        """All events emitted by the resolver must be in SUPPORTED_EVENT_TYPES."""
        for intent in ["investigate_thread", "talk_to_npc", "travel_to_location", "request_recap"]:
            option = _make_option_dict(intent_type=intent, target_id="target")
            result = self.resolver.resolve_choice(option, self.cc, self.gm)
            for event in result.events:
                assert event["type"] in SUPPORTED_EVENT_TYPES, (
                    f"Event type {event['type']!r} not in SUPPORTED_EVENT_TYPES"
                )

    def test_action_resolver_to_dict_roundtrip(self):
        option = _make_option_dict()
        result = self.resolver.resolve_choice(option, self.cc, self.gm)
        d = result.to_dict()
        r2 = ActionResolutionResult.from_dict(d)
        assert r2.resolved_action.action_id == result.resolved_action.action_id
        assert len(r2.events) == len(result.events)
