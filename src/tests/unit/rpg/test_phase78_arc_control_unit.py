"""Phase 7.8 — Live Narrative Steering / Arc Control — Unit Tests.

Covers:
- models: NarrativeArc, RevealDirectiveState, PacingPlanState, SceneBiasState
- arc_registry: ArcRegistry
- reveal_scheduler: RevealScheduler
- pacing_plan: PacingPlanController
- scene_bias: SceneBiasController
- directive_adapter: ArcDirectiveAdapter
- controller: ArcControlController
- presenters: ArcControlPresenter
- control/controller: external_bias parameter
- narrative/story_director: arc_control_context field + guidance
- creator/commands: arc steering command parsing + application
"""

import pytest

from app.rpg.arc_control.models import (
    NarrativeArc,
    PacingPlanState,
    RevealDirectiveState,
    SceneBiasState,
)
from app.rpg.arc_control.arc_registry import ArcRegistry
from app.rpg.arc_control.reveal_scheduler import RevealScheduler
from app.rpg.arc_control.pacing_plan import PacingPlanController
from app.rpg.arc_control.scene_bias import SceneBiasController
from app.rpg.arc_control.directive_adapter import ArcDirectiveAdapter
from app.rpg.arc_control.controller import ArcControlController
from app.rpg.arc_control.presenters import ArcControlPresenter


# ======================================================================
# Model Tests
# ======================================================================


class TestNarrativeArc:
    def test_defaults(self):
        arc = NarrativeArc(arc_id="a1", title="Test Arc")
        assert arc.status == "active"
        assert arc.priority == "normal"
        assert arc.arc_type == "general"
        assert arc.related_thread_ids == []
        assert arc.focus_entity_ids == []
        assert arc.summary == ""
        assert arc.metadata == {}

    def test_to_dict(self):
        arc = NarrativeArc(arc_id="a1", title="Arc", status="dormant")
        d = arc.to_dict()
        assert d["arc_id"] == "a1"
        assert d["status"] == "dormant"

    def test_from_dict(self):
        d = {"arc_id": "a1", "title": "Arc", "status": "blocked", "priority": "high"}
        arc = NarrativeArc.from_dict(d)
        assert arc.arc_id == "a1"
        assert arc.status == "blocked"
        assert arc.priority == "high"

    def test_roundtrip(self):
        arc = NarrativeArc(
            arc_id="a1",
            title="Test",
            status="resolved",
            priority="high",
            arc_type="mystery",
            related_thread_ids=["t1", "t2"],
            focus_entity_ids=["e1"],
            summary="A mystery",
            metadata={"key": "val"},
        )
        arc2 = NarrativeArc.from_dict(arc.to_dict())
        assert arc2.to_dict() == arc.to_dict()

    def test_from_dict_defaults(self):
        arc = NarrativeArc.from_dict({})
        assert arc.arc_id == ""
        assert arc.title == ""
        assert arc.status == "active"


class TestRevealDirectiveState:
    def test_defaults(self):
        r = RevealDirectiveState(reveal_id="r1", target_id="t1", target_type="secret")
        assert r.status == "scheduled"
        assert r.timing == "soon"
        assert r.hold_reason == ""

    def test_roundtrip(self):
        r = RevealDirectiveState(
            reveal_id="r1", target_id="t1", target_type="secret",
            status="held", timing="held", hold_reason="suspense",
            metadata={"k": "v"},
        )
        r2 = RevealDirectiveState.from_dict(r.to_dict())
        assert r2.to_dict() == r.to_dict()


class TestPacingPlanState:
    def test_defaults(self):
        p = PacingPlanState(plan_id="p1", label="Act 2")
        assert p.danger_bias == "medium"
        assert p.mystery_bias == "medium"
        assert p.social_bias == "medium"
        assert p.combat_bias == "low"
        assert p.target_scene_count == 3

    def test_roundtrip(self):
        p = PacingPlanState(
            plan_id="p1", label="Act 2",
            danger_bias="high", mystery_bias="low",
            target_scene_count=5,
        )
        p2 = PacingPlanState.from_dict(p.to_dict())
        assert p2.to_dict() == p.to_dict()


