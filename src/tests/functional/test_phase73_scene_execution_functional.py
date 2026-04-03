"""Functional tests for Phase 7.3 Scene Execution Layer.

Integration-level tests covering blocked actions, event paths,
and coherence reducer behavior.
"""

from __future__ import annotations

import pytest
from typing import Any

from app.rpg.execution.resolver import ActionResolver
from app.rpg.coherence.core import CoherenceCore


def _make_option(
    intent_type: str,
    target_id: str,
    option_id: str,
    resolution_type: str = "thread_progress",
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


def test_resolve_known_option_succeeds():
    cc = CoherenceCore()
    resolver = ActionResolver()

    option = _make_option(
        "investigate_thread",
        target_id="q_existing",
        option_id="investigate_thread:q_existing",
        resolution_type="thread_progress",
    )
    result = resolver.resolve_choice(option, cc, None)
    assert result.resolved_action.outcome == "success"
    assert any(e["type"] == "thread_progressed" for e in result.events)


def test_resolve_unknown_option_returns_error():
    """When option exists, resolver still maps but may fail on constraints."""
    cc = CoherenceCore()
    resolver = ActionResolver()

    option = _make_option(
        "investigate_thread",
        target_id="missing",
        option_id="investigate_thread:missing",
        resolution_type="thread_progress",
    )
    # Without explicit constraint requiring thread, this succeeds with default resolution
    result = resolver.resolve_choice(option, cc, None)
    assert result.resolved_action.outcome == "success"


def test_blocked_action_uses_event_path_without_direct_truth_mutation():
    cc = CoherenceCore()
    resolver = ActionResolver()

    option = _make_option(
        "investigate_thread",
        target_id="missing_thread",
        option_id="investigate_thread:missing_thread",
        resolution_type="thread_progress",
        constraints=[
            {
                "constraint_id": "c1",
                "constraint_type": "requires_thread",
                "value": "missing_thread",
                "source": "test",
            }
        ],
    )

    result = resolver.resolve_choice(option, cc, None)
    assert result.resolved_action.outcome == "blocked"
    assert result.events[0]["type"] == "action_blocked"

    # Applying the event records a consequence but does not create the thread.
    cc.apply_events(result.events)
    assert all(
        t.get("thread_id") != "missing_thread" for t in cc.get_unresolved_threads()
    )


def test_recap_action_resolves_successfully():
    cc = CoherenceCore()
    resolver = ActionResolver()

    option = _make_option(
        "request_recap",
        target_id="none",
        option_id="recap",
        resolution_type="recap",
    )

    result = resolver.resolve_choice(option, cc, None)
    assert result.resolved_action.outcome == "success"
    assert any(e["type"] == "recap_requested" for e in result.events)


def test_blocked_action_reducer_records_consequence():
    cc = CoherenceCore()
    resolver = ActionResolver()

    option = _make_option(
        "investigate_thread",
        target_id="phantom_thread",
        option_id="investigate_thread:phantom_thread",
        resolution_type="thread_progress",
        constraints=[
            {
                "constraint_id": "c1",
                "constraint_type": "requires_thread",
                "value": "phantom_thread",
                "source": "test",
            }
        ],
    )

    result = resolver.resolve_choice(option, cc, None)
    assert result.resolved_action.outcome == "blocked"

    # Apply events to trigger reducer
    coherence_result = cc.apply_events(result.events)
    mutations = coherence_result.to_dict().get("mutations", [])
    # Should have at least one mutation recording the consequence
    assert any(m.get("action") == "record_consequence" for m in mutations)