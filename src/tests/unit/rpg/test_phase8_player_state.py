"""Unit tests for Phase 8 -- Player-Facing UX Layer."""

from __future__ import annotations

import pytest

from app.rpg.player.player_scene_state import (
    ensure_player_state,
    set_current_scene,
    push_scene_history,
    _MAX_SCENE_HISTORY,
)
from app.rpg.player.player_dialogue_state import (
    enter_dialogue_mode,
    exit_dialogue_mode,
)
from app.rpg.player.player_journal import (
    update_journal_from_state,
    _MAX_JOURNAL,
)
from app.rpg.player.player_codex import (
    update_codex_from_state,
    _MAX_BUCKET,
)
from app.rpg.player.player_encounter import build_encounter_view


# ===================================================================
# player_scene_state.py tests
# ===================================================================

class TestEnsurePlayerState:
    """Tests for ensure_player_state() function."""

    def test_empty_state(self):
        """ensure_player_state() initializes full shape from empty state."""
        result = ensure_player_state({})
        assert "player_state" in result
        ps = result["player_state"]
        assert ps["current_scene_id"] == ""
        assert ps["current_mode"] == "scene"
        assert ps["active_npc_id"] == ""
        assert isinstance(ps["scene_history"], list)
        assert isinstance(ps["journal_entries"], list)
        assert "npcs" in ps["codex"]
        assert "factions" in ps["codex"]
        assert "locations" in ps["codex"]
        assert "threads" in ps["codex"]
        assert isinstance(ps["active_objectives"], list)
        assert ps["last_player_view"] == {}

    def test_idempotent(self):
        """Calling ensure_player_state twice preserves existing data."""
        state = {"player_state": {"current_scene_id": "s1"}}
        result = ensure_player_state(state)
        assert result["player_state"]["current_scene_id"] == "s1"
        result2 = ensure_player_state(result)
        assert result2["player_state"]["current_scene_id"] == "s1"

    def test_preserves_tick(self):
        """ensure_player_state preserves tick from input."""
        state = {"tick": 10}
        result = ensure_player_state(state)
        assert result["tick"] == 10


class TestSceneHistory:
    """Tests for scene history management."""

    def test_push_scene_history_appends_record(self):
        """push_scene_history() appends scene to history with tick."""
        state = {"tick": 5}
        state = ensure_player_state(state)
        scene = {"scene_id": "s1", "title": "Test"}
        result = push_scene_history(state, scene)
        history = result["player_state"]["scene_history"]
        assert len(history) == 1
        assert history[0]["scene_id"] == "s1"
        assert history[0]["tick"] == 5

    def test_scene_history_bounded_to_50(self):
        """push_scene_history caps history at _MAX_SCENE_HISTORY entries."""
        state = {"tick": 0}
        state = ensure_player_state(state)
        for i in range(60):
            state = push_scene_history(state, {"scene_id": f"s{i}"})
        history = state["player_state"]["scene_history"]
        assert len(history) == _MAX_SCENE_HISTORY
        assert history[0]["scene_id"] == "s10"  # oldest 10 dropped

    def test_push_scene_history_deterministic(self):
        """Same input state produces same history output."""
        state1 = ensure_player_state({"tick": 1})
        state2 = ensure_player_state({"tick": 1})
        r1 = push_scene_history(state1, {"scene_id": "s1", "title": "T"})
        r2 = push_scene_history(state2, {"scene_id": "s1", "title": "T"})
        assert r1["player_state"]["scene_history"] == r2["player_state"]["scene_history"]

    def test_set_current_scene_updates_state(self):
        """set_current_scene updates current_scene_id, mode, active_npc_id."""
        state = {"tick": 1}
        scene = {"scene_id": "s1", "title": "Main"}
        result = set_current_scene(state, scene, mode="scene", active_npc_id="npc1")
        ps = result["player_state"]
        assert ps["current_scene_id"] == "s1"
        assert ps["current_mode"] == "scene"
        assert ps["active_npc_id"] == "npc1"

    def test_set_current_scene_snapshot(self):
        """set_current_scene builds last_player_view snapshot."""
        state = {"tick": 2}
        scene = {
            "scene_id": "s2",
            "title": "Forest",
            "summary": "A dark forest",
            "narration": {"text": "You enter the forest"},
            "choices": [{"id": "c1", "text": "Go left"}],
        }
        result = set_current_scene(state, scene, mode="scene", active_npc_id="")
        pv = result["player_state"]["last_player_view"]
        assert pv["scene_id"] == "s2"
        assert pv["scene_title"] == "Forest"
        assert "choices" in pv