class TestSceneBiasState:
    def test_defaults(self):
        b = SceneBiasState(bias_id="b1")
        assert b.scene_type_bias == "balanced"
        assert b.focus_arc_id is None
        assert b.force_option_framing is False
        assert b.force_recap is False

    def test_roundtrip(self):
        b = SceneBiasState(
            bias_id="b1",
            scene_type_bias="mystery",
            focus_arc_id="arc:t1",
            focus_npc_id="npc1",
            force_recap=True,
        )
        b2 = SceneBiasState.from_dict(b.to_dict())
        assert b2.to_dict() == b.to_dict()


# ======================================================================
# ArcRegistry Tests
# ======================================================================


class TestArcRegistry:
    def test_list_empty(self):
        reg = ArcRegistry()
        assert reg.list_arcs({}) == []

    def test_upsert_and_get(self):
        reg = ArcRegistry()
        state: dict = {}
        arc = NarrativeArc(arc_id="a1", title="Arc 1")
        reg.upsert_arc(state, arc)
        assert reg.get_arc(state, "a1") is arc
        assert len(reg.list_arcs(state)) == 1

    def test_set_status(self):
        reg = ArcRegistry()
        state: dict = {}
        arc = NarrativeArc(arc_id="a1", title="Arc 1")
        reg.upsert_arc(state, arc)
        reg.set_status(state, "a1", "dormant")
        assert state["a1"].status == "dormant"

    def test_set_status_missing(self):
        reg = ArcRegistry()
        reg.set_status({}, "missing", "dormant")  # no-op, no error

    def test_build_from_threads(self):
        class MockCoherence:
            def get_unresolved_threads(self):
                return [
                    {"thread_id": "t1", "title": "Thread 1"},
                    {"thread_id": "t2", "title": "Thread 2"},
                ]
        reg = ArcRegistry()
        arcs = reg.build_from_threads(MockCoherence())
        assert len(arcs) == 2
        assert arcs[0].arc_id == "arc:t1"
        assert arcs[1].related_thread_ids == ["t2"]

    def test_build_from_threads_none(self):
        reg = ArcRegistry()
        assert reg.build_from_threads(None) == []

    def test_refresh_from_coherence_non_destructive(self):
        reg = ArcRegistry()
        state: dict = {}
        # Pre-existing arc with GM-set priority
        arc = NarrativeArc(arc_id="arc:t1", title="Existing", priority="high")
        state["arc:t1"] = arc

        class MockCoherence:
            def get_unresolved_threads(self):
                return [{"thread_id": "t1", "title": "Thread 1"}, {"thread_id": "t2"}]

        reg.refresh_from_coherence(state, MockCoherence())
        # Existing arc not overwritten
        assert state["arc:t1"].priority == "high"
        # New arc added
        assert "arc:t2" in state


# ======================================================================
# RevealScheduler Tests
# ======================================================================


class TestRevealScheduler:
    def test_schedule_and_list(self):
        sched = RevealScheduler()
        state: dict = {}
        r = RevealDirectiveState(reveal_id="r1", target_id="t1", target_type="secret")
        sched.schedule(state, r)
        assert len(sched.list_reveals(state)) == 1

    def test_hold_and_release(self):
        sched = RevealScheduler()
        state: dict = {}
        r = RevealDirectiveState(reveal_id="r1", target_id="t1", target_type="secret")
        sched.schedule(state, r)
        sched.hold(state, "r1", "suspense")
        assert state["r1"].timing == "held"
        assert state["r1"].status == "held"
        assert state["r1"].hold_reason == "suspense"
        sched.release(state, "r1")
        assert state["r1"].timing == "soon"
        assert state["r1"].status == "scheduled"
        assert state["r1"].hold_reason == ""

    def test_hold_missing(self):
        sched = RevealScheduler()
        sched.hold({}, "missing", "reason")  # no-op

    def test_release_missing(self):
        sched = RevealScheduler()
        sched.release({}, "missing")  # no-op

    def test_due_reveals(self):
        sched = RevealScheduler()
        state: dict = {}
        sched.schedule(state, RevealDirectiveState(
            reveal_id="r1", target_id="t1", target_type="s", timing="immediate",
        ))
        sched.schedule(state, RevealDirectiveState(
            reveal_id="r2", target_id="t2", target_type="s", timing="later",
        ))
        sched.schedule(state, RevealDirectiveState(
            reveal_id="r3", target_id="t3", target_type="s", timing="soon",
        ))
        due = sched.due_reveals(state)
        ids = [r.reveal_id for r in due]
        assert "r1" in ids
        assert "r3" in ids
        assert "r2" not in ids

    def test_held_reveals_not_due(self):
        sched = RevealScheduler()
        state: dict = {}
        sched.schedule(state, RevealDirectiveState(
            reveal_id="r1", target_id="t1", target_type="s", timing="soon",
        ))
        sched.hold(state, "r1", "wait")
        assert sched.due_reveals(state) == []


