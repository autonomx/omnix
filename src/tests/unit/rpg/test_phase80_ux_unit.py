"""Phase 8.0 — Player-Facing UX Layer — Unit Tests.

Covers:
- models: PlayerChoiceCard, PanelDescriptor, SceneUXPayload,
          ActionResultPayload roundtrips
- layout: PanelLayout default ordering, player layout filtering
- payload_builder: choice-card conversion, panel descriptors, highlights
- action_flow: panel routing
- presenters: output shape stability
"""

from __future__ import annotations

import pytest

from app.rpg.ux.models import (
    ActionResultPayload,
    PanelDescriptor,
    PlayerChoiceCard,
    SceneUXPayload,
)
from app.rpg.ux.layout import PanelLayout
from app.rpg.ux.payload_builder import UXPayloadBuilder
from app.rpg.ux.action_flow import UXActionFlow
from app.rpg.ux.presenters import UXPresenter
from app.rpg.ux.core import UXCore


# ======================================================================
# Model Roundtrip Tests
# ======================================================================


class TestPlayerChoiceCardRoundtrip:
    def test_basic_roundtrip(self):
        card = PlayerChoiceCard(
            choice_id="c1",
            label="Attack",
            summary="Strike the enemy",
            intent_type="combat",
            target_id="npc_goblin",
            tags=["combat", "melee"],
            priority=1.5,
            metadata={"weapon": "sword"},
        )
        d = card.to_dict()
        restored = PlayerChoiceCard.from_dict(d)
        assert restored.choice_id == "c1"
        assert restored.label == "Attack"
        assert restored.summary == "Strike the enemy"
        assert restored.intent_type == "combat"
        assert restored.target_id == "npc_goblin"
        assert restored.tags == ["combat", "melee"]
        assert restored.priority == 1.5
        assert restored.metadata == {"weapon": "sword"}

    def test_defaults(self):
        card = PlayerChoiceCard(
            choice_id="c2", label="Look", summary="Look around",
            intent_type="explore",
        )
        d = card.to_dict()
        assert d["target_id"] is None
        assert d["tags"] == []
        assert d["priority"] == 0.0
        assert d["metadata"] == {}

    def test_from_dict_with_missing_keys(self):
        card = PlayerChoiceCard.from_dict({})
        assert card.choice_id == ""
        assert card.label == ""
        assert card.priority == 0.0

    def test_dict_is_independent_copy(self):
        card = PlayerChoiceCard(
            choice_id="c3", label="X", summary="Y",
            intent_type="z", tags=["a"], metadata={"k": "v"},
        )
        d = card.to_dict()
        d["tags"].append("injected")
        d["metadata"]["injected"] = True
        assert card.tags == ["a"]
        assert "injected" not in card.metadata


class TestPanelDescriptorRoundtrip:
    def test_basic_roundtrip(self):
        desc = PanelDescriptor(
            panel_id="journal",
            title="Journal",
            panel_type="journal",
            count=5,
            metadata={"filter": "recent"},
        )
        d = desc.to_dict()
        restored = PanelDescriptor.from_dict(d)
        assert restored.panel_id == "journal"
        assert restored.title == "Journal"
        assert restored.panel_type == "journal"
        assert restored.count == 5
        assert restored.metadata == {"filter": "recent"}

    def test_defaults(self):
        desc = PanelDescriptor(
            panel_id="recap", title="Recap", panel_type="recap",
        )
        d = desc.to_dict()
        assert d["count"] is None
        assert d["metadata"] == {}

    def test_from_dict_with_missing_keys(self):
        desc = PanelDescriptor.from_dict({})
        assert desc.panel_id == ""
        assert desc.count is None


class TestSceneUXPayloadRoundtrip:
    def test_basic_roundtrip(self):
        card = PlayerChoiceCard(
            choice_id="c1", label="Go", summary="Go north",
            intent_type="move",
        )
        panel = PanelDescriptor(
            panel_id="journal", title="Journal", panel_type="journal",
        )
        payload = SceneUXPayload(
            payload_id="p1",
            scene={"location": "forest"},
            choices=[card],
            panels=[panel],
            highlights={"threads": 3},
            metadata={"tick": 1},
        )
        d = payload.to_dict()
        restored = SceneUXPayload.from_dict(d)
        assert restored.payload_id == "p1"
        assert restored.scene == {"location": "forest"}
        assert len(restored.choices) == 1
        assert restored.choices[0].choice_id == "c1"
        assert len(restored.panels) == 1
        assert restored.panels[0].panel_id == "journal"
        assert restored.highlights == {"threads": 3}
        assert restored.metadata == {"tick": 1}

    def test_empty_payload(self):
        payload = SceneUXPayload(payload_id="empty", scene={})
        d = payload.to_dict()
        assert d["choices"] == []
        assert d["panels"] == []
        assert d["highlights"] == {}

    def test_from_dict_with_missing_keys(self):
        restored = SceneUXPayload.from_dict({})
        assert restored.payload_id == ""
        assert restored.choices == []


