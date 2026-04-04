"""Phase 8.0 — Player-Facing UX Layer — Regression Tests.

Ensures:
- UX payload building does not mutate loop state
- Same loop state gives same scene payload (deterministic)
- Panel order is stable
- Selecting a choice through UX still uses the same underlying event path
"""

from __future__ import annotations

import copy

import pytest

from app.rpg.ux.core import UXCore
from app.rpg.ux.layout import PanelLayout
from app.rpg.ux.payload_builder import UXPayloadBuilder
from app.rpg.ux.action_flow import UXActionFlow
from app.rpg.memory.core import CampaignMemoryCore
from app.rpg.social_state.core import SocialStateCore
from app.rpg.arc_control.controller import ArcControlController
from app.rpg.arc_control.presenters import ArcControlPresenter
from app.rpg.memory.presenters import MemoryPresenter
from app.rpg.packs.registry import PackRegistry
from app.rpg.packs.presenters import PackPresenter


# ======================================================================
# Helpers
# ======================================================================


class _MockCoherenceCore:
    def __init__(self, scene=None, threads=None):
        self._scene = scene or {"location": "tavern"}
        self.active_threads = threads or ["thread_a"]

    def get_scene_summary(self):
        return dict(self._scene)


class _MockFramingState:
    def __init__(self, last_choice_set=None):
        self.last_choice_set = last_choice_set


class _MockFramingEngine:
    def __init__(self, state=None):
        self._state = state or _MockFramingState()

    def get_state(self):
        return self._state


class _MockGameplayController:
    def __init__(self, last_choice_set=None):
        self._last = last_choice_set
        self.framing_engine = _MockFramingEngine(_MockFramingState(last_choice_set))

    def get_last_choice_set(self):
        return self._last

    def select_option(self, option_id):
        if self._last is None:
            return None
        for opt in self._last.get("options", []):
            if opt.get("option_id") == option_id:
                return dict(opt)
        return None


def _build_loop():
    """Build a loop-like object with real subsystems for regression tests."""

    class _Loop:
        pass

    loop = _Loop()
    loop.coherence_core = _MockCoherenceCore()
    loop.campaign_memory_core = CampaignMemoryCore()
    loop.social_state_core = SocialStateCore()
    loop.arc_control_controller = ArcControlController()
    loop.arc_control_presenter = ArcControlPresenter()
    loop.memory_presenter = MemoryPresenter()
    loop.pack_registry = PackRegistry()
    loop.pack_presenter = PackPresenter()
    loop.gameplay_control_controller = _MockGameplayController(
        last_choice_set={
            "options": [
                {"option_id": "o1", "label": "A", "summary": "Action A", "intent_type": "combat"},
                {"option_id": "o2", "label": "B", "summary": "Action B", "intent_type": "explore"},
            ],
        },
    )

    # Resolve path
    loop._resolve_log = []

    def resolve_selected_option(option_id):
        loop._resolve_log.append(option_id)
        option = loop.gameplay_control_controller.select_option(option_id)
        if option is None:
            return {"ok": False, "reason": "unknown_option", "option_id": option_id}
        return {
            "ok": True,
            "resolution": {"resolved_action": option, "events": []},
            "scene_summary": loop.coherence_core.get_scene_summary(),
        }

    loop.resolve_selected_option = resolve_selected_option

    # Panel delegates
    loop.get_journal_panel = lambda: loop.memory_presenter.present_journal_entries(
        [e.to_dict() for e in loop.campaign_memory_core.journal_entries],
    )
    loop.get_recap_panel = lambda: {"title": "Recap", "summary": "", "scene_summary": {}, "active_threads": [], "recent_consequences": [], "social_highlights": []}
    loop.get_codex_panel = lambda: loop.memory_presenter.present_codex(
        [e.to_dict() for e in loop.campaign_memory_core.codex_entries.values()],
    )
    loop.get_campaign_memory_panel = lambda: {"title": "Campaign Memory", "current_scene": {}, "active_threads": [], "resolved_threads": [], "major_consequences": [], "social_summary": {}, "canon_summary": {}}
    loop.get_social_dashboard = lambda: {"title": "Social State", "relationships": [], "rumors": [], "alliances": []}
    loop.get_arc_panel = lambda: loop.arc_control_presenter.present_arc_panel(loop.arc_control_controller)
    loop.get_reveal_panel = lambda: loop.arc_control_presenter.present_reveal_panel(loop.arc_control_controller)
    loop.get_scene_bias_panel = lambda: loop.arc_control_presenter.present_scene_bias_panel(loop.arc_control_controller)
    loop.list_registered_packs = lambda: loop.pack_presenter.present_pack_list([p.to_dict() for p in loop.pack_registry.list_packs()])

    loop.ux_core = UXCore()
    return loop


# ======================================================================
# Determinism Tests
# ======================================================================