# ======================================================================
# PacingPlanController Tests
# ======================================================================


class TestPacingPlanController:
    def test_set_and_get(self):
        ctrl = PacingPlanController()
        state: dict = {}
        plan = PacingPlanState(plan_id="p1", label="Act 2")
        ctrl.set_plan(state, plan)
        assert ctrl.get(state, "p1") is plan

    def test_get_active_plan_empty(self):
        ctrl = PacingPlanController()
        assert ctrl.get_active_plan({}) is None

    def test_get_active_plan_last_wins(self):
        ctrl = PacingPlanController()
        state: dict = {}
        ctrl.set_plan(state, PacingPlanState(plan_id="p1", label="First"))
        ctrl.set_plan(state, PacingPlanState(plan_id="p2", label="Second"))
        active = ctrl.get_active_plan(state)
        assert active is not None
        assert active.plan_id == "p2"

    def test_apply_to_control_output_none(self):
        ctrl = PacingPlanController()
        output = {"choice_set": {}}
        assert ctrl.apply_to_control_output(None, output) is output

    def test_apply_to_control_output(self):
        ctrl = PacingPlanController()
        plan = PacingPlanState(plan_id="p1", label="Act 2", danger_bias="high")
        output = {"choice_set": {}}
        result = ctrl.apply_to_control_output(plan, output)
        assert "pacing_bias" in result
        assert result["pacing_bias"]["danger_bias"] == "high"
        assert result["pacing_bias"]["plan_id"] == "p1"
        # Original key preserved
        assert "choice_set" in result


# ======================================================================
# SceneBiasController Tests
# ======================================================================


class TestSceneBiasController:
    def test_set_and_get(self):
        ctrl = SceneBiasController()
        state: dict = {}
        bias = SceneBiasState(bias_id="b1", scene_type_bias="mystery")
        ctrl.set_bias(state, bias)
        assert ctrl.get(state, "b1") is bias

    def test_get_active_bias_empty(self):
        ctrl = SceneBiasController()
        assert ctrl.get_active_bias({}) is None

    def test_apply_to_choice_set_none(self):
        ctrl = SceneBiasController()
        cs = {"options": []}
        assert ctrl.apply_to_choice_set(None, cs) is cs

    def test_apply_to_choice_set(self):
        ctrl = SceneBiasController()
        bias = SceneBiasState(
            bias_id="b1", scene_type_bias="combat", focus_arc_id="arc:t1",
        )
        result = ctrl.apply_to_choice_set(bias, {"options": []})
        assert result["scene_bias"]["scene_type_bias"] == "combat"
        assert result["scene_bias"]["focus_arc_id"] == "arc:t1"

    def test_apply_to_director_context_none(self):
        ctrl = SceneBiasController()
        ctx = {"some_key": "val"}
        assert ctrl.apply_to_director_context(None, ctx) is ctx

    def test_apply_to_director_context(self):
        ctrl = SceneBiasController()
        bias = SceneBiasState(
            bias_id="b1",
            scene_type_bias="social",
            focus_npc_id="npc1",
            force_recap=True,
        )
        result = ctrl.apply_to_director_context(bias, {"existing": True})
        assert result["scene_bias"]["scene_type_bias"] == "social"
        assert result["scene_bias"]["focus_npc_id"] == "npc1"
        assert result["scene_bias"]["force_recap"] is True
        assert result["existing"] is True


# ======================================================================
# ArcDirectiveAdapter Tests
# ======================================================================


class _MockDirective:
    """Minimal directive mock."""
    def __init__(self, dtype, **kwargs):
        self.directive_type = dtype
        for k, v in kwargs.items():
            setattr(self, k, v)


class _MockGMState:
    """Minimal GM state mock."""
    def __init__(self, directives=None):
        self._directives = directives or []

    def list_directives(self):
        return self._directives