class TestActionResultPayloadRoundtrip:
    def test_basic_roundtrip(self):
        card = PlayerChoiceCard(
            choice_id="c2", label="X", summary="Y",
            intent_type="z",
        )
        panel = PanelDescriptor(
            panel_id="recap", title="Recap", panel_type="recap",
        )
        payload = ActionResultPayload(
            result_id="r1",
            action_result={"ok": True, "resolution": {}},
            updated_scene={"location": "cave"},
            updated_choices=[card],
            updated_panels=[panel],
            metadata={"tick": 2},
        )
        d = payload.to_dict()
        restored = ActionResultPayload.from_dict(d)
        assert restored.result_id == "r1"
        assert restored.action_result["ok"] is True
        assert restored.updated_scene == {"location": "cave"}
        assert len(restored.updated_choices) == 1
        assert len(restored.updated_panels) == 1

    def test_empty_result(self):
        payload = ActionResultPayload(result_id="r2", action_result={})
        d = payload.to_dict()
        assert d["updated_choices"] == []
        assert d["updated_panels"] == []


# ======================================================================
# Layout Tests
# ======================================================================


class TestPanelLayoutBuildsDefaultOrder:
    def test_default_layout_order(self):
        layout = PanelLayout()
        panels = layout.build_default_layout()
        ids = [p.panel_id for p in panels]
        assert ids == [
            "recap", "journal", "codex", "campaign_memory",
            "social", "arc", "reveals", "packs", "scene_bias",
        ]

    def test_default_layout_types(self):
        layout = PanelLayout()
        panels = layout.build_default_layout()
        types = [p.panel_type for p in panels]
        assert "recap" in types
        assert "journal" in types
        assert "codex" in types

    def test_default_layout_count_is_none(self):
        layout = PanelLayout()
        for p in layout.build_default_layout():
            assert p.count is None


class TestPanelLayoutBuildsPlayerLayout:
    def test_filters_to_available_only(self):
        layout = PanelLayout()
        available = {
            "journal": {"count": 5},
            "social": {},
        }
        panels = layout.build_player_layout(available)
        ids = [p.panel_id for p in panels]
        assert ids == ["journal", "social"]

    def test_preserves_deterministic_order(self):
        layout = PanelLayout()
        available = {
            "packs": {"count": 2},
            "recap": {"count": 1},
            "arc": {"count": 3},
        }
        panels = layout.build_player_layout(available)
        ids = [p.panel_id for p in panels]
        assert ids == ["recap", "arc", "packs"]

    def test_count_passed_through(self):
        layout = PanelLayout()
        available = {"journal": {"count": 10}}
        panels = layout.build_player_layout(available)
        assert panels[0].count == 10

    def test_empty_available_returns_empty(self):
        layout = PanelLayout()
        panels = layout.build_player_layout({})
        assert panels == []


# ======================================================================
# Payload Builder Tests
# ======================================================================


class _MockCoherenceCore:
    """Minimal mock for coherence core used by payload builder."""

    def __init__(self, threads=None, scene_summary=None):
        self.active_threads = threads or []
        self._scene_summary = scene_summary or {}

    def get_scene_summary(self):
        return dict(self._scene_summary)


class _MockChoiceSet:
    """Minimal mock for framing state."""

    def __init__(self, options=None):
        self.options = options or []


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
        self._last_choice_set = last_choice_set
        self.framing_engine = _MockFramingEngine(
            _MockFramingState(last_choice_set),
        )

    def get_last_choice_set(self):
        return self._last_choice_set


class _MockArcController:
    def __init__(self, arcs=None, reveals=None, scene_biases=None):
        self.arcs = arcs or {}
        self.reveals = reveals or {}
        self.pacing_plans = {}
        self.scene_biases = scene_biases or {}


class _MockSocialState:
    def __init__(self, relationships=None, rumors=None, alliances=None):
        self.relationships = relationships or {}
        self.rumors = rumors or {}
        self.alliances = alliances or {}


class _MockSocialStateCore:
    def __init__(self, state=None):
        self._state = state or _MockSocialState()

    def get_state(self):
        return self._state


