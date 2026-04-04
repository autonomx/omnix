"""Functional tests for Phase 7.4 — NPC Agency & Social Response.

Integration-level tests covering:
- talk_to_npc option resolution through NPC agency engine
- coherence absorbing NPC response events via reducers
- action resolution payload includes NPC decision info
- presenter returns UI-safe NPC decision shape
"""

from __future__ import annotations

import pytest
from typing import Any

from app.rpg.execution.resolver import ActionResolver, SUPPORTED_EVENT_TYPES
from app.rpg.coherence.core import CoherenceCore
from app.rpg.coherence.reducers import REDUCERS
from app.rpg.npc_agency.agency_engine import NPCAgencyEngine
from app.rpg.creator.presenters import CreatorStatePresenter


def _make_option(
    intent_type: str,
    target_id: str,
    option_id: str,
    resolution_type: str = "social_contact",
    constraints: list[dict] | None = None,
) -> dict:
    return {
        "option_id": option_id,
        "intent_type": intent_type,
        "target_id": target_id,
        "resolution_type": resolution_type,
        "summary": f"Option {option_id}",
        "constraints": constraints or [],
    }


def test_talk_to_npc_option_uses_npc_agency_engine():
    """Selecting a talk_to_npc option should yield NPC-driven events."""
    cc = CoherenceCore()
    engine = NPCAgencyEngine()
    resolver = ActionResolver(npc_agency_engine=engine)

    option = _make_option(
        "talk_to_npc",
        target_id="guard_1",
        option_id="talk_to_npc:guard_1",
        resolution_type="social_contact",
    )
    result = resolver.resolve_choice(option, cc, None)

    # Should have NPC agency events, not generic npc_interaction_started only
    event_types = [e["type"] for e in result.events]
    assert "npc_interaction_started" in event_types
    # Should have an NPC response event
    npc_response_events = [
        t for t in event_types if t.startswith("npc_response_")
    ]
    assert len(npc_response_events) >= 1

    # NPC decision should be in trace
    assert "npc_decision" in result.trace


def test_npc_response_event_updates_coherence_via_reducer():
    """NPC response events should be processed by coherence reducers."""
    cc = CoherenceCore()
    engine = NPCAgencyEngine()
    resolver = ActionResolver(npc_agency_engine=engine)

    option = _make_option(
        "talk_to_npc",
        target_id="merchant_1",
        option_id="talk_to_npc:merchant_1",
    )
    result = resolver.resolve_choice(option, cc, None)

    # Apply events to coherence
    coherence_result = cc.apply_events(result.events)
    mutations = coherence_result.to_dict().get("mutations", [])

    # Should have at least one record_consequence mutation from NPC response
    has_npc_consequence = any(
        m.get("action") == "record_consequence"
        and "npc_response" in m.get("data", {}).get("consequence_type", "")
        for m in mutations
    )
    assert has_npc_consequence


def test_action_resolution_includes_npc_decision_trace():
    """The action resolution should include NPC decision in trace and metadata."""
    cc = CoherenceCore()
    engine = NPCAgencyEngine()
    resolver = ActionResolver(npc_agency_engine=engine)

    option = _make_option(
        "talk_to_npc",
        target_id="blacksmith_1",
        option_id="talk_to_npc:blacksmith_1",
    )
    result = resolver.resolve_choice(option, cc, None)
    result_dict = result.to_dict()

    # Check trace has npc_decision
    assert "npc_decision" in result_dict["trace"]
    npc_decision = result_dict["trace"]["npc_decision"]
    assert "npc_id" in npc_decision
    assert "outcome" in npc_decision
    assert "response_type" in npc_decision

    # Check resolved_action metadata has npc_decision
    metadata = result_dict["resolved_action"]["metadata"]
    assert "npc_decision" in metadata


def test_present_npc_decision_returns_ui_safe_payload():
    """The presenter should return a clean, UI-safe NPC decision dict."""
    presenter = CreatorStatePresenter()
    decision = {
        "npc_id": "guard_1",
        "outcome": "refuse",
        "response_type": "social_refusal",
        "summary": "NPC guard_1 refused",
        "modifiers": ["high_hostility"],
        "emitted_event_types": ["npc_response_refused"],
        "metadata": {"internal": True},
    }
    presented = presenter.present_npc_decision(decision)
    assert presented["npc_id"] == "guard_1"
    assert presented["outcome"] == "refuse"
    assert presented["response_type"] == "social_refusal"
    assert presented["summary"] == "NPC guard_1 refused"
    assert presented["modifiers"] == ["high_hostility"]
    # Should not leak internal metadata
    assert "metadata" not in presented
    assert "emitted_event_types" not in presented


def test_npc_response_event_types_registered_in_reducers():
    """All NPC response event types should be registered in REDUCERS."""
    expected = [
        "npc_response_agreed",
        "npc_response_refused",
        "npc_response_delayed",
        "npc_response_threatened",
        "npc_response_redirected",
    ]
    for event_type in expected:
        assert event_type in REDUCERS, f"{event_type} not registered in REDUCERS"


def test_npc_response_event_types_in_supported_event_types():
    """All NPC response event types should be in SUPPORTED_EVENT_TYPES."""
    expected = [
        "npc_response_agreed",
        "npc_response_refused",
        "npc_response_delayed",
        "npc_response_threatened",
        "npc_response_redirected",
    ]
    for event_type in expected:
        assert event_type in SUPPORTED_EVENT_TYPES, (
            f"{event_type} not in SUPPORTED_EVENT_TYPES"
        )