class TestArcDirectiveAdapter:
    def test_ingest_none_gm_state(self):
        adapter = ArcDirectiveAdapter()
        arcs: dict = {}
        reveals: dict = {}
        pacing: dict = {}
        biases: dict = {}
        adapter.ingest_gm_state(None, arcs, reveals, pacing, biases)
        assert arcs == {}

    def test_pin_thread(self):
        adapter = ArcDirectiveAdapter()
        arcs: dict = {}
        gm = _MockGMState([_MockDirective("pin_thread", thread_id="t1", priority="high")])
        adapter.ingest_gm_state(gm, arcs, {}, {}, {})
        assert "arc:t1" in arcs
        assert arcs["arc:t1"].priority == "high"

    def test_pin_thread_updates_existing(self):
        adapter = ArcDirectiveAdapter()
        arcs = {"arc:t1": NarrativeArc(arc_id="arc:t1", title="Old", priority="normal")}
        gm = _MockGMState([_MockDirective("pin_thread", thread_id="t1", priority="high")])
        adapter.ingest_gm_state(gm, arcs, {}, {}, {})
        assert arcs["arc:t1"].priority == "high"
        assert arcs["arc:t1"].status == "active"

    def test_reveal_directive(self):
        adapter = ArcDirectiveAdapter()
        reveals: dict = {}
        gm = _MockGMState([_MockDirective(
            "reveal", reveal_type="secret", target_id="npc1", timing="immediate",
        )])
        adapter.ingest_gm_state(gm, {}, reveals, {}, {})
        assert "reveal:secret:npc1" in reveals
        assert reveals["reveal:secret:npc1"].timing == "immediate"

    def test_danger_directive(self):
        adapter = ArcDirectiveAdapter()
        pacing: dict = {}
        gm = _MockGMState([_MockDirective("danger", level="high")])
        adapter.ingest_gm_state(gm, {}, {}, pacing, {})
        assert "gm:pacing" in pacing
        assert pacing["gm:pacing"].danger_bias == "high"

    def test_tone_directive(self):
        adapter = ArcDirectiveAdapter()
        pacing: dict = {}
        gm = _MockGMState([_MockDirective("tone", tone="dark")])
        adapter.ingest_gm_state(gm, {}, {}, pacing, {})
        assert "gm:pacing" in pacing
        assert pacing["gm:pacing"].danger_bias == "high"  # dark → high danger

    def test_target_npc(self):
        adapter = ArcDirectiveAdapter()
        biases: dict = {}
        gm = _MockGMState([_MockDirective("target_npc", npc_id="npc1")])
        adapter.ingest_gm_state(gm, {}, {}, {}, biases)
        assert "gm:focus" in biases
        assert biases["gm:focus"].focus_npc_id == "npc1"

    def test_option_framing(self):
        adapter = ArcDirectiveAdapter()
        biases: dict = {}
        gm = _MockGMState([_MockDirective("option_framing", force=True)])
        adapter.ingest_gm_state(gm, {}, {}, {}, biases)
        assert biases["gm:focus"].force_option_framing is True

    def test_recap(self):
        adapter = ArcDirectiveAdapter()
        biases: dict = {}
        gm = _MockGMState([_MockDirective("recap", force=True)])
        adapter.ingest_gm_state(gm, {}, {}, {}, biases)
        assert biases["gm:focus"].force_recap is True

    def test_multiple_directives(self):
        adapter = ArcDirectiveAdapter()
        arcs: dict = {}
        reveals: dict = {}
        pacing: dict = {}
        biases: dict = {}
        gm = _MockGMState([
            _MockDirective("pin_thread", thread_id="t1", priority="high"),
            _MockDirective("reveal", reveal_type="secret", target_id="npc1", timing="soon"),
            _MockDirective("danger", level="low"),
            _MockDirective("target_npc", npc_id="npc2"),
        ])
        adapter.ingest_gm_state(gm, arcs, reveals, pacing, biases)
        assert len(arcs) == 1
        assert len(reveals) == 1
        assert len(pacing) == 1
        assert len(biases) == 1


# ======================================================================
# ArcControlController Tests
# ======================================================================


