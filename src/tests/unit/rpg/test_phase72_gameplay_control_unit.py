"""Comprehensive unit tests for Phase 7.2 Real Gameplay Control Layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Imports under test – control package
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

# ---------------------------------------------------------------------------
# Imports under test – modified creator modules
# ---------------------------------------------------------------------------
from app.rpg.creator.gm_state import (
    DangerDirective,
    GMDirective,
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
# Lightweight stubs for CoherenceCore / CoherenceState
# ===========================================================================

@dataclass
class _StubCommitments:
    player_commitments: dict = field(default_factory=dict)
    npc_commitments: dict = field(default_factory=dict)


class StubCoherenceCore:
    """Minimal stub so OptionEngine / PacingController can read data."""

    def __init__(
        self,
        threads: list | None = None,
        scene: dict | None = None,
        commitments: _StubCommitments | None = None,
    ):
        self._threads = threads or []
        self._scene = scene or {}
        self._state = commitments or _StubCommitments()

    def get_unresolved_threads(self) -> list:
        return self._threads

    def get_scene_summary(self) -> dict:
        return self._scene

    def get_state(self) -> _StubCommitments:
        return self._state

    def get_known_facts(self, entity_id: str) -> dict:
        return {"facts": [{"entity": entity_id}]}

    def get_active_tensions(self) -> list:
        return []


# ===================================================================
# MODELS
# ===================================================================


class TestOptionConstraint:
    def test_roundtrip(self):
        c = OptionConstraint(
            constraint_id="c1",
            constraint_type="gm_pin",
            value="boosted",
            source="test",
            metadata={"x": 1},
        )
        d = c.to_dict()
        assert d["constraint_id"] == "c1"
        c2 = OptionConstraint.from_dict(d)
        assert c2.constraint_id == "c1"
        assert c2.metadata == {"x": 1}

    def test_defaults(self):
        c = OptionConstraint(constraint_id="c2", constraint_type="t", value="v", source="s")
        assert c.metadata == {}


class TestChoiceOption:
    def test_roundtrip(self):
        opt = ChoiceOption(
            option_id="o1",
            label="Test",
            intent_type="investigate_thread",
            summary="desc",
            target_id="t1",
            tags=["a"],
            constraints=[
                OptionConstraint(constraint_id="c1", constraint_type="t", value="v", source="s")
            ],
            priority=2.0,
            metadata={"k": "v"},
        )
        d = opt.to_dict()
        assert d["option_id"] == "o1"
        assert len(d["constraints"]) == 1
        opt2 = ChoiceOption.from_dict(d)
        assert opt2.option_id == "o1"
        assert len(opt2.constraints) == 1
        assert isinstance(opt2.constraints[0], OptionConstraint)

    def test_defaults(self):
        opt = ChoiceOption(option_id="o2", label="L", intent_type="i", summary="s")
        assert opt.target_id is None
        assert opt.tags == []
        assert opt.constraints == []
        assert opt.priority == 0.0
        assert opt.metadata == {}


class TestChoiceSet:
    def test_roundtrip(self):
        cs = ChoiceSet(
            choice_set_id="cs1",
            title="T",
            prompt="P",
            options=[
                ChoiceOption(option_id="o1", label="L", intent_type="i", summary="s")
            ],
            source_summary={"k": 1},
        )
        d = cs.to_dict()
        assert d["choice_set_id"] == "cs1"
        assert len(d["options"]) == 1
        cs2 = ChoiceSet.from_dict(d)
        assert cs2.choice_set_id == "cs1"
        assert len(cs2.options) == 1
        assert isinstance(cs2.options[0], ChoiceOption)

    def test_empty_options(self):
        cs = ChoiceSet(choice_set_id="cs2", title="T", prompt="P")
        assert cs.options == []
        d = cs.to_dict()
        assert d["options"] == []


class TestPacingState:
    def test_defaults(self):
        ps = PacingState()
        assert ps.scene_index == 0
        assert ps.danger_level == "medium"
        assert ps.combat_pressure == "low"

    def test_roundtrip(self):
        ps = PacingState(scene_index=5, danger_level="high", metadata={"x": 1})
        d = ps.to_dict()
        ps2 = PacingState.from_dict(d)
        assert ps2.scene_index == 5
        assert ps2.danger_level == "high"
        assert ps2.metadata == {"x": 1}


class TestFramingState:
    def test_defaults(self):
        fs = FramingState()
        assert fs.last_choice_set is None
        assert fs.forced_recap_pending is False
        assert fs.forced_option_framing_pending is False
        assert fs.focus_target_type is None

    def test_roundtrip(self):
        fs = FramingState(
            last_choice_set={"id": "cs1"},
            forced_recap_pending=True,
            focus_target_type="npc",
            focus_target_id="npc1",
        )
        d = fs.to_dict()
        fs2 = FramingState.from_dict(d)
        assert fs2.forced_recap_pending is True
        assert fs2.focus_target_id == "npc1"


# ===================================================================
# OPTION ENGINE
# ===================================================================


class TestOptionEngine:
    def _make_engine(self):
        return OptionEngine()

    def test_build_choice_set_empty(self):
        engine = self._make_engine()
        cc = StubCoherenceCore()
        gm = GMDirectiveState()
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        assert isinstance(cs, ChoiceSet)
        assert cs.choice_set_id.startswith("cs:")
        # Should at least have the recap option
        assert any(o.intent_type == "request_recap" for o in cs.options)

    def test_thread_options_generated(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(
            threads=[
                {"thread_id": "t1", "title": "Mystery", "priority": "high"},
                {"thread_id": "t2", "title": "Side quest", "priority": "low"},
            ]
        )
        gm = GMDirectiveState()
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        thread_opts = [o for o in cs.options if o.intent_type == "investigate_thread"]
        assert len(thread_opts) == 2

    def test_npc_options_from_scene(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(
            scene={"present_actors": ["npc_alara", "npc_bob"], "location": "tavern"}
        )
        gm = GMDirectiveState()
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        npc_opts = [o for o in cs.options if o.intent_type == "talk_to_npc"]
        assert len(npc_opts) == 2

    def test_location_option(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(scene={"location": "forest"})
        gm = GMDirectiveState()
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        loc_opts = [o for o in cs.options if o.intent_type == "travel_to_location"]
        assert len(loc_opts) == 1
        assert loc_opts[0].target_id == "forest"

    def test_gm_pin_boosts_priority(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "Mystery", "priority": "normal"}]
        )
        gm = GMDirectiveState()
        gm.add_directive(
            PinThreadDirective(
                directive_id="gm:pin:t1",
                directive_type="pin_thread",
                thread_id="t1",
            )
        )
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        pinned = [o for o in cs.options if o.target_id == "t1"]
        assert len(pinned) == 1
        assert pinned[0].priority > 1.0
        assert any(c.constraint_type == "gm_pin" for c in pinned[0].constraints)

    def test_focus_bias(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(
            scene={"present_actors": ["npc_a"], "location": "market"}
        )
        gm = GMDirectiveState()
        framing = FramingState(focus_target_type="npc", focus_target_id="npc_a")
        cs = engine.build_choice_set(cc, gm, PacingState(), framing)
        focused = [o for o in cs.options if o.target_id == "npc_a"]
        assert len(focused) == 1
        assert "focused" in focused[0].tags

    def test_pacing_danger_high_boosts_threads(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "M", "priority": "normal"}]
        )
        gm = GMDirectiveState()
        pacing = PacingState(danger_level="high")
        cs = engine.build_choice_set(cc, gm, pacing, FramingState())
        thread_opt = [o for o in cs.options if o.intent_type == "investigate_thread"]
        assert thread_opt[0].priority > 1.0

    def test_sort_and_trim_limits(self):
        engine = self._make_engine()
        # Make many threads to exceed limit
        threads = [
            {"thread_id": f"t{i}", "title": f"T{i}", "priority": "normal"}
            for i in range(10)
        ]
        cc = StubCoherenceCore(
            threads=threads,
            scene={"present_actors": ["a", "b", "c"], "location": "x"},
        )
        gm = GMDirectiveState()
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        assert len(cs.options) <= 6

    def test_choice_set_serializable(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "M", "priority": "high"}],
            scene={"present_actors": ["npc1"], "location": "city"},
        )
        gm = GMDirectiveState()
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        d = cs.to_dict()
        assert isinstance(d, dict)
        assert "options" in d
        cs2 = ChoiceSet.from_dict(d)
        assert cs2.choice_set_id == cs.choice_set_id

    def test_reveal_pressure_high_boosts_threads(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "X", "priority": "normal"}]
        )
        gm = GMDirectiveState()
        pacing = PacingState(reveal_pressure="high")
        cs = engine.build_choice_set(cc, gm, pacing, FramingState())
        thread_opt = [o for o in cs.options if o.intent_type == "investigate_thread"]
        assert thread_opt[0].priority > 1.0

    def test_social_pressure_high_boosts_npc(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(scene={"present_actors": ["npc_a"], "location": "inn"})
        gm = GMDirectiveState()
        pacing = PacingState(social_pressure="high")
        cs = engine.build_choice_set(cc, gm, pacing, FramingState())
        npc_opt = [o for o in cs.options if o.intent_type == "talk_to_npc"]
        assert npc_opt[0].priority > 1.0

    def test_no_scene_no_npc_or_loc_options(self):
        engine = self._make_engine()
        cc = StubCoherenceCore(scene={})
        gm = GMDirectiveState()
        cs = engine.build_choice_set(cc, gm, PacingState(), FramingState())
        npc_opts = [o for o in cs.options if o.intent_type == "talk_to_npc"]
        loc_opts = [o for o in cs.options if o.intent_type == "travel_to_location"]
        assert len(npc_opts) == 0
        assert len(loc_opts) == 0

    def test_none_gm_state_does_not_crash(self):
        engine = self._make_engine()
        cc = StubCoherenceCore()
        cs = engine.build_choice_set(cc, None, PacingState(), FramingState())
        assert isinstance(cs, ChoiceSet)


# ===================================================================
# PACING CONTROLLER
# ===================================================================


class TestPacingController:
    def test_initial_state(self):
        pc = PacingController()
        s = pc.get_state()
        assert isinstance(s, PacingState)
        assert s.scene_index == 0

    def test_advance_scene(self):
        pc = PacingController()
        pc.advance_scene()
        pc.advance_scene()
        assert pc.get_state().scene_index == 2

    def test_set_state(self):
        pc = PacingController()
        pc.set_state(PacingState(scene_index=10, danger_level="high"))
        assert pc.get_state().scene_index == 10
        assert pc.get_state().danger_level == "high"

    def test_update_from_coherence_high_threads(self):
        pc = PacingController()
        cc = StubCoherenceCore(
            threads=[
                {"thread_id": "t1", "title": "A", "priority": "high"},
                {"thread_id": "t2", "title": "B", "priority": "critical"},
                {"thread_id": "t3", "title": "C", "priority": "high"},
            ],
            commitments=_StubCommitments(
                player_commitments={"p1": {}, "p2": {}, "p3": {}},
                npc_commitments={"n1": {}, "n2": {}},
            ),
        )
        pc.update_from_coherence(cc)
        assert pc.get_state().reveal_pressure == "high"
        assert pc.get_state().social_pressure == "high"

    def test_update_from_coherence_low_threads(self):
        pc = PacingController()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "A", "priority": "low"}],
            commitments=_StubCommitments(),
        )
        pc.update_from_coherence(cc)
        assert pc.get_state().reveal_pressure == "low"
        assert pc.get_state().social_pressure == "low"

    def test_apply_gm_danger_directive(self):
        pc = PacingController()
        gm = GMDirectiveState()
        gm.add_directive(
            DangerDirective(
                directive_id="d1",
                directive_type="danger",
                level="high",
            )
        )
        pc.apply_gm_directives(gm)
        assert pc.get_state().danger_level == "high"

    def test_apply_gm_no_danger(self):
        pc = PacingController()
        pc.set_state(PacingState(danger_level="low"))
        gm = GMDirectiveState()
        pc.apply_gm_directives(gm)
        # Should retain existing level when no directive found
        assert pc.get_state().danger_level == "low"

    def test_apply_gm_none(self):
        pc = PacingController()
        pc.set_state(PacingState(danger_level="low"))
        pc.apply_gm_directives(None)
        assert pc.get_state().danger_level == "low"

    def test_serialize_deserialize(self):
        pc = PacingController()
        pc.advance_scene()
        pc.set_state(PacingState(scene_index=3, danger_level="high", metadata={"k": 1}))
        d = pc.serialize_state()
        pc2 = PacingController()
        pc2.deserialize_state(d)
        assert pc2.get_state().scene_index == 3
        assert pc2.get_state().danger_level == "high"

    def test_medium_reveal_pressure(self):
        pc = PacingController()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "A", "priority": "high"}],
            commitments=_StubCommitments(),
        )
        pc.update_from_coherence(cc)
        assert pc.get_state().reveal_pressure == "medium"

    def test_medium_social_pressure(self):
        pc = PacingController()
        cc = StubCoherenceCore(
            commitments=_StubCommitments(
                player_commitments={"p1": {}, "p2": {}},
                npc_commitments={},
            ),
        )
        pc.update_from_coherence(cc)
        assert pc.get_state().social_pressure == "medium"


# ===================================================================
# FRAMING ENGINE
# ===================================================================


class TestFramingEngine:
    def test_initial_state(self):
        fe = FramingEngine()
        s = fe.get_state()
        assert isinstance(s, FramingState)
        assert s.forced_recap_pending is False

    def test_set_state(self):
        fe = FramingEngine()
        fe.set_state(FramingState(forced_recap_pending=True))
        assert fe.get_state().forced_recap_pending is True

    def test_update_from_gm_forced_option_framing(self):
        fe = FramingEngine()
        gm = GMDirectiveState()
        gm.add_directive(
            OptionFramingDirective(
                directive_id="gm:frame",
                directive_type="option_framing",
                force=True,
            )
        )
        fe.update_from_gm_state(gm)
        assert fe.get_state().forced_option_framing_pending is True

    def test_update_from_gm_forced_recap(self):
        fe = FramingEngine()
        gm = GMDirectiveState()
        gm.add_directive(
            RecapDirective(
                directive_id="gm:recap",
                directive_type="recap",
                force=True,
            )
        )
        fe.update_from_gm_state(gm)
        assert fe.get_state().forced_recap_pending is True

    def test_update_from_gm_focus_target(self):
        fe = FramingEngine()
        gm = GMDirectiveState()
        gm.add_directive(
            TargetNPCDirective(
                directive_id="gm:t",
                directive_type="target_npc",
                npc_id="npc_a",
                instruction="focus",
            )
        )
        fe.update_from_gm_state(gm)
        assert fe.get_state().focus_target_type == "npc"
        assert fe.get_state().focus_target_id == "npc_a"

    def test_update_clears_focus_when_none(self):
        fe = FramingEngine()
        fe.set_state(FramingState(focus_target_type="npc", focus_target_id="npc_a"))
        gm = GMDirectiveState()  # no focus directives
        fe.update_from_gm_state(gm)
        assert fe.get_state().focus_target_type is None
        assert fe.get_state().focus_target_id is None

    def test_update_from_none_gm(self):
        fe = FramingEngine()
        fe.update_from_gm_state(None)
        assert fe.get_state().forced_recap_pending is False

    def test_mark_choice_set_presented(self):
        fe = FramingEngine()
        cs = ChoiceSet(choice_set_id="cs1", title="T", prompt="P")
        fe.mark_choice_set_presented(cs, tick=5)
        s = fe.get_state()
        assert s.last_choice_set is not None
        assert s.last_choice_set["choice_set_id"] == "cs1"
        assert s.last_recap_tick == 5

    def test_consume_forced_recap(self):
        fe = FramingEngine()
        fe.set_state(FramingState(forced_recap_pending=True))
        assert fe.consume_forced_recap() is True
        assert fe.get_state().forced_recap_pending is False
        assert fe.consume_forced_recap() is False

    def test_consume_forced_option_framing(self):
        fe = FramingEngine()
        fe.set_state(FramingState(forced_option_framing_pending=True))
        assert fe.consume_forced_option_framing() is True
        assert fe.get_state().forced_option_framing_pending is False
        assert fe.consume_forced_option_framing() is False

    def test_serialize_deserialize(self):
        fe = FramingEngine()
        fe.set_state(
            FramingState(
                forced_recap_pending=True,
                focus_target_type="thread",
                focus_target_id="t1",
            )
        )
        d = fe.serialize_state()
        fe2 = FramingEngine()
        fe2.deserialize_state(d)
        assert fe2.get_state().forced_recap_pending is True
        assert fe2.get_state().focus_target_id == "t1"


# ===================================================================
# GAMEPLAY CONTROL CONTROLLER
# ===================================================================


class TestGameplayControlController:
    def _cc(self, **kwargs):
        return StubCoherenceCore(**kwargs)

    def _gm(self):
        return GMDirectiveState()

    def test_build_control_output_shape(self):
        ctrl = GameplayControlController()
        out = ctrl.build_control_output(self._cc(), self._gm())
        assert "choice_set" in out
        assert "pacing" in out
        assert "framing" in out

    def test_build_control_output_with_threads(self):
        ctrl = GameplayControlController()
        cc = self._cc(
            threads=[{"thread_id": "t1", "title": "X", "priority": "high"}],
            scene={"present_actors": ["npc1"], "location": "city"},
        )
        out = ctrl.build_control_output(cc, self._gm())
        opts = out["choice_set"]["options"]
        assert any(o["intent_type"] == "investigate_thread" for o in opts)

    def test_build_control_output_updates_pacing(self):
        ctrl = GameplayControlController()
        gm = self._gm()
        gm.add_directive(
            DangerDirective(directive_id="d1", directive_type="danger", level="high")
        )
        cc = self._cc(
            threads=[
                {"thread_id": "t1", "title": "A", "priority": "high"},
                {"thread_id": "t2", "title": "B", "priority": "critical"},
                {"thread_id": "t3", "title": "C", "priority": "high"},
            ]
        )
        out = ctrl.build_control_output(cc, gm)
        assert out["pacing"]["danger_level"] == "high"
        assert out["pacing"]["reveal_pressure"] == "high"

    def test_build_control_output_updates_framing(self):
        ctrl = GameplayControlController()
        gm = self._gm()
        gm.add_directive(
            OptionFramingDirective(
                directive_id="gm:frame",
                directive_type="option_framing",
                force=True,
            )
        )
        out = ctrl.build_control_output(self._cc(), gm)
        # forced_option_framing_pending is set by update_from_gm_state;
        # it remains True until explicitly consumed by the caller
        assert out["framing"]["forced_option_framing_pending"] is True

    def test_build_control_output_records_last_choice_set(self):
        ctrl = GameplayControlController()
        out = ctrl.build_control_output(self._cc(), self._gm(), tick=7)
        assert out["framing"]["last_choice_set"] is not None
        assert out["framing"]["last_recap_tick"] == 7

    def test_set_mode(self):
        ctrl = GameplayControlController()
        ctrl.set_mode("test")
        s = ctrl.serialize_state()
        assert s["mode"] == "test"

    def test_mark_choice_set_presented(self):
        ctrl = GameplayControlController()
        cs_dict = {"choice_set_id": "cs1", "title": "T", "prompt": "P", "options": [], "source_summary": {}, "metadata": {}}
        ctrl.mark_choice_set_presented(cs_dict, tick=10)
        s = ctrl.serialize_state()
        assert s["framing"]["last_recap_tick"] == 10

    def test_serialize_deserialize(self):
        ctrl = GameplayControlController()
        ctrl.set_mode("test_mode")
        ctrl.build_control_output(self._cc(), self._gm(), tick=3)
        d = ctrl.serialize_state()
        ctrl2 = GameplayControlController()
        ctrl2.deserialize_state(d)
        s = ctrl2.serialize_state()
        assert s["mode"] == "test_mode"
        assert s["framing"]["last_recap_tick"] == 3

    def test_custom_engines(self):
        oe = OptionEngine()
        pc = PacingController()
        fe = FramingEngine()
        ctrl = GameplayControlController(
            option_engine=oe, pacing_controller=pc, framing_engine=fe
        )
        out = ctrl.build_control_output(self._cc(), self._gm())
        assert "choice_set" in out

    def test_deterministic_output_structure(self):
        ctrl = GameplayControlController()
        cc = self._cc(
            threads=[
                {"thread_id": "t1", "title": "X", "priority": "normal"},
                {"thread_id": "t2", "title": "Y", "priority": "high"},
            ],
            scene={"present_actors": ["npc1"], "location": "castle"},
        )
        out = ctrl.build_control_output(cc, self._gm(), tick=1)
        cs = out["choice_set"]
        assert isinstance(cs["options"], list)
        assert isinstance(cs["choice_set_id"], str)
        pacing = out["pacing"]
        assert isinstance(pacing["scene_index"], int)
        assert isinstance(pacing["danger_level"], str)


# ===================================================================
# GM DIRECTIVE STATE — NEW METHODS (Phase 7.2)
# ===================================================================


class TestGMDirectiveStatePhase72:
    def test_has_forced_option_framing_false(self):
        gm = GMDirectiveState()
        assert gm.has_forced_option_framing() is False

    def test_has_forced_option_framing_true(self):
        gm = GMDirectiveState()
        gm.add_directive(
            OptionFramingDirective(
                directive_id="gm:frame",
                directive_type="option_framing",
                force=True,
            )
        )
        assert gm.has_forced_option_framing() is True

    def test_has_forced_option_framing_not_forced(self):
        gm = GMDirectiveState()
        gm.add_directive(
            OptionFramingDirective(
                directive_id="gm:frame",
                directive_type="option_framing",
                force=False,
            )
        )
        assert gm.has_forced_option_framing() is False

    def test_has_forced_recap_false(self):
        gm = GMDirectiveState()
        assert gm.has_forced_recap() is False

    def test_has_forced_recap_true(self):
        gm = GMDirectiveState()
        gm.add_directive(
            RecapDirective(
                directive_id="gm:recap",
                directive_type="recap",
                force=True,
            )
        )
        assert gm.has_forced_recap() is True

    def test_has_forced_recap_not_forced(self):
        gm = GMDirectiveState()
        gm.add_directive(
            RecapDirective(
                directive_id="gm:recap",
                directive_type="recap",
                force=False,
            )
        )
        assert gm.has_forced_recap() is False

    def test_get_focus_target_none(self):
        gm = GMDirectiveState()
        assert gm.get_focus_target() is None

    def test_get_focus_target_npc(self):
        gm = GMDirectiveState()
        gm.add_directive(
            TargetNPCDirective(
                directive_id="gm:t",
                directive_type="target_npc",
                npc_id="npc_a",
                instruction="focus",
            )
        )
        ft = gm.get_focus_target()
        assert ft == {"target_type": "npc", "target_id": "npc_a"}

    def test_get_focus_target_faction(self):
        gm = GMDirectiveState()
        gm.add_directive(
            TargetFactionDirective(
                directive_id="gm:t",
                directive_type="target_faction",
                faction_id="faction_a",
                instruction="focus",
            )
        )
        ft = gm.get_focus_target()
        assert ft == {"target_type": "faction", "target_id": "faction_a"}

    def test_get_focus_target_location(self):
        gm = GMDirectiveState()
        gm.add_directive(
            TargetLocationDirective(
                directive_id="gm:t",
                directive_type="target_location",
                location_id="loc_a",
                instruction="focus",
            )
        )
        ft = gm.get_focus_target()
        assert ft == {"target_type": "location", "target_id": "loc_a"}

    def test_get_focus_target_thread(self):
        gm = GMDirectiveState()
        gm.add_directive(
            PinThreadDirective(
                directive_id="gm:pin:t1",
                directive_type="pin_thread",
                thread_id="t1",
            )
        )
        ft = gm.get_focus_target()
        assert ft == {"target_type": "thread", "target_id": "t1"}

    def test_option_framing_in_directive_types(self):
        assert "option_framing" in DIRECTIVE_TYPES
        assert DIRECTIVE_TYPES["option_framing"] is OptionFramingDirective

    def test_recap_in_directive_types(self):
        assert "recap" in DIRECTIVE_TYPES
        assert DIRECTIVE_TYPES["recap"] is RecapDirective

    def test_serialize_deserialize_new_directives(self):
        gm = GMDirectiveState()
        gm.add_directive(
            OptionFramingDirective(
                directive_id="gm:frame",
                directive_type="option_framing",
                force=True,
            )
        )
        gm.add_directive(
            RecapDirective(
                directive_id="gm:recap",
                directive_type="recap",
                force=True,
            )
        )
        d = gm.serialize_state()
        gm2 = GMDirectiveState()
        gm2.deserialize_state(d)
        assert gm2.has_forced_option_framing() is True
        assert gm2.has_forced_recap() is True

    def test_disabled_directives_ignored(self):
        gm = GMDirectiveState()
        gm.add_directive(
            OptionFramingDirective(
                directive_id="gm:frame",
                directive_type="option_framing",
                force=True,
                enabled=False,
            )
        )
        assert gm.has_forced_option_framing() is False


# ===================================================================
# GM COMMAND PROCESSOR — NEW COMMANDS (Phase 7.2)
# ===================================================================


class TestGMCommandProcessorPhase72:
    def _proc(self):
        return GMCommandProcessor()

    def _gm(self):
        return GMDirectiveState()

    def _cc(self):
        return StubCoherenceCore()

    # parse_command tests

    def test_parse_frame_options(self):
        cmd = self._proc().parse_command("frame options")
        assert cmd["command"] == "frame_options"

    def test_parse_force_recap(self):
        cmd = self._proc().parse_command("force recap")
        assert cmd["command"] == "force_recap"

    def test_parse_focus_on_thread(self):
        cmd = self._proc().parse_command("focus on thread t1")
        assert cmd["command"] == "focus_thread"
        assert cmd["thread_id"] == "t1"

    def test_parse_raise_danger(self):
        cmd = self._proc().parse_command("raise danger")
        assert cmd["command"] == "raise_danger"

    def test_parse_lower_danger(self):
        cmd = self._proc().parse_command("lower danger")
        assert cmd["command"] == "lower_danger"

    # apply_command handler tests

    def test_command_frame_options(self):
        proc = self._proc()
        gm = self._gm()
        result = proc.apply_command({"command": "frame_options"}, gm, self._cc())
        assert result["ok"] is True
        assert gm.has_forced_option_framing() is True

    def test_command_force_recap(self):
        proc = self._proc()
        gm = self._gm()
        result = proc.apply_command({"command": "force_recap"}, gm, self._cc())
        assert result["ok"] is True
        assert gm.has_forced_recap() is True

    def test_command_focus_thread(self):
        proc = self._proc()
        gm = self._gm()
        result = proc.apply_command(
            {"command": "focus_thread", "thread_id": "t1"}, gm, self._cc()
        )
        assert result["ok"] is True
        ft = gm.get_focus_target()
        assert ft["target_type"] == "thread"
        assert ft["target_id"] == "t1"

    def test_command_focus_thread_missing_id(self):
        proc = self._proc()
        gm = self._gm()
        result = proc.apply_command({"command": "focus_thread"}, gm, self._cc())
        assert result["ok"] is False
        assert result["reason"] == "missing_thread_id"

    def test_command_raise_danger(self):
        proc = self._proc()
        gm = self._gm()
        result = proc.apply_command({"command": "raise_danger"}, gm, self._cc())
        assert result["ok"] is True
        directives = gm.get_active_directives()
        danger_ds = [d for d in directives if getattr(d, "directive_type", "") == "danger"]
        assert len(danger_ds) == 1
        assert danger_ds[0].level == "high"

    def test_command_lower_danger(self):
        proc = self._proc()
        gm = self._gm()
        result = proc.apply_command({"command": "lower_danger"}, gm, self._cc())
        assert result["ok"] is True
        directives = gm.get_active_directives()
        danger_ds = [d for d in directives if getattr(d, "directive_type", "") == "danger"]
        assert len(danger_ds) == 1
        assert danger_ds[0].level == "low"

    # end-to-end parse + apply

    def test_e2e_frame_options(self):
        proc = self._proc()
        gm = self._gm()
        cmd = proc.parse_command("frame options")
        result = proc.apply_command(cmd, gm, self._cc())
        assert result["ok"] is True
        assert gm.has_forced_option_framing() is True

    def test_e2e_force_recap(self):
        proc = self._proc()
        gm = self._gm()
        cmd = proc.parse_command("force recap")
        result = proc.apply_command(cmd, gm, self._cc())
        assert result["ok"] is True
        assert gm.has_forced_recap() is True

    def test_e2e_focus_on_thread(self):
        proc = self._proc()
        gm = self._gm()
        cmd = proc.parse_command("focus on thread my_thread")
        result = proc.apply_command(cmd, gm, self._cc())
        assert result["ok"] is True
        ft = gm.get_focus_target()
        assert ft == {"target_type": "thread", "target_id": "my_thread"}

    def test_e2e_raise_danger(self):
        proc = self._proc()
        gm = self._gm()
        cmd = proc.parse_command("raise danger")
        result = proc.apply_command(cmd, gm, self._cc())
        assert result["ok"] is True

    def test_e2e_lower_danger(self):
        proc = self._proc()
        gm = self._gm()
        cmd = proc.parse_command("lower danger")
        result = proc.apply_command(cmd, gm, self._cc())
        assert result["ok"] is True


# ===================================================================
# INTEGRATION — control + creator together
# ===================================================================


class TestControlCreatorIntegration:
    def test_gm_directives_flow_into_control_output(self):
        """GM directive -> framing engine -> control output."""
        gm = GMDirectiveState()
        gm.add_directive(
            OptionFramingDirective(
                directive_id="gm:frame",
                directive_type="option_framing",
                force=True,
            )
        )
        gm.add_directive(
            DangerDirective(directive_id="d1", directive_type="danger", level="high")
        )
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "X", "priority": "high"}],
            scene={"present_actors": ["npc1"], "location": "castle"},
        )
        ctrl = GameplayControlController()
        out = ctrl.build_control_output(cc, gm, tick=1)
        assert out["pacing"]["danger_level"] == "high"
        assert out["choice_set"]["options"]
        assert out["framing"]["last_choice_set"] is not None

    def test_command_to_control_output_flow(self):
        """parse + apply command -> control output incorporates it."""
        proc = GMCommandProcessor()
        gm = GMDirectiveState()
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "X", "priority": "normal"}]
        )

        # Apply raise danger command
        cmd = proc.parse_command("raise danger")
        proc.apply_command(cmd, gm, cc)

        # Apply frame options command
        cmd = proc.parse_command("frame options")
        proc.apply_command(cmd, gm, cc)

        ctrl = GameplayControlController()
        out = ctrl.build_control_output(cc, gm, tick=2)
        assert out["pacing"]["danger_level"] == "high"

    def test_focus_thread_flows_to_option_bias(self):
        """focus on thread command -> pinned thread -> higher priority in options."""
        proc = GMCommandProcessor()
        gm = GMDirectiveState()
        cc = StubCoherenceCore(
            threads=[
                {"thread_id": "t1", "title": "Main quest", "priority": "normal"},
                {"thread_id": "t2", "title": "Side quest", "priority": "normal"},
            ]
        )

        cmd = proc.parse_command("focus on thread t1")
        proc.apply_command(cmd, gm, cc)

        ctrl = GameplayControlController()
        out = ctrl.build_control_output(cc, gm, tick=1)
        opts = out["choice_set"]["options"]
        t1_opt = [o for o in opts if o.get("target_id") == "t1"]
        t2_opt = [o for o in opts if o.get("target_id") == "t2"]
        assert t1_opt
        assert t2_opt
        # t1 should have higher priority due to focus + pin
        assert t1_opt[0]["priority"] > t2_opt[0]["priority"]

    def test_full_control_serialize_roundtrip(self):
        """Build output -> serialize -> deserialize -> state preserved."""
        ctrl = GameplayControlController()
        ctrl.set_mode("integration_test")
        cc = StubCoherenceCore(
            threads=[{"thread_id": "t1", "title": "X", "priority": "high"}]
        )
        gm = GMDirectiveState()
        ctrl.build_control_output(cc, gm, tick=5)
        d = ctrl.serialize_state()

        ctrl2 = GameplayControlController()
        ctrl2.deserialize_state(d)
        s = ctrl2.serialize_state()
        assert s["mode"] == "integration_test"
        assert s["framing"]["last_recap_tick"] == 5

    def test_existing_commands_still_work(self):
        """Ensure Phase 7.1 commands remain functional."""
        proc = GMCommandProcessor()
        gm = GMDirectiveState()
        cc = StubCoherenceCore()

        for text, expected_cmd in [
            ("pin thread t1", "pin_thread"),
            ("set danger high", "set_danger"),
            ("set tone darker", "switch_tone"),
            ("restate canon", "restate_canon"),
        ]:
            cmd = proc.parse_command(text)
            assert cmd["command"] == expected_cmd, f"Failed for '{text}': {cmd}"