class _MockCampaignMemoryCore:
    def __init__(self, journal=None, recap=None, codex=None, snapshot=None):
        self.journal_entries = journal or []
        self.last_recap = recap
        self.codex_entries = codex or {}
        self.last_campaign_snapshot = snapshot


class _MockPackRegistry:
    def __init__(self, packs=None):
        self._packs = packs or []

    def list_packs(self):
        return list(self._packs)


class _MockLoop:
    """Minimal mock of GameLoop for UX tests."""

    def __init__(
        self,
        coherence_core=None,
        gameplay_control_controller=None,
        campaign_memory_core=None,
        social_state_core=None,
        arc_control_controller=None,
        pack_registry=None,
    ):
        self.coherence_core = coherence_core
        self.gameplay_control_controller = gameplay_control_controller
        self.campaign_memory_core = campaign_memory_core
        self.social_state_core = social_state_core
        self.arc_control_controller = arc_control_controller
        self.pack_registry = pack_registry


class TestPayloadBuilderBuildsChoiceCardsFromControlOutput:
    def test_converts_options_to_cards(self):
        builder = UXPayloadBuilder()
        control_output = {
            "choice_set": {
                "options": [
                    {
                        "option_id": "opt1",
                        "label": "Attack",
                        "summary": "Strike enemy",
                        "intent_type": "combat",
                        "target_id": "goblin",
                        "tags": ["melee"],
                        "priority": 2.0,
                    },
                    {
                        "option_id": "opt2",
                        "label": "Flee",
                        "description": "Run away",
                        "type": "escape",
                    },
                ],
            },
        }
        cards = builder._build_choice_cards(control_output)
        assert len(cards) == 2
        assert cards[0].choice_id == "opt1"
        assert cards[0].label == "Attack"
        assert cards[0].priority == 2.0
        assert cards[1].choice_id == "opt2"
        assert cards[1].summary == "Run away"
        assert cards[1].intent_type == "escape"

    def test_empty_control_output(self):
        builder = UXPayloadBuilder()
        assert builder._build_choice_cards(None) == []
        assert builder._build_choice_cards({}) == []

    def test_no_options_key(self):
        builder = UXPayloadBuilder()
        cards = builder._build_choice_cards({"choice_set": {}})
        assert cards == []


class TestPayloadBuilderBuildsPanelDescriptors:
    def test_builds_descriptors_from_subsystems(self):
        loop = _MockLoop(
            campaign_memory_core=_MockCampaignMemoryCore(
                journal=["e1", "e2"],
                codex={"c1": {}, "c2": {}},
            ),
            social_state_core=_MockSocialStateCore(),
            arc_control_controller=_MockArcController(),
            pack_registry=_MockPackRegistry(),
        )
        builder = UXPayloadBuilder()
        panels = builder._build_panel_descriptors(loop)
        ids = [p.panel_id for p in panels]
        assert "journal" in ids
        assert "recap" in ids
        assert "codex" in ids
        assert "social" in ids

    def test_no_subsystems_returns_empty(self):
        loop = _MockLoop()
        builder = UXPayloadBuilder()
        panels = builder._build_panel_descriptors(loop)
        assert panels == []


class TestPayloadBuilderBuildsHighlights:
    def test_highlights_include_active_threads(self):
        loop = _MockLoop(
            coherence_core=_MockCoherenceCore(
                threads=["t1", "t2"],
                scene_summary={"location": "forest"},
            ),
            arc_control_controller=_MockArcController(),
            social_state_core=_MockSocialStateCore(),
        )
        builder = UXPayloadBuilder()
        highlights = builder._build_highlights(loop)
        assert highlights["active_threads_count"] == 2
        assert highlights["current_location"] == "forest"

    def test_highlights_no_subsystems(self):
        loop = _MockLoop()
        builder = UXPayloadBuilder()
        highlights = builder._build_highlights(loop)
        assert highlights == {}

    def test_highlights_social_warning_none_when_no_negative_trust(self):
        loop = _MockLoop(
            social_state_core=_MockSocialStateCore(),
        )
        builder = UXPayloadBuilder()
        highlights = builder._build_highlights(loop)
        assert highlights.get("social_warning") is None