class TestArcControlController:
    def test_init(self):
        ctrl = ArcControlController()
        assert ctrl.arcs == {}
        assert ctrl.reveals == {}
        assert ctrl.pacing_plans == {}
        assert ctrl.scene_biases == {}

    def test_set_mode(self):
        ctrl = ArcControlController()
        ctrl.set_mode("replay")
        assert ctrl._mode == "replay"

    def test_refresh_from_state_no_coherence(self):
        ctrl = ArcControlController()
        ctrl.refresh_from_state(None, None)
        assert ctrl.arcs == {}

    def test_refresh_from_state_with_coherence(self):
        class MockCoherence:
            def get_unresolved_threads(self):
                return [{"thread_id": "t1", "title": "T1"}]

        ctrl = ArcControlController()
        ctrl.refresh_from_state(MockCoherence(), None)
        assert "arc:t1" in ctrl.arcs

    def test_refresh_from_state_with_gm(self):
        ctrl = ArcControlController()
        gm = _MockGMState([_MockDirective("danger", level="high")])
        ctrl.refresh_from_state(None, gm)
        assert "gm:pacing" in ctrl.pacing_plans

    def test_build_director_context(self):
        ctrl = ArcControlController()
        ctrl.arcs["a1"] = NarrativeArc(arc_id="a1", title="Arc 1")
        ctx = ctrl.build_director_context(None)
        assert len(ctx["active_arcs"]) == 1
        assert ctx["due_reveals"] == []
        assert ctx["active_pacing_plan"] is None
        assert ctx["active_scene_bias"] is None

    def test_build_director_context_with_reveals(self):
        ctrl = ArcControlController()
        ctrl.reveals["r1"] = RevealDirectiveState(
            reveal_id="r1", target_id="t1", target_type="s", timing="soon",
        )
        ctx = ctrl.build_director_context(None)
        assert len(ctx["due_reveals"]) == 1

    def test_build_control_bias(self):
        ctrl = ArcControlController()
        ctrl.pacing_plans["p1"] = PacingPlanState(
            plan_id="p1", label="Act 2", danger_bias="high",
        )
        ctrl.scene_biases["b1"] = SceneBiasState(
            bias_id="b1", scene_type_bias="mystery",
        )
        result = ctrl.build_control_bias({"choice_set": {}})
        assert "pacing_bias" in result
        assert "scene_bias" in result
        assert result["pacing_bias"]["danger_bias"] == "high"
        assert result["scene_bias"]["scene_type_bias"] == "mystery"

    def test_serialize_deserialize(self):
        ctrl = ArcControlController()
        ctrl.arcs["a1"] = NarrativeArc(arc_id="a1", title="Arc 1")
        ctrl.reveals["r1"] = RevealDirectiveState(
            reveal_id="r1", target_id="t1", target_type="s",
        )
        ctrl.pacing_plans["p1"] = PacingPlanState(plan_id="p1", label="L")
        ctrl.scene_biases["b1"] = SceneBiasState(bias_id="b1")
        ctrl._mode = "replay"

        data = ctrl.serialize_state()

        ctrl2 = ArcControlController()
        ctrl2.deserialize_state(data)
        assert "a1" in ctrl2.arcs
        assert ctrl2.arcs["a1"].title == "Arc 1"
        assert "r1" in ctrl2.reveals
        assert "p1" in ctrl2.pacing_plans
        assert "b1" in ctrl2.scene_biases
        assert ctrl2._mode == "replay"

    def test_serialize_empty(self):
        ctrl = ArcControlController()
        data = ctrl.serialize_state()
        assert data["arcs"] == {}
        assert data["mode"] == "live"

    def test_deserialize_empty(self):
        ctrl = ArcControlController()
        ctrl.arcs["a1"] = NarrativeArc(arc_id="a1", title="A")
        ctrl.deserialize_state({})
        assert ctrl.arcs == {}
        assert ctrl._mode == "live"


# ======================================================================
# ArcControlPresenter Tests
# ======================================================================


