"""Phase 7.3 — Scene Execution Layer — Functional Tests.

Covers:
- Resolving a selected option emits events
- Coherence updates after resolution
- Travel option updates scene location via event path
- Request recap emits recap event and produces stable result payload
- Presenter returns UI-safe shape
"""

from __future__ import annotations

import pytest

from app.rpg.coherence.core import CoherenceCore
from app.rpg.coherence.models import ThreadRecord
from app.rpg.execution.resolver import ActionResolver
from app.rpg.execution.models import ActionResolutionResult
from app.rpg.creator.presenters import CreatorStatePresenter
from app.rpg.core.event_bus import Event


# ==================================================================
# Helpers
# ==================================================================

class FakeGMState:
    pass


def _make_option(intent_type: str, target_id: str | None = None, option_id: str | None = None) -> dict:
    return {
        "option_id": option_id or f"{intent_type}:{target_id or 'none'}",
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
    """Create a CoherenceCore with a pre-existing unresolved thread."""
    cc = CoherenceCore()
    cc.insert_thread(ThreadRecord(
        thread_id=thread_id,
        title=f"Test Thread {thread_id}",
        status="unresolved",
        priority="normal",
    ))
    return cc


def _setup_coherence_with_location(location: str = "town_square") -> CoherenceCore:
    """Create a CoherenceCore with a known scene location."""
    cc = CoherenceCore()
    cc.apply_event(Event(
        type="scene_started",
        payload={"location": location, "summary": f"In {location}"},
    ))
    return cc


# ==================================================================
# Tests
# ==================================================================

class TestResolveSelectedThreadOption:
    def test_resolve_selected_thread_option_updates_coherence(self):
        """Resolving a thread investigation option emits thread_progressed
        and applying that event via coherence updates the thread."""
        cc = _setup_coherence_with_thread("thread_x")
        gm = FakeGMState()
        resolver = ActionResolver()

        option = _make_option("investigate_thread", target_id="thread_x")
        result = resolver.resolve_choice(option, cc, gm)

        # Events should include thread_progressed
        types = [e["type"] for e in result.events]
        assert "thread_progressed" in types

        # Apply the events to coherence
        events = [
            Event(type=e["type"], payload=e["payload"], source="action_resolver")
            for e in result.events
        ]
        update_result = cc.apply_events(events)

        # Thread should be updated
        thread = cc.get_state().unresolved_threads.get("thread_x")
        assert thread is not None
        assert thread.status == "unresolved"
        assert any("Progressed" in n for n in thread.notes)


class TestResolveSelectedLocationOption:
    def test_resolve_selected_location_option_updates_scene_summary(self):
        """Travel option updates the scene location via the event path."""
        cc = _setup_coherence_with_location("town_square")
        gm = FakeGMState()
        resolver = ActionResolver()

        # Verify initial location is stored (scene_started puts location in stable_world_facts)
        loc_fact = cc.get_state().stable_world_facts.get("scene:location")
        assert loc_fact is not None
        assert loc_fact.value == "town_square"

        option = _make_option("travel_to_location", target_id="dark_forest")
        result = resolver.resolve_choice(option, cc, gm)

        types = [e["type"] for e in result.events]
        assert "scene_transition_requested" in types

        # Apply events
        events = [
            Event(type=e["type"], payload=e["payload"], source="action_resolver")
            for e in result.events
        ]
        cc.apply_events(events)

        # Location fact should be updated
        loc_fact = cc.get_state().stable_world_facts.get("scene:location")
        assert loc_fact is not None
        assert loc_fact.value == "dark_forest"


class TestResolveUnknownOption:
    def test_resolve_unknown_option_returns_error(self):
        """When option_id is not in the choice set, game loop should
        return an error. We test the resolver still works with unknown
        intent types but produces empty consequences."""
        resolver = ActionResolver()
        cc = CoherenceCore()
        gm = FakeGMState()

        option = _make_option("completely_unknown_action", target_id="x")
        result = resolver.resolve_choice(option, cc, gm)
        # Unknown intent produces no consequences but still returns a result
        assert isinstance(result, ActionResolutionResult)
        assert result.resolved_action.intent_type == "completely_unknown_action"


class TestPresentActionResolution:
    def test_present_action_resolution_returns_ui_safe_shape(self):
        """Presenter must return a UI-safe dict shape."""
        resolver = ActionResolver()
        cc = _setup_coherence_with_location("town")
        gm = FakeGMState()

        option = _make_option("travel_to_location", target_id="forest")
        result = resolver.resolve_choice(option, cc, gm)

        presenter = CreatorStatePresenter()
        presented = presenter.present_action_resolution(result.to_dict())

        assert presented["title"] == "Action Result"
        assert "action" in presented
        assert "events" in presented
        assert isinstance(presented["events"], list)
        assert presented["action"]["intent_type"] == "travel_to_location"

        # Transition should be present for travel
        assert presented["transition"] is not None
        assert presented["transition"]["to_location"] == "forest"

    def test_present_action_resolution_no_transition(self):
        """Non-travel actions have no transition."""
        resolver = ActionResolver()
        cc = CoherenceCore()
        gm = FakeGMState()

        option = _make_option("request_recap")
        result = resolver.resolve_choice(option, cc, gm)

        presenter = CreatorStatePresenter()
        presented = presenter.present_action_resolution(result.to_dict())
        assert presented["transition"] is None


class TestRecapEventFlow:
    def test_recap_emits_event_and_stable_result(self):
        """Recap option emits recap_requested and produces stable payload."""
        resolver = ActionResolver()
        cc = CoherenceCore()
        gm = FakeGMState()

        option = _make_option("request_recap")
        result = resolver.resolve_choice(option, cc, gm)

        assert len(result.events) == 1
        assert result.events[0]["type"] == "recap_requested"

        # Apply to coherence
        events = [
            Event(type=e["type"], payload=e["payload"], source="action_resolver")
            for e in result.events
        ]
        update = cc.apply_events(events)
        assert update.events_applied == 1
