"""Unit tests for Phase 7.3 Scene Execution Layer.

Tests for ActionResolver constraint enforcement, blocked resolution,
event validation, and deterministic behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

import pytest

from app.rpg.execution.models import (
    ActionConsequence,
    ActionResolutionResult,
    ResolvedAction,
)
from app.rpg.execution.resolver import SUPPORTED_EVENT_TYPES, ActionResolver

# ===========================================================================
# Test Helpers
# ===========================================================================

class FakeCoherenceCore:
    """Minimal fake of CoherenceCore for testing."""

    def __init__(self, threads: list[dict] | None = None, scene: dict | None = None):
        self._threads = threads or []
        self._scene = scene or {"location": "default_loc"}

    def get_unresolved_threads(self) -> list[dict]:
        return self._threads

    def get_scene_summary(self) -> dict:
        return self._scene


class FakeGMState:
    """Minimal fake GM state for testing."""
    pass


def _make_option_dict(
    option_id: str,
    intent_type: str,
    target_id: str,
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


# ===========================================================================
# Tests
# ===========================================================================

class TestActionResolver:

    def setup_method(self):
        cc = FakeCoherenceCore(
            threads=[{"thread_id": "q1", "title": "Test Thread"}],
            scene={"location": "default_loc"},
        )
        gm = FakeGMState()
        self.resolver = ActionResolver()
        self.cc = cc
        self.gm = gm

    def test_action_resolver_builds_deterministic_events(self):
        option = _make_option_dict(
            option_id="investigate_thread:q1",
            intent_type="investigate_thread",
            target_id="q1",
            resolution_type="thread_progress",
        )
        result1 = self.resolver.resolve_choice(option, self.cc, self.gm)
        result2 = self.resolver.resolve_choice(option, self.cc, self.gm)
        assert result1.to_dict()["events"] == result2.to_dict()["events"]

    def test_action_resolver_blocks_when_constraints_fail(self):
        option = _make_option_dict(
            option_id="investigate_thread:q_missing",
            intent_type="investigate_thread",
            target_id="q_missing",
            resolution_type="thread_progress",
            constraints=[
                {
                    "constraint_id": "c1",
                    "constraint_type": "requires_thread",
                    "value": "q_missing",
                    "source": "test",
                }
            ],
        )
        result = self.resolver.resolve_choice(option, self.cc, self.gm)
        assert result.resolved_action.outcome == "blocked"
        assert result.events
        assert result.events[0]["type"] == "action_blocked"

    def test_action_resolver_validates_supported_event_types(self):
        with pytest.raises(ValueError):
            self.resolver._validate_event({"type": "not_supported", "payload": {}})

    def test_action_resolver_validates_event_payload_shape(self):
        with pytest.raises(ValueError):
            self.resolver._validate_event({"type": "thread_progressed", "payload": "bad"})

    def test_action_resolver_succeeds_when_constraints_pass(self):
        option = _make_option_dict(
            option_id="investigate_thread:q1",
            intent_type="investigate_thread",
            target_id="q1",
            resolution_type="thread_progress",
            constraints=[
                {
                    "constraint_id": "c1",
                    "constraint_type": "requires_thread",
                    "value": "q1",
                    "source": "test",
                }
            ],
        )
        result = self.resolver.resolve_choice(option, self.cc, self.gm)
        assert result.resolved_action.outcome == "success"
        assert any(e["type"] == "thread_progressed" for e in result.events)

    def test_action_resolver_recap_returns_success(self):
        option = _make_option_dict(
            option_id="recap",
            intent_type="request_recap",
            target_id="none",
            resolution_type="recap",
        )
        result = self.resolver.resolve_choice(option, self.cc, self.gm)
        assert result.resolved_action.outcome == "success"
        assert any(e["type"] == "recap_requested" for e in result.events)


class TestResolvedActionModel:

    def test_resolved_action_roundtrip(self):
        action = ResolvedAction(
            action_id="act1",
            option_id="opt1",
            intent_type="test",
            target_id="t1",
            summary="Test action",
            outcome="blocked",
        )
        d = action.to_dict()
        action2 = ResolvedAction.from_dict(d)
        assert action2.outcome == "blocked"
        assert action2.action_id == "act1"


class TestEventValidation:

    def test_validation_rejects_unknown_types(self):
        resolver = ActionResolver()
        resolver._validate_event({"type": "thread_progressed", "payload": {}})
        with pytest.raises(ValueError):
            resolver._validate_event({"type": "unknown_event", "payload": {}})

    def test_validation_accepts_known_types(self):
        resolver = ActionResolver()
        for et in SUPPORTED_EVENT_TYPES:
            resolver._validate_event({"type": et, "payload": {}})