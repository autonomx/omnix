"""Phase 7.3 — Scene Execution Layer — Regression Tests.

Covers:
- Resolving same option in same state produces same events
- Resolution does not directly mutate coherence without events
- Choice selection stays stable across snapshot/restore if choice set is preserved
- Resolver does not invent unrelated event types
"""

from __future__ import annotations

import copy

import pytest

from app.rpg.coherence.core import CoherenceCore
from app.rpg.coherence.models import ThreadRecord
from app.rpg.execution.resolver import ActionResolver, SUPPORTED_EVENT_TYPES
from app.rpg.execution.models import ActionResolutionResult
from app.rpg.core.event_bus import Event


# ==================================================================
# Helpers
# ==================================================================

class FakeGMState:
    pass


def _make_option(intent_type: str, target_id: str | None = None) -> dict:
    return {
        "option_id": f"{intent_type}:{target_id or 'none'}",
        "label": f"Test: {intent_type}",
        "intent_type": intent_type,
        "summary": f"Do {intent_type}",
        "target_id": target_id,
        "tags": [],
        "constraints": [],
        "priority": 0.5,
        "selected": False,
        "resolution_type": None,
        "metadata": {},
    }


def _setup_coherence_with_thread(thread_id: str = "thread_x") -> CoherenceCore:
    cc = CoherenceCore()
    cc.insert_thread(ThreadRecord(
        thread_id=thread_id,
        title=f"Test Thread {thread_id}",
        status="unresolved",
        priority="normal",
    ))
    return cc


def _setup_coherence_with_location(location: str = "town_square") -> CoherenceCore:
    cc = CoherenceCore()
    cc.apply_event(Event(
        type="scene_started",
        payload={"location": location, "summary": f"In {location}"},
    ))
    return cc


# ==================================================================
# Regression tests
# ==================================================================

class TestActionResolutionDeterminism:
    def test_action_resolution_is_deterministic_for_same_choice_set(self):
        """Resolving the same option with the same coherence state
        must produce identical events both times."""
        resolver = ActionResolver()
        cc = _setup_coherence_with_thread("thread_x")
        gm = FakeGMState()

        option = _make_option("investigate_thread", target_id="thread_x")

        result1 = resolver.resolve_choice(option, cc, gm)
        result2 = resolver.resolve_choice(option, cc, gm)

        assert result1.to_dict()["events"] == result2.to_dict()["events"]
        assert result1.resolved_action.action_id == result2.resolved_action.action_id
        assert result1.to_dict()["resolved_action"] == result2.to_dict()["resolved_action"]

    def test_deterministic_across_all_intent_types(self):
        """All intent types produce deterministic results."""
        resolver = ActionResolver()
        cc = _setup_coherence_with_location("town")
        gm = FakeGMState()

        for intent in ["investigate_thread", "talk_to_npc", "travel_to_location", "request_recap"]:
            option = _make_option(intent, target_id="target")
            r1 = resolver.resolve_choice(option, cc, gm)
            r2 = resolver.resolve_choice(option, cc, gm)
            assert r1.to_dict() == r2.to_dict(), f"Non-deterministic for {intent}"


class TestActionResolutionUsesEventPath:
    def test_action_resolution_uses_event_path_not_direct_mutation(self):
        """Resolver must NOT mutate coherence directly. It returns events
        that the caller must apply."""
        resolver = ActionResolver()
        cc = _setup_coherence_with_location("town")
        gm = FakeGMState()

        # Take a snapshot of coherence state before
        state_before = cc.serialize_state()

        option = _make_option("travel_to_location", target_id="forest")
        result = resolver.resolve_choice(option, cc, gm)

        # Coherence state must not have changed
        state_after = cc.serialize_state()
        assert state_before == state_after, (
            "Resolver mutated coherence directly instead of returning events"
        )

        # Now apply events — state should change
        events = [
            Event(type=e["type"], payload=e["payload"], source="action_resolver")
            for e in result.events
        ]
        cc.apply_events(events)
        state_applied = cc.serialize_state()
        assert state_applied != state_before


class TestSelectedOptionStabilityAcrossRestore:
    def test_selected_option_resolution_remains_stable_after_restore(self):
        """If we serialize/deserialize the coherence state, the same option
        resolution still produces identical events."""
        resolver = ActionResolver()
        cc1 = _setup_coherence_with_location("town")
        gm = FakeGMState()

        option = _make_option("travel_to_location", target_id="forest")
        result1 = resolver.resolve_choice(option, cc1, gm)

        # Serialize and restore
        serialized = cc1.serialize_state()
        cc2 = CoherenceCore()
        cc2.deserialize_state(serialized)

        result2 = resolver.resolve_choice(option, cc2, gm)
        assert result1.to_dict()["events"] == result2.to_dict()["events"]


class TestResolverEmitsOnlySupportedEventTypes:
    def test_resolver_emits_only_supported_event_types(self):
        """The resolver must not invent event types outside the
        SUPPORTED_EVENT_TYPES set."""
        resolver = ActionResolver()
        cc = _setup_coherence_with_location("town")
        gm = FakeGMState()

        all_intents = [
            "investigate_thread",
            "talk_to_npc",
            "travel_to_location",
            "request_recap",
            "completely_unknown",
        ]

        for intent in all_intents:
            option = _make_option(intent, target_id="target")
            result = resolver.resolve_choice(option, cc, gm)
            for event in result.events:
                assert event["type"] in SUPPORTED_EVENT_TYPES, (
                    f"Unsupported event type {event['type']!r} from intent {intent!r}"
                )


class TestCoherenceNotMutatedOnRecap:
    def test_recap_does_not_mutate_location(self):
        """Recap events must not change the scene location."""
        resolver = ActionResolver()
        cc = _setup_coherence_with_location("town")
        gm = FakeGMState()

        # Verify initial location fact
        loc_fact = cc.get_state().stable_world_facts.get("scene:location")
        assert loc_fact is not None
        assert loc_fact.value == "town"

        option = _make_option("request_recap")
        result = resolver.resolve_choice(option, cc, gm)

        events = [
            Event(type=e["type"], payload=e["payload"], source="action_resolver")
            for e in result.events
        ]
        cc.apply_events(events)

        # Location fact must remain unchanged
        loc_fact = cc.get_state().stable_world_facts.get("scene:location")
        assert loc_fact is not None
        assert loc_fact.value == "town"
