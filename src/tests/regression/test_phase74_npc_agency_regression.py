"""Regression tests for Phase 7.4 — NPC Agency & Social Response.

Covers:
- Deterministic resolution (same state → same result)
- NPC agency uses event path, not direct mutation
- Only supported event types are emitted
- Unknown NPCs fall back safely
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any

from app.rpg.execution.resolver import ActionResolver, SUPPORTED_EVENT_TYPES
from app.rpg.coherence.core import CoherenceCore
from app.rpg.npc_agency.agency_engine import NPCAgencyEngine
from app.rpg.npc_agency.response_builder import SUPPORTED_NPC_EVENT_TYPES


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


def test_social_interaction_resolution_is_deterministic():
    """Same input state must produce the same NPC decision and events."""
    cc = CoherenceCore()
    engine = NPCAgencyEngine()
    resolver = ActionResolver(npc_agency_engine=engine)

    option = _make_option(
        "talk_to_npc",
        target_id="stable_npc",
        option_id="talk_to_npc:stable_npc",
    )

    result1 = resolver.resolve_choice(option, cc, None)
    result2 = resolver.resolve_choice(option, cc, None)

    # Decisions should be identical
    assert result1.trace.get("npc_decision") == result2.trace.get("npc_decision")

    # Event types should be identical
    types1 = [e["type"] for e in result1.events]
    types2 = [e["type"] for e in result2.events]
    assert types1 == types2


def test_npc_agency_uses_event_path_not_direct_mutation():
    """NPC agency must not directly mutate coherence — only emit events."""
    cc = CoherenceCore()
    engine = NPCAgencyEngine()
    resolver = ActionResolver(npc_agency_engine=engine)

    # Capture coherence state before
    state_before = cc.get_state()
    facts_before = dict(state_before.stable_world_facts)

    option = _make_option(
        "talk_to_npc",
        target_id="test_npc",
        option_id="talk_to_npc:test_npc",
    )
    result = resolver.resolve_choice(option, cc, None)

    # Coherence state should NOT have changed yet (before apply_events)
    state_after = cc.get_state()
    facts_after = dict(state_after.stable_world_facts)
    assert facts_before.keys() == facts_after.keys()

    # Only after apply_events should coherence be updated
    cc.apply_events(result.events)


def test_response_builder_emits_only_supported_npc_response_events():
    """All events from the response builder must be in the supported set."""
    cc = CoherenceCore()
    engine = NPCAgencyEngine()
    resolver = ActionResolver(npc_agency_engine=engine)

    option = _make_option(
        "talk_to_npc",
        target_id="any_npc",
        option_id="talk_to_npc:any_npc",
    )
    result = resolver.resolve_choice(option, cc, None)

    for event in result.events:
        event_type = event.get("type")
        assert event_type in SUPPORTED_EVENT_TYPES, (
            f"Unsupported event type emitted: {event_type}"
        )


def test_unknown_npc_social_interaction_falls_back_safely():
    """Interacting with an unknown NPC should not crash or invent data."""
    cc = CoherenceCore()
    engine = NPCAgencyEngine()
    resolver = ActionResolver(npc_agency_engine=engine)

    option = _make_option(
        "talk_to_npc",
        target_id="nonexistent_npc_xyz",
        option_id="talk_to_npc:nonexistent_npc_xyz",
    )
    result = resolver.resolve_choice(option, cc, None)

    # Should still succeed with a valid decision
    assert result.resolved_action.outcome in (
        "agree", "refuse", "delay", "threaten", "assist", "suspicious", "redirect"
    )
    assert len(result.events) >= 1

    # NPC ID in decision should match the target, not be invented
    npc_decision = result.trace.get("npc_decision", {})
    assert npc_decision.get("npc_id") == "nonexistent_npc_xyz"


def test_fallback_to_generic_consequences_without_npc_agency():
    """Without NPC agency engine, social_contact uses old generic path."""
    cc = CoherenceCore()
    resolver = ActionResolver()  # No npc_agency_engine

    option = _make_option(
        "talk_to_npc",
        target_id="fallback_npc",
        option_id="talk_to_npc:fallback_npc",
    )
    result = resolver.resolve_choice(option, cc, None)

    # Should still work via the old consequence builder path
    assert result.resolved_action.outcome == "success"
    event_types = [e["type"] for e in result.events]
    assert "npc_interaction_started" in event_types
    # Should NOT have NPC decision in trace
    assert "npc_decision" not in result.trace


def test_blocked_social_contact_does_not_use_npc_agency():
    """If constraints block the action, NPC agency should not be invoked."""
    cc = CoherenceCore()
    engine = NPCAgencyEngine()
    resolver = ActionResolver(npc_agency_engine=engine)

    option = _make_option(
        "talk_to_npc",
        target_id="blocked_npc",
        option_id="talk_to_npc:blocked_npc",
        constraints=[
            {
                "constraint_id": "c1",
                "constraint_type": "requires_location",
                "value": "unreachable_location",
            }
        ],
    )
    result = resolver.resolve_choice(option, cc, None)

    assert result.resolved_action.outcome == "blocked"
    assert "npc_decision" not in result.trace