class TestScenePayloadIsDeterministicForSameState:
    def test_same_state_produces_same_payload_structure(self):
        """Same loop state should produce the same payload keys, scene,
        choices, and panel list (payload_id will differ)."""
        loop = _build_loop()
        core = UXCore()

        p1 = core.build_scene_payload(loop)
        p2 = core.build_scene_payload(loop)

        # payload_id will be different UUIDs, but everything else should match
        assert p1["scene"] == p2["scene"]
        assert len(p1["choices"]) == len(p2["choices"])
        for c1, c2 in zip(p1["choices"], p2["choices"]):
            assert c1["choice_id"] == c2["choice_id"]
            assert c1["label"] == c2["label"]
        assert len(p1["panels"]) == len(p2["panels"])
        for pa1, pa2 in zip(p1["panels"], p2["panels"]):
            assert pa1["panel_id"] == pa2["panel_id"]
        assert p1["highlights"] == p2["highlights"]

    def test_multiple_calls_do_not_drift(self):
        """Calling build_scene_payload 10 times should yield identical
        structures every time."""
        loop = _build_loop()
        core = UXCore()

        baseline = core.build_scene_payload(loop)
        for _ in range(10):
            current = core.build_scene_payload(loop)
            assert current["scene"] == baseline["scene"]
            assert current["highlights"] == baseline["highlights"]
            assert len(current["choices"]) == len(baseline["choices"])
            assert len(current["panels"]) == len(baseline["panels"])


# ======================================================================
# No Mutation Tests
# ======================================================================


class TestUXPayloadBuilderDoesNotMutateLoopState:
    def test_build_scene_payload_no_mutation(self):
        """Building a scene payload should not change any subsystem state."""
        loop = _build_loop()

        # Snapshot state before
        journal_before = list(loop.campaign_memory_core.journal_entries)
        codex_before = dict(loop.campaign_memory_core.codex_entries)
        social_before = loop.social_state_core.get_state()
        arcs_before = dict(loop.arc_control_controller.arcs)
        reveals_before = dict(loop.arc_control_controller.reveals)

        core = UXCore()
        _ = core.build_scene_payload(loop)

        # Assert nothing changed
        assert list(loop.campaign_memory_core.journal_entries) == journal_before
        assert dict(loop.campaign_memory_core.codex_entries) == codex_before
        assert loop.social_state_core.get_state() is social_before
        assert dict(loop.arc_control_controller.arcs) == arcs_before
        assert dict(loop.arc_control_controller.reveals) == reveals_before

    def test_build_action_result_no_mutation(self):
        """Building an action result payload should not mutate loop state."""
        loop = _build_loop()

        journal_before = list(loop.campaign_memory_core.journal_entries)
        arcs_before = dict(loop.arc_control_controller.arcs)

        core = UXCore()
        _ = core.build_action_result_payload(loop, {"ok": True})

        assert list(loop.campaign_memory_core.journal_entries) == journal_before
        assert dict(loop.arc_control_controller.arcs) == arcs_before


# ======================================================================
# Panel Order Stability Tests
# ======================================================================


class TestPanelLayoutOrderRemainsStable:
    def test_default_order_is_constant(self):
        """Default layout should always be the same sequence."""
        layout = PanelLayout()
        expected = [
            "recap", "journal", "codex", "campaign_memory",
            "social", "arc", "reveals", "packs", "scene_bias",
        ]
        for _ in range(5):
            ids = [p.panel_id for p in layout.build_default_layout()]
            assert ids == expected

    def test_player_layout_order_survives_different_available_sets(self):
        """Even with different available sets, the relative order is the
        same as the default order."""
        layout = PanelLayout()
        default_order = [p.panel_id for p in layout.build_default_layout()]

        sets = [
            {"journal": {}, "social": {}, "packs": {}},
            {"recap": {}, "arc": {}, "scene_bias": {}},
            {"codex": {}, "campaign_memory": {}, "reveals": {}},
        ]
        for available in sets:
            ids = [p.panel_id for p in layout.build_player_layout(available)]
            # Check relative order matches default
            default_indices = [default_order.index(pid) for pid in ids]
            assert default_indices == sorted(default_indices)


# ======================================================================
# Event Path Preservation Tests
# ======================================================================


class TestSelectChoiceViaUXPreservesEventPathExecution:
    def test_choice_goes_through_resolve_selected_option(self):
        """Selecting a choice via UX must call the same
        resolve_selected_option path."""
        loop = _build_loop()
        core = UXCore()

        assert loop._resolve_log == []

        core.select_choice(loop, "o1")

        assert loop._resolve_log == ["o1"]

    def test_unknown_choice_still_goes_through_resolve(self):
        """Even unknown choices should hit the resolve path."""
        loop = _build_loop()
        core = UXCore()

        result = core.select_choice(loop, "nonexistent")

        assert loop._resolve_log == ["nonexistent"]
        assert result["action_result"]["ok"] is False

    def test_multiple_choices_preserve_order(self):
        """Selecting multiple choices records them in order."""
        loop = _build_loop()
        core = UXCore()

        core.select_choice(loop, "o1")
        core.select_choice(loop, "o2")
        core.select_choice(loop, "o1")

        assert loop._resolve_log == ["o1", "o2", "o1"]