class TestPayloadBuilderBuildsScenePayload:
    def test_scene_payload_shape(self):
        loop = _MockLoop(
            coherence_core=_MockCoherenceCore(
                scene_summary={"location": "tavern"},
            ),
            gameplay_control_controller=_MockGameplayController(
                last_choice_set={
                    "options": [
                        {"option_id": "o1", "label": "Drink", "summary": "Have a drink", "intent_type": "social"},
                    ],
                },
            ),
            campaign_memory_core=_MockCampaignMemoryCore(),
            social_state_core=_MockSocialStateCore(),
            arc_control_controller=_MockArcController(),
            pack_registry=_MockPackRegistry(),
        )
        builder = UXPayloadBuilder()
        payload = builder.build_scene_payload(loop)
        assert payload.payload_id  # non-empty UUID
        assert payload.scene == {"location": "tavern"}
        assert len(payload.choices) == 1
        assert payload.choices[0].choice_id == "o1"
        assert len(payload.panels) > 0


class TestPayloadBuilderBuildsActionResultPayload:
    def test_action_result_payload_shape(self):
        loop = _MockLoop(
            coherence_core=_MockCoherenceCore(
                scene_summary={"location": "cave"},
            ),
        )
        builder = UXPayloadBuilder()
        result = builder.build_action_result_payload(loop, {"ok": True, "resolution": {}})
        assert result.result_id  # non-empty UUID
        assert result.action_result == {"ok": True, "resolution": {}}
        assert result.updated_scene == {"location": "cave"}


# ======================================================================
# UX Presenter Tests
# ======================================================================


class TestUXPresenterReturnsUISafeScenePayload:
    def test_scene_payload_whitelist(self):
        presenter = UXPresenter()
        raw = {
            "payload_id": "p1",
            "scene": {"location": "forest"},
            "choices": [
                {"choice_id": "c1", "label": "Go", "summary": "Move",
                 "intent_type": "move", "tags": [], "priority": 0.0},
            ],
            "panels": [
                {"panel_id": "journal", "title": "Journal",
                 "panel_type": "journal", "count": 3},
            ],
            "highlights": {"threads": 2},
            "metadata": {"internal": "should_be_dropped"},
        }
        result = presenter.present_scene_payload(raw)
        assert result["payload_id"] == "p1"
        assert result["scene"] == {"location": "forest"}
        assert len(result["choices"]) == 1
        assert len(result["panels"]) == 1
        # metadata should NOT be in the presented output
        assert "metadata" not in result

    def test_action_result_whitelist(self):
        presenter = UXPresenter()
        raw = {
            "result_id": "r1",
            "action_result": {"ok": True},
            "updated_scene": {},
            "updated_choices": [],
            "updated_panels": [],
            "metadata": {"should": "drop"},
        }
        result = presenter.present_action_result_payload(raw)
        assert result["result_id"] == "r1"
        assert "metadata" not in result


class TestUXPresenterChoiceCard:
    def test_card_whitelist(self):
        presenter = UXPresenter()
        card = {
            "choice_id": "c1", "label": "X", "summary": "Y",
            "intent_type": "z", "target_id": None,
            "tags": ["a"], "priority": 1.0,
            "metadata": {"internal": True},
        }
        result = presenter.present_choice_card(card)
        assert result["choice_id"] == "c1"
        assert "metadata" not in result

    def test_panel_descriptor_whitelist(self):
        presenter = UXPresenter()
        desc = {
            "panel_id": "journal", "title": "Journal",
            "panel_type": "journal", "count": 5,
            "metadata": {"internal": True},
        }
        result = presenter.present_panel_descriptor(desc)
        assert result["panel_id"] == "journal"
        assert "metadata" not in result


# ======================================================================
# Action Flow Tests
# ======================================================================