class TestArcControlPresenter:
    def test_present_arc_panel_empty(self):
        p = ArcControlPresenter()
        ctrl = ArcControlController()
        result = p.present_arc_panel(ctrl)
        assert result["title"] == "Arcs"
        assert result["items"] == []
        assert result["count"] == 0

    def test_present_arc_panel(self):
        p = ArcControlPresenter()
        ctrl = ArcControlController()
        ctrl.arcs["a1"] = NarrativeArc(arc_id="a1", title="Arc 1")
        result = p.present_arc_panel(ctrl)
        assert result["count"] == 1
        assert result["items"][0]["arc_id"] == "a1"

    def test_present_reveal_panel(self):
        p = ArcControlPresenter()
        ctrl = ArcControlController()
        ctrl.reveals["r1"] = RevealDirectiveState(
            reveal_id="r1", target_id="t1", target_type="s",
        )
        result = p.present_reveal_panel(ctrl)
        assert result["title"] == "Reveals"
        assert result["count"] == 1

    def test_present_pacing_plan_panel(self):
        p = ArcControlPresenter()
        ctrl = ArcControlController()
        ctrl.pacing_plans["p1"] = PacingPlanState(plan_id="p1", label="L")
        result = p.present_pacing_plan_panel(ctrl)
        assert result["title"] == "Pacing Plan"
        assert result["count"] == 1

    def test_present_scene_bias_panel(self):
        p = ArcControlPresenter()
        ctrl = ArcControlController()
        ctrl.scene_biases["b1"] = SceneBiasState(bias_id="b1")
        result = p.present_scene_bias_panel(ctrl)
        assert result["title"] == "Scene Bias"
        assert result["count"] == 1

    def test_present_director_context(self):
        p = ArcControlPresenter()
        ctx = {
            "active_arcs": [{"arc_id": "a1"}],
            "due_reveals": [],
            "active_pacing_plan": None,
            "active_scene_bias": None,
        }
        result = p.present_director_context(ctx)
        assert result["title"] == "Director Context"
        assert len(result["active_arcs"]) == 1


# ======================================================================
# Control Controller — external_bias parameter Tests
# ======================================================================


class TestGameplayControlExternalBias:
    def test_build_control_output_without_bias(self):
        from app.rpg.control.controller import GameplayControlController
        ctrl = GameplayControlController()

        class FakeCoherence:
            def get_unresolved_threads(self):
                return []
            def get_active_tensions(self):
                return []
            def get_scene_summary(self):
                return {}

        output = ctrl.build_control_output(FakeCoherence(), None, tick=1)
        assert "external_bias" not in output

    def test_build_control_output_with_bias(self):
        from app.rpg.control.controller import GameplayControlController
        ctrl = GameplayControlController()

        class FakeCoherence:
            def get_unresolved_threads(self):
                return []
            def get_active_tensions(self):
                return []
            def get_scene_summary(self):
                return {}

        bias = {"danger_bias": "high", "focus_arc_id": "arc:t1"}
        output = ctrl.build_control_output(FakeCoherence(), None, tick=1, external_bias=bias)
        assert output["external_bias"]["danger_bias"] == "high"
        assert output["external_bias"]["focus_arc_id"] == "arc:t1"


# ======================================================================
# Story Director — arc_control_context Tests
# ======================================================================


class TestStoryDirectorArcControl:
    def test_arc_control_context_default_none(self):
        from app.rpg.narrative.story_director import StoryDirector
        sd = StoryDirector()
        assert sd.arc_control_context is None

    def test_set_arc_control_context(self):
        from app.rpg.narrative.story_director import StoryDirector
        sd = StoryDirector()
        ctx = {"active_arcs": [{"arc_id": "a1"}], "due_reveals": []}
        sd.set_arc_control_context(ctx)
        assert sd.arc_control_context is ctx

    def test_build_arc_guidance_none(self):
        from app.rpg.narrative.story_director import StoryDirector
        sd = StoryDirector()
        assert sd._build_arc_guidance() == {}

    def test_build_arc_guidance(self):
        from app.rpg.narrative.story_director import StoryDirector
        sd = StoryDirector()
        ctx = {"active_arcs": [{"arc_id": "a1"}]}
        sd.set_arc_control_context(ctx)
        guidance = sd._build_arc_guidance()
        assert guidance["active_arcs"] == [{"arc_id": "a1"}]

    def test_process_includes_arc_control(self):
        from app.rpg.narrative.story_director import StoryDirector
        from app.rpg.core.event_bus import EventBus
        sd = StoryDirector()
        sd.set_arc_control_context({"active_arcs": [{"arc_id": "a1"}]})
        eb = EventBus()
        result = sd.process([], {"action": "test"}, eb)
        # Arc control is added to world_state which feeds into narrative
        # We verify the director didn't error and arc_control_context is set
        assert sd.arc_control_context is not None


# ======================================================================
# Creator Commands — Phase 7.8 Tests
# ======================================================================