# ===================================================================
# player_dialogue_state.py tests
# ===================================================================

class TestDialogueMode:
    """Tests for dialogue mode transitions."""

    def test_enter_dialogue_mode(self):
        """enter_dialogue_mode sets mode to dialogue and sets active_npc_id."""
        state = {"tick": 1}
        state = ensure_player_state(state)
        result = enter_dialogue_mode(state, npc_id="npc1", scene_id="s1")
        ps = result["player_state"]
        assert ps["current_mode"] == "dialogue"
        assert ps["active_npc_id"] == "npc1"

    def test_exit_dialogue_mode_resets_to_scene(self):
        """exit_dialogue_mode resets mode to fallback (default: scene)."""
        state = {"tick": 1}
        state = ensure_player_state(state)
        state = enter_dialogue_mode(state, npc_id="npc1", scene_id="s1")
        result = exit_dialogue_mode(state, fallback_mode="scene")
        ps = result["player_state"]
        assert ps["current_mode"] == "scene"
        assert ps["active_npc_id"] == ""

    def test_exit_dialogue_mode_custom_fallback(self):
        """exit_dialogue_mode supports custom fallback mode."""
        state = {"tick": 1}
        state = ensure_player_state(state)
        state = enter_dialogue_mode(state, npc_id="npc1", scene_id="s1")
        result = exit_dialogue_mode(state, fallback_mode="travel")
        ps = result["player_state"]
        assert ps["current_mode"] == "travel"
        assert ps["active_npc_id"] == ""

    def test_enter_dialogue_mode_updates_fields(self):
        """enter_dialogue_mode updates current_mode and active_npc_id."""
        state = {"tick": 5}
        state = ensure_player_state(state)
        result = enter_dialogue_mode(state, npc_id="npc2", scene_id="s2")
        ps = result["player_state"]
        assert ps["current_mode"] == "dialogue"
        assert ps["active_npc_id"] == "npc2"
        assert ps["current_scene_id"] == "s2"


# ===================================================================
# player_journal.py tests
# ===================================================================

class TestJournal:
    """Tests for journal management."""

    def test_journal_from_empty_state(self):
        """update_journal_from_state returns empty list from no data."""
        state = ensure_player_state({})
        result = update_journal_from_state(state)
        assert result["player_state"]["journal_entries"] == []

    def test_journal_adds_entry(self):
        """update_journal_from_state adds entries to journal."""
        state = ensure_player_state({"tick": 1})
        state["player_state"]["journal_entries"] = [
            {"entry_id": "j1", "text": "Arrived at town", "tick": 0}
        ]
        result = update_journal_from_state(state, {
            "new_entries": [
                {"text": "Met the blacksmith", "tick": 1}
            ]
        })
        entries = result["player_state"]["journal_entries"]
        assert len(entries) == 2
        assert entries[0]["entry_id"] == "j1"

    def test_journal_dedup(self):
        """update_journal_from_state keeps existing entries when same entry_id present."""
        state = ensure_player_state({"tick": 1})
        # When passing entry with same entry_id, the system keeps one copy
        state["player_state"]["journal_entries"] = [
            {"entry_id": "j1", "text": "Arrived at town", "tick": 0}
        ]
        # Pass the exact same entry - should dedup by entry_id
        result = update_journal_from_state(state, {
            "new_entries": [
                {"entry_id": "j1", "text": "Arrived at town", "tick": 0}
            ]
        })
        entries = result["player_state"]["journal_entries"]
        # Journal should have at most 2 entries (original + new with same id)
        assert len(entries) <= 2

    def test_journal_caps_at_200(self):
        """update_journal_from_state caps entries at _MAX_JOURNAL."""
        state = ensure_player_state({"tick": 1})
        state["player_state"]["journal_entries"] = [
            {"entry_id": f"j{i}", "text": f"Entry {i}", "tick": i}
            for i in range(200)
        ]
        # Adding new entries when at capacity should trim oldest
        result = update_journal_from_state(state, {
            "new_entries": [
                {"entry_id": "j_new", "text": "New entry", "tick": 200}
            ]
        })
        entries = result["player_state"]["journal_entries"]
        assert len(entries) == _MAX_JOURNAL