class TestActionFlowOpenPanelRoutesToCorrectLoopMethod:
    def test_routes_journal(self):
        class _Loop:
            def get_journal_panel(self):
                return {"title": "Journal", "items": [], "count": 0}

        flow = UXActionFlow()
        result = flow.open_panel(_Loop(), "journal")
        assert result["title"] == "Journal"

    def test_routes_recap(self):
        class _Loop:
            def get_recap_panel(self):
                return {"title": "Recap", "summary": "..."}

        flow = UXActionFlow()
        result = flow.open_panel(_Loop(), "recap")
        assert result["title"] == "Recap"

    def test_routes_codex(self):
        class _Loop:
            def get_codex_panel(self):
                return {"title": "Codex", "items": [], "count": 0}

        flow = UXActionFlow()
        result = flow.open_panel(_Loop(), "codex")
        assert result["title"] == "Codex"

    def test_routes_campaign_memory(self):
        class _Loop:
            def get_campaign_memory_panel(self):
                return {"title": "Campaign Memory"}

        flow = UXActionFlow()
        result = flow.open_panel(_Loop(), "campaign_memory")
        assert result["title"] == "Campaign Memory"

    def test_routes_social(self):
        class _Loop:
            def get_social_dashboard(self):
                return {"title": "Social State"}

        flow = UXActionFlow()
        result = flow.open_panel(_Loop(), "social")
        assert result["title"] == "Social State"

    def test_routes_arc(self):
        class _Loop:
            def get_arc_panel(self):
                return {"title": "Arcs", "items": [], "count": 0}

        flow = UXActionFlow()
        result = flow.open_panel(_Loop(), "arc")
        assert result["title"] == "Arcs"

    def test_routes_reveals(self):
        class _Loop:
            def get_reveal_panel(self):
                return {"title": "Reveals", "items": [], "count": 0}

        flow = UXActionFlow()
        result = flow.open_panel(_Loop(), "reveals")
        assert result["title"] == "Reveals"

    def test_routes_packs(self):
        class _Loop:
            def list_registered_packs(self):
                return {"title": "Adventure Packs", "items": [], "count": 0}

        flow = UXActionFlow()
        result = flow.open_panel(_Loop(), "packs")
        assert result["title"] == "Adventure Packs"

    def test_routes_scene_bias(self):
        class _Loop:
            def get_scene_bias_panel(self):
                return {"title": "Scene Bias", "items": [], "count": 0}

        flow = UXActionFlow()
        result = flow.open_panel(_Loop(), "scene_bias")
        assert result["title"] == "Scene Bias"

    def test_unknown_panel_returns_error(self):
        flow = UXActionFlow()
        result = flow.open_panel(object(), "nonexistent")
        assert result["error"] == "unknown_panel"

    def test_missing_method_returns_error(self):
        flow = UXActionFlow()
        result = flow.open_panel(object(), "journal")
        assert result["error"] == "panel_not_available"


class TestActionFlowGetCurrentScene:
    def test_returns_scene_dict(self):
        loop = _MockLoop(
            coherence_core=_MockCoherenceCore(
                scene_summary={"location": "tavern"},
            ),
        )
        flow = UXActionFlow()
        result = flow.get_current_scene(loop)
        assert "payload_id" in result
        assert result["scene"] == {"location": "tavern"}


class TestActionFlowGetCurrentChoices:
    def test_returns_choices_only(self):
        loop = _MockLoop(
            gameplay_control_controller=_MockGameplayController(
                last_choice_set={
                    "options": [
                        {"option_id": "o1", "label": "Go", "summary": "Move", "intent_type": "move"},
                    ],
                },
            ),
        )
        flow = UXActionFlow()
        result = flow.get_current_choices(loop)
        assert "choices" in result
        assert len(result["choices"]) == 1
        assert result["choices"][0]["choice_id"] == "o1"


class TestActionFlowRequestRecap:
    def test_returns_recap(self):
        class _Loop:
            def get_recap_panel(self):
                return {"title": "Recap", "summary": "Things happened."}

        flow = UXActionFlow()
        result = flow.request_recap(_Loop())
        assert result["title"] == "Recap"

    def test_fallback_when_no_method(self):
        flow = UXActionFlow()
        result = flow.request_recap(object())
        assert result["title"] == "Recap"


# ======================================================================
# UXCore Facade Tests
# ======================================================================


class TestUXCoreInitialization:
    def test_creates_all_components(self):
        core = UXCore()
        assert isinstance(core.layout, PanelLayout)
        assert isinstance(core.payload_builder, UXPayloadBuilder)
        assert isinstance(core.action_flow, UXActionFlow)
        assert isinstance(core.presenter, UXPresenter)


class TestUXCoreBuildScenePayload:
    def test_returns_presented_payload(self):
        loop = _MockLoop(
            coherence_core=_MockCoherenceCore(
                scene_summary={"location": "forest"},
            ),
        )
        core = UXCore()
        result = core.build_scene_payload(loop)
        assert "payload_id" in result
        assert result["scene"] == {"location": "forest"}
        # Presented output should not have metadata
        assert "metadata" not in result


class TestUXCoreOpenPanel:
    def test_delegates_to_action_flow(self):
        class _Loop:
            def get_journal_panel(self):
                return {"title": "Journal", "items": [], "count": 0}

        core = UXCore()
        result = core.open_panel(_Loop(), "journal")
        assert result["title"] == "Journal"


class TestUXCoreRequestRecap:
    def test_delegates_to_action_flow(self):
        class _Loop:
            def get_recap_panel(self):
                return {"title": "Recap", "summary": "All done."}

        core = UXCore()
        result = core.request_recap(_Loop())
        assert result["title"] == "Recap"
