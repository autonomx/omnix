"""Regression tests for Phase 7.3 Scene Execution Layer.

These tests ensure that blocked action resolution remains deterministic
and that constraint enforcement is consistently applied.
"""

from __future__ import annotations

import pytest

from app.rpg.coherence.core import CoherenceCore
from app.rpg.execution.resolver import SUPPORTED_EVENT_TYPES, ActionResolver


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


def test_resolver_emits_only_supported_event_types():
    cc = CoherenceCore()
    resolver = ActionResolver()

    # Test with a successful action
    option = _make_option(
        "investigate_thread",
        target_id="t1",
        option_id="investigate_thread:t1",
        resolution_type="thread_progress",
    )
    result = resolver.resolve_choice(option, cc, None)
    assert all(e["type"] in SUPPORTED_EVENT_TYPES for e in result.to_dict()["events"])


def test_resolver_emits_blocked_event_type_when_constraints_fail():
    cc = CoherenceCore()
    resolver = ActionResolver()

    option = _make_option(
        "investigate_thread",
        target_id="missing",
        option_id="investigate_thread:missing",
        resolution_type="thread_progress",
        constraints=[
            {
                "constraint_id": "c1",
                "constraint_type": "requires_thread",
                "value": "missing",
                "source": "test",
            }
        ],
    )
    result = resolver.resolve_choice(option, cc, None)
    assert result.events[0]["type"] in SUPPORTED_EVENT_TYPES
    assert result.events[0]["type"] == "action_blocked"


def test_blocked_action_resolution_is_deterministic_for_same_constraints():
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

    result1 = resolver.resolve_choice(option, cc, None)
    result2 = resolver.resolve_choice(option, cc, None)

    assert result1.to_dict()["events"] == result2.to_dict()["events"]
    assert result1.resolved_action.outcome == "blocked"
    assert result2.resolved_action.outcome == "blocked"


def test_resolver_does_not_mutate_state_on_blocked_action():
    """Blocked actions should only record consequences via the reducer path."""
    cc = CoherenceCore()
    resolver = ActionResolver()

    initial_threads = list(cc.get_unresolved_threads())

    option = _make_option(
        "investigate_thread",
        target_id="phantom",
        option_id="investigate_thread:phantom",
        resolution_type="thread_progress",
        constraints=[
            {
                "constraint_id": "c1",
                "constraint_type": "requires_thread",
                "value": "phantom",
                "source": "test",
            }
        ],
    )

    result = resolver.resolve_choice(option, cc, None)
    assert result.resolved_action.outcome == "blocked"

    # No new threads should exist after blocked resolution
    final_threads = list(cc.get_unresolved_threads())
    assert initial_threads == final_threads