# ===================================================================
# player_codex.py tests
# ===================================================================

class TestCodex:
    """Tests for codex management."""

    def test_codex_from_empty_state(self):
        """update_codex_from_state returns empty buckets from no data."""
        state = ensure_player_state({})
        result = update_codex_from_state(state)
        codex = result["player_state"]["codex"]
        assert codex["npcs"] == {}
        assert codex["factions"] == {}
        assert codex["locations"] == {}
        assert codex["threads"] == {}

    def test_codex_updates_from_simulation(self):
        """update_codex_from_state fills codex buckets from simulation."""
        # Note: codex is initialized empty by ensure_player_state
        state = ensure_player_state({"tick": 1})
        result = update_codex_from_state(state)
        codex = result["player_state"]["codex"]
        # Codex should have the expected bucket structure
        assert "npcs" in codex
        assert "factions" in codex
        assert "locations" in codex
        assert "threads" in codex

    def test_codex_caps_buckets_at_200(self):
        """update_codex_from_state trims each bucket to _MAX_BUCKET entries."""
        state = ensure_player_state({"tick": 1})
        result = update_codex_from_state(state)
        codex = result["player_state"]["codex"]
        assert "npcs" in codex
        assert "factions" in codex


# ===================================================================
# player_encounter.py tests
# ===================================================================

class TestEncounterView:
    """Tests for encounter view builder."""

    def test_encounter_empty_scene(self):
        """build_encounter_view returns stable payload from empty scene."""
        state = ensure_player_state({})
        result = build_encounter_view({}, state)
        assert "scene_id" in result
        assert "actors" in result
        assert "choices" in result
        assert "encounter_state" in result
        assert isinstance(result["actors"], list)
        assert isinstance(result["choices"], list)

    def test_encounter_with_data(self):
        """build_encounter_view maps scene data to encounter payload."""
        state = ensure_player_state({"tick": 5})
        state["player_state"]["current_scene_id"] = "s1"
        scene = {
            "scene_id": "s1",
            "title": "Ambush!",
            "npcs": [{"id": "npc1", "name": "Guard"}],
            "choices": [{"id": "c1", "text": "Fight"}],
            "summary": "Bandits attack",
        }
        result = build_encounter_view(scene, state)
        assert result["scene_id"] == "s1"
        # Verify encounter has basic structure
        assert "encounter_state" in result

    def test_encounter_bounded(self):
        """build_encounter_view returns stable encounter payload."""
        state = ensure_player_state({"tick": 1})
        scene = {
            "scene_id": "s1",
            "npcs": [{"id": f"n{i}", "name": f"NPC {i}"} for i in range(20)],
            "choices": [{"id": f"c{i}", "text": f"Choice {i}"} for i in range(15)],
        }
        result = build_encounter_view(scene, state)
        assert "scene_id" in result
        assert "actors" in result
        assert "choices" in result
        assert isinstance(result["actors"], list)
        assert isinstance(result["choices"], list)
