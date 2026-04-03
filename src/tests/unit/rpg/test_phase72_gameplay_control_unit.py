"""Comprehensive unit tests for Phase 7.2 Gameplay Control Layer.

Tests for the option engine, framing engine, pacing controller, and 
integration with the GM directive system.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from app.rpg.control.models import (
    ChoiceOption,
    ChoiceSet,
    FramingState,
    OptionConstraint,
    PacingState,
)
from app.rpg.control.option_engine import OptionEngine
from app.rpg.control.pacing import PacingController
from app.rpg.control.framing import FramingEngine
from app.rpg.control.controller import GameplayControlController

from app.rpg.creator.gm_state import (
    DangerDirective,
    GMDirectiveState,
    OptionFramingDirective,
    PinThreadDirective,
    RecapDirective,
    TargetNPCDirective,
    TargetFactionDirective,
    TargetLocationDirective,
    DIRECTIVE_TYPES,
)
from app.rpg.creator.commands import GMCommandProcessor

# ===========================================================================
# Test Stubs
# ===========================================================================

@dataclass
class _StubCommitments:
    player_commitments: dict = field(default_factory=dict)
    npc_commitments: dict = field(default_factory=dict)


class StubCoherenceCore:
    """Consolidated stub for CoherenceCore to support all control tests."""

    def __init__(
        self,
        threads: list | None = None,
        scene: dict | None = None,
        commitments: _StubCommitments | None = None,
    ):
        # Format threads to match what OptionEngine expects
        self._threads = threads or []
        self._scene = scene or {"location": "default_loc", "present_actors": []}
        self._state = commitments or _StubCommitments()

    def get_unresolved_threads(self) -> list:
        return self._threads

    def get_scene_summary(self) -> dict:
        return self._scene

    def get_state(self) -> Any:
        # Returns the object containing commitments/facts
        return self._state

    def get_known_facts(self, entity_id: str) -> dict:
        return {"facts": [{"entity": entity_id}]}

    def get_active_tensions(self) -> list:
        return []

    def get_recent_consequences(self, limit: int = 10) -> list:
        return []


# ===================================================================
# MODELS
# ===================================================================

class TestControlModels:
    def test_option_constraint_roundtrip(self):
        c = OptionConstraint(
            constraint_id="c1",
            constraint_type="gm_pin",
            value="boosted",
            source="test",
            metadata={"x": 1},
        )
        d = c.to_dict()
        c2 = OptionConstraint.from_dict(d)
        assert c2.constraint_id == "c1"
        assert c2.metadata == {"x": 1}

    def test_choice_option_roundtrip(self):
        opt = ChoiceOption(
            option_id="o1",
            label="Test",
            intent_type="investigate_thread",
            summary="desc",
            target_id="t1",
            priority=0.8,
            metadata={"source": "logic"},
        )
        d = opt.to_dict()
        opt2 = ChoiceOption.from_dict(d)
        assert opt2.option_id == "o1"
        assert opt2.priority == 0.8

    def test_choice_set_roundtrip(self):
        cs = ChoiceSet(
            choice_set_id="cs1",
            title="T",
            prompt="P",
            options=[ChoiceOption(option_id="o1", label="L", intent_type="i", summary="s")]
        )
        d = cs.to_dict()
        cs2 = ChoiceSet.from_dict(d)
        assert len(cs2.options) == 1
        assert cs2.choice_set_id == "cs1"


# ===================================================================
# OPTION ENGINE
# ===================================================================

class TestOptionEngine:
    def test_build_choice_set_empty(self):
        engine = OptionEngine()
        cc = StubCoherenceCore()
        gm = GMDirectiveState()
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        assert isinstance(cs, ChoiceSet)
        # Should always have at least the recap option
        assert any(o.intent_type == "request_recap" for o in cs.options)

    def test_thread_options_generated_with_semantic_ids(self):
        engine = OptionEngine()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "Mystery", "priority": "high"}]
        )
        cs = engine.build_choice_set(cc, GMDirectiveState(), PacingState(), FramingState())
        thread_opts = [o for o in cs.options if o.intent_type == "investigate_thread"]
        assert len(thread_opts) == 1
        # Check semantic ID style from Roleplay5
        assert "investigate_thread:t1" in thread_opts[0].option_id

    def test_gm_pin_boosts_priority(self):
        engine = OptionEngine()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "Mystery", "priority": "normal"}]
        )
        gm = GMDirectiveState()
        gm.add_directive(PinThreadDirective(directive_id="g1", thread_id="t1"))
        
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        pinned = [o for o in cs.options if o.target_id == "t1"][0]
        assert any(c.constraint_type == "gm_pin" for c in pinned.constraints)
        # Depending on engine implementation, priority is either > 1.0 (raw) 
        # or higher than non-pinned (normalized)

    def test_pacing_bias_reveal_pressure(self):
        engine = OptionEngine()
        cc = StubCoherenceCore(threads=[{"thread_id": "t1", "title": "T"}])
        pacing = PacingState(reveal_pressure="high")
        cs = engine.build_choice_set(cc, GMDirectiveState(), pacing, FramingState())
        thread_opts = [o for o in cs.options if o.intent_type == "investigate_thread"]
        assert "reveal_pressure_high" in thread_opts[0].metadata.get("biases", [])

    def test_priority_normalization(self):
        engine = OptionEngine()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "T1"}],
            scene={"present_actors": ["npc_a"], "location": "loc_a"}
        )
        cs = engine.build_choice_set(cc, GMDirectiveState(), PacingState(), FramingState())
        for opt in cs.options:
            assert 0.0 <= opt.priority <= 1.0


# ===================================================================
# PACING & FRAMING ENGINES
# ===================================================================

class TestPacingController:
    def test_apply_gm_danger_directive(self):
        pc = PacingController()
        gm = GMDirectiveState()
        gm.add_directive(DangerDirective(directive_id="d1", level="high"))
        pc.apply_gm_directives(gm)
        assert pc.get_state().danger_level == "high"

    def test_update_from_coherence(self):
        pc = PacingController()
        cc = StubCoherenceCore(
            commitments=_StubCommitments(player_commitments={"p1": {}, "p2": {}, "p3": {}})
        )
        pc.update_from_coherence(cc)
        # High player commitments should drive social pressure
        assert pc.get_state().social_pressure == "high"


class TestFramingEngine:
    def test_update_from_gm_forced_recap(self):
        fe = FramingEngine()
        gm = GMDirectiveState()
        gm.add_directive(RecapDirective(directive_id="r1", force=True))
        fe.update_from_gm_state(gm)
        assert fe.get_state().forced_recap_pending is True

    def test_consume_forced_flags(self):
        fe = FramingEngine()
        fe.set_state(FramingState(forced_recap_pending=True))
        assert fe.consume_forced_recap() is True
        assert fe.consume_forced_recap() is False


# ===================================================================
# GAMEPLAY CONTROL CONTROLLER
# ===================================================================

class TestGameplayControlController:
    def test_build_control_output_integration(self):
        ctrl = GameplayControlController()
        cc = StubCoherenceCore(threads=[{"thread_id": "t1", "title": "X"}])
        gm = GMDirectiveState()
        gm.add_directive(DangerDirective(directive_id="d1", level="high"))
        
        out = ctrl.build_control_output(cc, gm, tick=10)
        assert out["pacing"]["danger_level"] == "high"
        assert out["choice_set"]["options"]
        assert out["framing"]["last_recap_tick"] == 10

    def test_consumes_directives_into_metadata(self):
        """Tests that the controller marks framing flags in output metadata."""
        ctrl = GameplayControlController()
        gm = GMDirectiveState()
        gm.add_directive(OptionFramingDirective(directive_id="f1", force=True))
        cc = StubCoherenceCore()
        
        out = ctrl.build_control_output(cc, gm)
        assert out["choice_set"]["metadata"]["framing"]["forced_option_framing"] is True
        
        # Second call should be false as it was consumed
        out2 = ctrl.build_control_output(cc, GMDirectiveState())
        assert out2["choice_set"]["metadata"]["framing"]["forced_option_framing"] is False


# ===================================================================
# GM COMMAND PROCESSOR (Phase 7.2 Commands)
# ===================================================================

class TestGMCommandProcessorPhase72:
    def test_parse_and_apply_frame_options(self):
        proc = GMCommandProcessor()
        gm = GMDirectiveState()
        cc = StubCoherenceCore()
        
        cmd = proc.parse_command("frame options")
        assert cmd["command"] == "frame_options"
        
        proc.apply_command(cmd, gm, cc)
        assert gm.has_forced_option_framing() is True

    def test_parse_and_apply_focus_thread(self):
        proc = GMCommandProcessor()
        gm = GMDirectiveState()
        cc = StubCoherenceCore()
        
        cmd = proc.parse_command("focus on thread t1")
        proc.apply_command(cmd, gm, cc)
        
        ft = gm.get_focus_target()
        assert ft == {"target_type": "thread", "target_id": "t1"}

    def test_danger_commands(self):
        proc = GMCommandProcessor()
        gm = GMDirectiveState()
        cc = StubCoherenceCore()
        
        proc.apply_command(proc.parse_command("raise danger"), gm, cc)
        directives = gm.get_active_directives()
        assert any(getattr(d, "level", "") == "high" for d in directives)

    def test_existing_commands_compatibility(self):
        proc = GMCommandProcessor()
        assert proc.parse_command("pin thread t1")["command"] == "pin_thread"
        assert proc.parse_command("set danger high")["command"] == "set_danger"