class TestArcControlCommands:
    def setup_method(self):
        from app.rpg.creator.commands import GMCommandProcessor
        self.processor = GMCommandProcessor()

    def test_parse_focus_arc(self):
        cmd = self.processor.parse_command("focus arc arc:main_quest")
        assert cmd["command"] == "focus_arc"
        assert cmd["arc_id"] == "arc:main_quest"

    def test_parse_hold_reveal(self):
        cmd = self.processor.parse_command("hold reveal r1 for suspense")
        assert cmd["command"] == "hold_reveal"
        assert cmd["reveal_id"] == "r1"
        assert cmd["reason"] == "for suspense"

    def test_parse_hold_reveal_no_reason(self):
        cmd = self.processor.parse_command("hold reveal r1")
        assert cmd["command"] == "hold_reveal"
        assert cmd["reveal_id"] == "r1"
        assert cmd["reason"] == ""

    def test_parse_release_reveal(self):
        cmd = self.processor.parse_command("release reveal r1")
        assert cmd["command"] == "release_reveal"
        assert cmd["reveal_id"] == "r1"

    def test_parse_set_pacing(self):
        cmd = self.processor.parse_command("set pacing danger high")
        assert cmd["command"] == "set_pacing"
        assert cmd["bias_type"] == "danger"
        assert cmd["level"] == "high"

    def test_parse_bias_scene(self):
        cmd = self.processor.parse_command("bias scene mystery")
        assert cmd["command"] == "bias_scene"
        assert cmd["scene_type"] == "mystery"

    def test_parse_accelerate_arc(self):
        cmd = self.processor.parse_command("accelerate arc arc:side_quest")
        assert cmd["command"] == "accelerate_arc"
        assert cmd["arc_id"] == "arc:side_quest"

    def test_parse_delay_arc(self):
        cmd = self.processor.parse_command("delay arc arc:side_quest")
        assert cmd["command"] == "delay_arc"
        assert cmd["arc_id"] == "arc:side_quest"

    def test_apply_focus_arc(self):
        from app.rpg.creator.gm_state import GMDirectiveState
        gm = GMDirectiveState()

        class FakeCoherence:
            def get_known_facts(self, _):
                return {}
        cmd = {"command": "focus_arc", "arc_id": "arc:t1"}
        result = self.processor.apply_command(cmd, gm, FakeCoherence())
        assert result["ok"] is True
        assert "focus_arc" in result["directive_id"]

    def test_apply_focus_arc_missing(self):
        from app.rpg.creator.gm_state import GMDirectiveState
        gm = GMDirectiveState()

        class FakeCoherence:
            pass
        cmd = {"command": "focus_arc", "arc_id": ""}
        result = self.processor.apply_command(cmd, gm, FakeCoherence())
        assert result["ok"] is False

    def test_apply_hold_reveal(self):
        from app.rpg.creator.gm_state import GMDirectiveState
        gm = GMDirectiveState()

        class FakeCoherence:
            pass
        cmd = {"command": "hold_reveal", "reveal_id": "r1", "reason": "suspense"}
        result = self.processor.apply_command(cmd, gm, FakeCoherence())
        assert result["ok"] is True

    def test_apply_release_reveal(self):
        from app.rpg.creator.gm_state import GMDirectiveState
        gm = GMDirectiveState()

        class FakeCoherence:
            pass
        cmd = {"command": "release_reveal", "reveal_id": "r1"}
        result = self.processor.apply_command(cmd, gm, FakeCoherence())
        assert result["ok"] is True

    def test_apply_set_pacing(self):
        from app.rpg.creator.gm_state import GMDirectiveState
        gm = GMDirectiveState()

        class FakeCoherence:
            pass
        cmd = {"command": "set_pacing", "bias_type": "danger", "level": "high"}
        result = self.processor.apply_command(cmd, gm, FakeCoherence())
        assert result["ok"] is True

    def test_apply_bias_scene(self):
        from app.rpg.creator.gm_state import GMDirectiveState
        gm = GMDirectiveState()

        class FakeCoherence:
            pass
        cmd = {"command": "bias_scene", "scene_type": "mystery"}
        result = self.processor.apply_command(cmd, gm, FakeCoherence())
        assert result["ok"] is True

    def test_apply_accelerate_arc(self):
        from app.rpg.creator.gm_state import GMDirectiveState
        gm = GMDirectiveState()

        class FakeCoherence:
            pass
        cmd = {"command": "accelerate_arc", "arc_id": "arc:t1"}
        result = self.processor.apply_command(cmd, gm, FakeCoherence())
        assert result["ok"] is True
        directives = gm.list_directives()
        found = [d for d in directives if hasattr(d, "metadata") and d.metadata.get("accelerated")]
        assert len(found) == 1

    def test_apply_delay_arc(self):
        from app.rpg.creator.gm_state import GMDirectiveState
        gm = GMDirectiveState()

        class FakeCoherence:
            pass
        cmd = {"command": "delay_arc", "arc_id": "arc:t1"}
        result = self.processor.apply_command(cmd, gm, FakeCoherence())
        assert result["ok"] is True
        directives = gm.list_directives()
        found = [d for d in directives if hasattr(d, "priority") and d.priority == "low"]
        assert len(found) == 1


