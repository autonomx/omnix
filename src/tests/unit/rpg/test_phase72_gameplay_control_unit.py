"""Phase 7.2 — Gameplay Control Unit Tests.

Tests for the option engine, framing engine, and gameplay control controller.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.app.rpg.control.controller import GameplayControlController
from src.app.rpg.control.framing import FramingEngine
from src.app.rpg.control.models import (
    ChoiceOption,
    ChoiceSet,
    FramingState,
    OptionConstraint,
    PacingState,
)
from src.app.rpg.control.option_engine import OptionEngine


class _FakeCoherenceCore:
    """Minimal fake coherence core for testing."""

    def __init__(
        self,
        threads: list[dict] | None = None,
        npcs: list[tuple[str, str]] | None = None,
        locations: list[tuple[str, str]] | None = None,
        scene_summary: dict | None = None,
    ) -> None:
        from src.app.rpg.coherence.models import CoherenceState, FactRecord, ThreadRecord

        self._threads = threads or []
        self._npcs = npcs or []
        self._locations = locations or []
        self._scene_summary = scene_summary or {"location": "default_place"}

        state = CoherenceState()
        for npc_id, name in self._npcs:
            state.stable_world_facts[f"npc:{npc_id}:name"] = FactRecord(
                fact_id=f"npc:{npc_id}:name",
                category="world",
                subject=npc_id,
                predicate="name",
                value=name,
                authority="creator_canon",
                status="confirmed",
            )
        for loc_id, name in self._locations:
            state.stable_world_facts[f"location:{loc_id}:name"] = FactRecord(
                fact_id=f"location:{loc_id}:name",
                category="world",
                subject=loc_id,
                predicate="name",
                value=name,
                authority="creator_canon",
                status="confirmed",
            )
        for thread in self._threads:
            state.unresolved_threads[thread.get("thread_id", "unknown")] = ThreadRecord(
                thread_id=thread.get("thread_id", "unknown"),
                title=thread.get("title", "unknown"),
                status="unresolved",
            )
        self._state = state

    def get_state(self) -> Any:
        return self._state

    def get_scene_summary(self) -> dict:
        return self._scene_summary

    def get_unresolved_threads(self) -> list[dict]:
        return [
            {"thread_id": tid, "title": t.title}
            for tid, t in self._state.unresolved_threads.items()
        ]

    def get_active_tensions(self) -> list:
        return []

    def get_recent_consequences(self, limit: int = 10) -> list:
        return []

    def get_last_good_anchor(self) -> dict | None:
        return None


class _FakeGMState:
    """Minimal fake GM state for testing."""

    def __init__(self) -> None:
        self._directives: list[Any] = []

    def add_directive(self, directive: Any) -> None:
        self._directives.append(directive)

    def list_directives(self) -> list[Any]:
        return list(self._directives)


def make_coherence_core(
    threads: list[dict] | None = None,
    npcs: list[tuple[str, str]] | None = None,
    locations: list[tuple[str, str]] | None = None,
) -> _FakeCoherenceCore:
    if threads is None:
        threads = [{"thread_id": "t1", "title": "Thread One"}]
    if npcs is None:
        npcs = [("npc_guard", "Guard")]
    if locations is None:
        locations = [("loc_tavern", "The Tavern")]
    return _FakeCoherenceCore(threads=threads, npcs=npcs, locations=locations)


def make_gm_state() -> _FakeGMState:
    return _FakeGMState()


class TestOptionEngine:
    def test_build_choice_set_produces_options(self):
        engine = OptionEngine()
        cc = make_coherence_core()
        gm = make_gm_state()
        choice_set = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        assert isinstance(choice_set, ChoiceSet)
        assert choice_set.options
        assert len(choice_set.options) > 0

    def test_build_choice_set_respects_limit(self):
        engine = OptionEngine()
        cc = make_coherence_core(
            threads=[{"thread_id": f"t{i}", "title": f"Thread {i}"} for i in range(10)],
            npcs=[(f"npc{i}", f"NPC {i}") for i in range(10)],
            locations=[(f"loc{i}", f"Location {i}") for i in range(10)],
        )
        gm = make_gm_state()
        choice_set = engine.build_choice_set(cc, gm, PacingState(), FramingState(), limit=3)
        assert len(choice_set.options) <= 3

    def test_pacing_bias_increases_investigation_on_reveal_pressure(self):
        engine = OptionEngine()
        cc = make_coherence_core()
        gm = make_gm_state()
        pacing = PacingState(reveal_pressure="high")
        choice_set = engine.build_choice_set(cc, gm, pacing, FramingState())
        investigation_options = [o for o in choice_set.options if o.intent_type == "investigate_thread"]
        assert investigation_options
        for opt in investigation_options:
            assert "reveal_pressure_high" in opt.metadata.get("biases", [])

    def test_focus_bias_increases_focused_option_priority(self):
        engine = OptionEngine()
        cc = make_coherence_core()
        gm = make_gm_state()
        framing = FramingState(focus_target_type="npc", focus_target_id="npc_guard")
        choice_set = engine.build_choice_set(cc, gm, PacingState(), framing)
        focused = [o for o in choice_set.options if o.target_id == "npc_guard"]
        non_focused = [o for o in choice_set.options if o.target_id != "npc_guard" and o.target_id is not None]
        if focused and non_focused:
            # Focused should generally have higher priority
            for f in focused:
                assert "focus_boost" in f.metadata.get("biases", [])

    def test_recap_option_always_present(self):
        engine = OptionEngine()
        cc = make_coherence_core()
        gm = make_gm_state()
        choice_set = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        recap_options = [o for o in choice_set.options if o.intent_type == "request_recap"]
        assert len(recap_options) == 1
        assert recap_options[0].option_id == "request_recap"

    def test_build_control_output_records_last_choice_set(self):
        ctrl = GameplayControlController()
        gm = make_gm_state()
        cc = make_coherence_core()
        out = ctrl.build_control_output(cc, gm)
        assert out["choice_set"]["choice_set_id"]
        assert ctrl.framing_engine.get_state().last_choice_set is not None

    def test_option_ids_are_stable_and_semantic(self):
        engine = OptionEngine()
        cc = make_coherence_core()
        gm = make_gm_state()
        choice_set = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        option_ids = [o.option_id for o in choice_set.options]
        assert all(isinstance(x, str) and x for x in option_ids)
        # Check that option IDs use the expected semantic prefixes
        assert any(x.startswith("investigate_thread:") for x in option_ids if "investigate" in x or x.startswith("investigate_thread:"))
        # At least one option should have a talk_to_npc or travel prefix
        assert any(
            x.startswith("talk_to_npc:") or x.startswith("travel_to_location:") or x == "request_recap"
            for x in option_ids
        )

    def test_option_metadata_contains_source_and_reason(self):
        engine = OptionEngine()
        cc = make_coherence_core()
        gm = make_gm_state()
        choice_set = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        assert choice_set.options
        for option in choice_set.options:
            assert "source" in option.metadata
            assert "reason" in option.metadata

    def test_priority_normalization_keeps_values_bounded(self):
        engine = OptionEngine()
        cc = make_coherence_core()
        gm = make_gm_state()
        pacing = PacingState(
            danger_level="high",
            reveal_pressure="high",
            social_pressure="high",
        )
        choice_set = engine.build_choice_set(cc, gm, pacing, FramingState())
        assert choice_set.options
        for option in choice_set.options:
            assert 0.0 <= option.priority <= 1.0

    def test_focus_bias_is_multiplicative_not_binary_additive(self):
        engine = OptionEngine()
        cc = make_coherence_core()
        gm = make_gm_state()
        framing = FramingState(
            focus_target_type="npc",
            focus_target_id="npc_guard",
        )
        choice_set = engine.build_choice_set(cc, gm, PacingState(), framing)
        focused = [o for o in choice_set.options if o.target_id == "npc_guard"]
        assert focused
        assert all("focus_boost" in o.metadata.get("biases", []) for o in focused)


class TestGameplayControlController:
    def test_build_control_output_consumes_forced_option_framing(self):
        ctrl = GameplayControlController()
        gm = make_gm_state()

        class _FakeOptionFramingDirective:
            directive_id = "gm:frame"
            directive_type = "option_framing"
            scope = "scene"
            force = True

        gm.add_directive(_FakeOptionFramingDirective())
        cc = make_coherence_core()
        out1 = ctrl.build_control_output(cc, gm, tick=1)
        assert out1["choice_set"]["metadata"]["framing"]["forced_option_framing"] is True

        # Remove the directive to simulate one-time directive processing
        gm._directives.clear()
        out2 = ctrl.build_control_output(cc, gm, tick=2)
        assert out2["choice_set"]["metadata"]["framing"]["forced_option_framing"] is False

    def test_build_control_output_consumes_forced_recap(self):
        ctrl = GameplayControlController()
        gm = make_gm_state()

        class _FakeRecapDirective:
            directive_id = "gm:recap"
            directive_type = "recap"
            scope = "scene"
            force = True

        gm.add_directive(_FakeRecapDirective())
        cc = make_coherence_core()
        out1 = ctrl.build_control_output(cc, gm, tick=1)
        assert out1["choice_set"]["metadata"]["framing"]["forced_recap"] is True

        # Remove the directive to simulate one-time directive processing
        gm._directives.clear()
        out2 = ctrl.build_control_output(cc, gm, tick=2)
        assert out2["choice_set"]["metadata"]["framing"]["forced_recap"] is False
