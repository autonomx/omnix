"""Phase 8.0 — Player-Facing UX Layer — Functional Tests.

End-to-end tests verifying UX operations through the GameLoop
integration layer: scene payloads, action results, panels, recaps.
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
from app.rpg.memory.core import CampaignMemoryCore
from app.rpg.social_state.core import SocialStateCore
from app.rpg.arc_control.controller import ArcControlController
from app.rpg.arc_control.presenters import ArcControlPresenter
from app.rpg.memory.presenters import MemoryPresenter
from app.rpg.packs.registry import PackRegistry
from app.rpg.packs.presenters import PackPresenter


# ======================================================================
# Helpers — Lightweight mock loop with real subsystems
# ======================================================================


class _MockCoherenceCore:
    """Lightweight coherence core mock with real-ish API."""

    def __init__(self):
        self.active_threads = []
        self._scene = {"location": "tavern", "npcs_present": ["bartender"]}

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


class _FunctionalLoop:
    """Simulates the GameLoop with real subsystem instances for UX tests."""

    def __init__(self):
        self.coherence_core = _MockCoherenceCore()
        self.campaign_memory_core = CampaignMemoryCore()
        self.social_state_core = SocialStateCore()
        self.arc_control_controller = ArcControlController()
        self.arc_control_presenter = ArcControlPresenter()
        self.memory_presenter = MemoryPresenter()
        self.pack_registry = PackRegistry()
        self.pack_presenter = PackPresenter()
        self.gameplay_control_controller = _MockGameplayController(
            last_choice_set={
                "options": [
                    {
                        "option_id": "talk_bartender",
                        "label": "Talk to bartender",
                        "summary": "Strike up a conversation",
                        "intent_type": "social_contact",
                        "target_id": "bartender",
                        "tags": ["social"],
                        "priority": 1.0,
                    },
                    {
                        "option_id": "explore_back",
                        "label": "Explore back room",
                        "summary": "Investigate the back room",
                        "intent_type": "explore",
                        "tags": ["explore"],
                        "priority": 0.5,
                    },
                ],
            },
        )
        self.ux_core = UXCore()

        # Resolve option simulation
        self._last_resolution = None

    def resolve_selected_option(self, option_id):
        """Simplified resolve: return a mock resolution dict."""
        option = self.gameplay_control_controller.select_option(option_id)
        if option is None:
            return {"ok": False, "reason": "unknown_option", "option_id": option_id}
        self._last_resolution = {
            "ok": True,
            "resolution": {
                "resolved_action": option,
                "events": [],
            },
            "scene_summary": self.coherence_core.get_scene_summary(),
        }
        return self._last_resolution

    # Panel delegates (mirrors GameLoop)
    def get_journal_panel(self):
        entries = [e.to_dict() for e in self.campaign_memory_core.journal_entries]
        return self.memory_presenter.present_journal_entries(entries)

    def get_recap_panel(self):
        recap = self.campaign_memory_core.last_recap
        if recap is None:
            return {"title": "Recap", "summary": "", "scene_summary": {}, "active_threads": [], "recent_consequences": [], "social_highlights": []}
        return self.memory_presenter.present_recap(recap.to_dict())

    def get_codex_panel(self):
        entries = [e.to_dict() for e in self.campaign_memory_core.codex_entries.values()]
        return self.memory_presenter.present_codex(entries)

    def get_campaign_memory_panel(self):
        snapshot = self.campaign_memory_core.last_campaign_snapshot
        if snapshot is None:
            return {"title": "Campaign Memory", "current_scene": {}, "active_threads": [], "resolved_threads": [], "major_consequences": [], "social_summary": {}, "canon_summary": {}}
        return self.memory_presenter.present_campaign_memory(snapshot.to_dict())

    def get_social_dashboard(self):
        state = self.social_state_core.get_state()
        return {
            "title": "Social State",
            "relationships": [r.to_dict() for r in state.relationships.values()],
            "rumors": [r.to_dict() for r in state.rumors.values()],
            "alliances": [a.to_dict() for a in state.alliances.values()],
        }

    def get_arc_panel(self):
        return self.arc_control_presenter.present_arc_panel(self.arc_control_controller)

    def get_reveal_panel(self):
        return self.arc_control_presenter.present_reveal_panel(self.arc_control_controller)

    def get_scene_bias_panel(self):
        return self.arc_control_presenter.present_scene_bias_panel(self.arc_control_controller)

    def list_registered_packs(self):
        packs = self.pack_registry.list_packs()
        return self.pack_presenter.present_pack_list([p.to_dict() for p in packs])

    # UX delegates
    def get_scene_payload(self):
        return self.ux_core.build_scene_payload(self)

    def get_action_result_payload(self, action_result):
        return self.ux_core.build_action_result_payload(self, action_result)

    def select_choice_via_ux(self, choice_id):
        return self.ux_core.select_choice(self, choice_id)

    def open_panel(self, panel_id):
        return self.ux_core.open_panel(self, panel_id)

    def request_recap_via_ux(self):
        return self.ux_core.request_recap(self)


# ======================================================================
# Functional Tests
# ======================================================================


class TestGetScenePayloadReturnsComposedPlayerPayload:
    def test_payload_contains_scene_choices_panels(self):
        loop = _FunctionalLoop()
        payload = loop.get_scene_payload()

        assert "payload_id" in payload
        assert payload["scene"]["location"] == "tavern"
        assert len(payload["choices"]) == 2
        assert payload["choices"][0]["choice_id"] == "talk_bartender"
        assert len(payload["panels"]) > 0

    def test_payload_highlights_present(self):
        loop = _FunctionalLoop()
        payload = loop.get_scene_payload()
        assert "highlights" in payload

    def test_panel_ids_in_payload(self):
        loop = _FunctionalLoop()
        payload = loop.get_scene_payload()
        panel_ids = [p["panel_id"] for p in payload["panels"]]
        # Should include at least recap, journal, codex
        assert "recap" in panel_ids
        assert "journal" in panel_ids
        assert "codex" in panel_ids


class TestSelectChoiceViaUXReturnsActionResultPayload:
    def test_valid_choice_returns_result(self):
        loop = _FunctionalLoop()
        result = loop.select_choice_via_ux("talk_bartender")

        assert "result_id" in result
        assert result["action_result"]["ok"] is True
        assert "updated_scene" in result
        assert "updated_choices" in result
        assert "updated_panels" in result

    def test_unknown_choice_returns_error(self):
        loop = _FunctionalLoop()
        result = loop.select_choice_via_ux("nonexistent")

        assert result["action_result"]["ok"] is False
        assert result["action_result"]["reason"] == "unknown_option"


class TestOpenPanelReturnsRequestedPresentedPanel:
    def test_journal_panel(self):
        loop = _FunctionalLoop()
        result = loop.open_panel("journal")
        assert result["title"] == "Journal"
        assert "items" in result
        assert "count" in result

    def test_recap_panel(self):
        loop = _FunctionalLoop()
        result = loop.open_panel("recap")
        assert result["title"] == "Recap"

    def test_codex_panel(self):
        loop = _FunctionalLoop()
        result = loop.open_panel("codex")
        assert result["title"] == "Codex"

    def test_campaign_memory_panel(self):
        loop = _FunctionalLoop()
        result = loop.open_panel("campaign_memory")
        assert result["title"] == "Campaign Memory"

    def test_social_panel(self):
        loop = _FunctionalLoop()
        result = loop.open_panel("social")
        assert result["title"] == "Social State"

    def test_arc_panel(self):
        loop = _FunctionalLoop()
        result = loop.open_panel("arc")
        assert result["title"] == "Arcs"

    def test_packs_panel(self):
        loop = _FunctionalLoop()
        result = loop.open_panel("packs")
        assert result["title"] == "Adventure Packs"

    def test_unknown_panel_returns_error(self):
        loop = _FunctionalLoop()
        result = loop.open_panel("nonexistent")
        assert result["error"] == "unknown_panel"


class TestRequestRecapViaUXReturnsRecapPayload:
    def test_recap_payload_shape(self):
        loop = _FunctionalLoop()
        result = loop.request_recap_via_ux()
        assert result["title"] == "Recap"
        # Default empty recap has expected keys
        assert "summary" in result
        assert "scene_summary" in result