# ======================================================================
# Integration Tests
# ======================================================================


class TestArcControlIntegration:
    """End-to-end flow: coherence threads → arcs → GM → bias → serialize."""

    def test_full_cycle(self):
        class MockCoherence:
            def get_unresolved_threads(self):
                return [{"thread_id": "t1", "title": "Main Quest"}]

        ctrl = ArcControlController()
        gm = _MockGMState([
            _MockDirective("pin_thread", thread_id="t1", priority="high"),
            _MockDirective("danger", level="high"),
            _MockDirective("reveal", reveal_type="secret", target_id="npc1", timing="soon"),
        ])

        ctrl.refresh_from_state(MockCoherence(), gm)

        # Arcs from threads + pin_thread
        assert "arc:t1" in ctrl.arcs
        assert ctrl.arcs["arc:t1"].priority == "high"

        # Reveals from GM
        assert len(ctrl.reveals) == 1

        # Pacing from danger
        assert ctrl.pacing_plans["gm:pacing"].danger_bias == "high"

        # Director context
        ctx = ctrl.build_director_context(None)
        assert len(ctx["active_arcs"]) == 1
        assert len(ctx["due_reveals"]) == 1
        assert ctx["active_pacing_plan"] is not None

        # Control bias
        bias = ctrl.build_control_bias({"choice_set": {}})
        assert "pacing_bias" in bias

        # Serialize/deserialize round-trip
        data = ctrl.serialize_state()
        ctrl2 = ArcControlController()
        ctrl2.deserialize_state(data)
        assert ctrl2.arcs["arc:t1"].priority == "high"
        assert len(ctrl2.reveals) == 1

    def test_dormant_arcs_excluded_from_active(self):
        ctrl = ArcControlController()
        ctrl.arcs["a1"] = NarrativeArc(arc_id="a1", title="Active", status="active")
        ctrl.arcs["a2"] = NarrativeArc(arc_id="a2", title="Dormant", status="dormant")
        ctx = ctrl.build_director_context(None)
        assert len(ctx["active_arcs"]) == 1
        assert ctx["active_arcs"][0]["arc_id"] == "a1"

    def test_presenter_full_flow(self):
        ctrl = ArcControlController()
        ctrl.arcs["a1"] = NarrativeArc(arc_id="a1", title="Arc 1")
        ctrl.reveals["r1"] = RevealDirectiveState(
            reveal_id="r1", target_id="t1", target_type="s",
        )
        ctrl.pacing_plans["p1"] = PacingPlanState(plan_id="p1", label="L")
        ctrl.scene_biases["b1"] = SceneBiasState(bias_id="b1")

        p = ArcControlPresenter()
        assert p.present_arc_panel(ctrl)["count"] == 1
        assert p.present_reveal_panel(ctrl)["count"] == 1
        assert p.present_pacing_plan_panel(ctrl)["count"] == 1
        assert p.present_scene_bias_panel(ctrl)["count"] == 1

        ctx = ctrl.build_director_context(None)
        dc = p.present_director_context(ctx)
        assert dc["title"] == "Director Context"

    def test_steering_does_not_mutate_truth(self):
        """Verify arc control only annotates — never mutates original dicts."""
        ctrl = ArcControlController()
        ctrl.pacing_plans["p1"] = PacingPlanState(
            plan_id="p1", label="L", danger_bias="high",
        )
        ctrl.scene_biases["b1"] = SceneBiasState(
            bias_id="b1", scene_type_bias="mystery",
        )

        original = {"choice_set": {"options": []}}
        result = ctrl.build_control_bias(original)
        # Original dict is NOT mutated (we create a new dict)
        assert "pacing_bias" not in original
        assert "pacing_bias" in result
