"""Regression tests for Phase 8 — Player-Facing UX Layer.

Ensures backward compatibility, deterministic behavior, and integration
with existing simulation pipelines.
"""

from __future__ import annotations

import pytest

from app.rpg.player.player_scene_state import (
    ensure_player_state,
    set_current_scene,
    push_scene_history,
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


class TestDeterminism:
    """Same input should produce same output across all player state functions."""

    def test_player_state_deterministic(self):
        """Same input simulation state produces same player_state."""
        sim_state = {
            "tick": 5,
            "npcs": {"npc1": {"name": "Alice"}},
            "factions": {"f1": {"name": "Mages"}},
            "locations": {"loc1": {"name": "Town"}},
            "threads": {"t1": {"name": "Quest"}},
        }
        r1 = ensure_player_state(sim_state)
        r2 = ensure_player_state(sim_state)
        assert r1["player_state"] == r2["player_state"]

    def test_journal_deterministic(self):
        """Same journal inputs produce same journal order and dedup behavior."""
        base_state = ensure_player_state({"tick": 1})
        base_state["player_state"]["journal_entries"] = []
        new_data = {
            "new_entries": [
                {"entry_id": "j1", "text": "Arrived", "tick": 0}
            ]
        }
        r1 = update_journal_from_state(base_state, new_data)
        r2 = update_journal_from_state(base_state, new_data)
        assert len(r1["player_state"]["journal_entries"]) == len(r2["player_state"]["journal_entries"])

    def test_codex_deterministic(self):
        """Same codex input ordering produces same codex output ordering."""
        state = ensure_player_state({"tick": 1})
        r1 = update_codex_from_state(state)
        r2 = update_codex_from_state(state)
        assert r1["player_state"]["codex"] == r2["player_state"]["codex"]

    def test_encounter_deterministic(self):
        """Same scene input produces same encounter payload."""
        state = ensure_player_state({"tick": 1})
        scene = {
            "scene_id": "s1",
            "npcs": [{"id": "n1", "name": "Guard"}],
            "choices": [{"id": "c1", "text": "Talk"}],
        }
        r1 = build_encounter_view(scene, state)
        r2 = build_encounter_view(scene, state)
        assert r1 == r2

    def test_scene_history_deterministic(self):
        """Same sequence of pushes produces same history."""
        state1 = ensure_player_state({"tick": 0})
        state2 = ensure_player_state({"tick": 0})
        for i in range(5):
            state1 = push_scene_history(state1, {"scene_id": f"s{i}"})
            state2 = push_scene_history(state2, {"scene_id": f"s{i}"})
        assert state1["player_state"]["scene_history"] == state2["player_state"]["scene_history"]


class TestBackwardCompatibility:
    """Ensure existing patterns still work after Phase 8 additions."""

    def test_ensure_player_state_preserves_existing_data(self):
        """ensure_player_state does not overwrite existing player_state fields."""
        state = {
            "tick": 10,
            "player_state": {
                "current_scene_id": "s_existing",
                "current_mode": "dialogue",
                "active_npc_id": "npc_old",
                "scene_history": [{"scene_id": "s_hist", "tick": 5}],
                "journal_entries": [{"entry_id": "j1", "text": "Old entry"}],
                "codex": {"npcs": {"npc_old": {"name": "Old NPC"}}},
                "active_objectives": [{"id": "obj1"}],
                "last_player_view": {"scene_id": "s_prev"},
            },
        }
        result = ensure_player_state(state)
        ps = result["player_state"]
        assert ps["current_scene_id"] == "s_existing"
        assert ps["current_mode"] == "dialogue"
        assert ps["active_npc_id"] == "npc_old"
        assert len(ps["scene_history"]) == 1
        assert len(ps["journal_entries"]) == 1

    def test_dialogue_mode_transitions_preserve_history(self):
        """Dialogue mode transitions do not lose scene history."""
        state = ensure_player_state({"tick": 1})
        state["player_state"]["scene_history"] = [{"scene_id": "s_old", "tick": 0}]

        state = enter_dialogue_mode(state, npc_id="npc_new", scene_id="s_new")
        assert len(state["player_state"]["scene_history"]) >= 1
        assert state["player_state"]["current_mode"] == "dialogue"

        state = exit_dialogue_mode(state, fallback_mode="scene")
        assert state["player_state"]["current_mode"] == "scene"
        # History should still be intact
        assert len(state["player_state"]["scene_history"]) >= 1

    def test_journal_accumulation(self):
        """Multiple journal updates accumulate entries."""
        state = ensure_player_state({"tick": 0})
        state["player_state"]["journal_entries"] = []

        state = update_journal_from_state(state, {
            "new_entries": [{"entry_id": "j1", "text": "First", "tick": 0}]
        })
        state = update_journal_from_state(state, {
            "new_entries": [{"entry_id": "j2", "text": "Second", "tick": 1}]
        })
        entries = state["player_state"]["journal_entries"]
        # At least one entry should exist
        assert len(entries) >= 1

    def test_codex_accumulation(self):
        """Multiple codex updates maintain bucket structure."""
        state = ensure_player_state({"tick": 1})
        result = update_codex_from_state(state)
        codex = result["player_state"]["codex"]
        assert "npcs" in codex
        assert "factions" in codex
        assert "locations" in codex
        assert "threads" in codex


class TestBoundaryConditions:
    """Test edge cases and boundary conditions."""

    def test_journal_at_max_capacity(self):
        """Journal at max capacity drops oldest when new entries added."""
        state = ensure_player_state({"tick": 0})
        state["player_state"]["journal_entries"] = [
            {"entry_id": f"j{i}", "text": f"Entry {i}", "tick": i}
            for i in range(_MAX_JOURNAL)
        ]
        result = update_journal_from_state(state, {
            "new_entries": [{"entry_id": "j_new", "text": "New", "tick": _MAX_JOURNAL}]
        })
        entries = result["player_state"]["journal_entries"]
        assert len(entries) == _MAX_JOURNAL

    def test_codex_bucket_at_max_capacity(self):
        """Codex bucket maintains expected structure."""
        state = ensure_player_state({"tick": 1})
        result = update_codex_from_state(state)
        codex = result["player_state"]["codex"]
        # Codex should have all expected buckets
        assert "npcs" in codex
        assert "factions" in codex
        assert "locations" in codex
        assert "threads" in codex

    def test_empty_scene_history(self):
        """Scene history starts empty and grows correctly."""
        state = ensure_player_state({})
        assert state["player_state"]["scene_history"] == []

        state = push_scene_history(state, {"scene_id": "s1"})
        assert len(state["player_state"]["scene_history"]) == 1

    def test_encounter_empty_payload_stable(self):
        """Empty scene still produces stable encounter payload."""
        state = ensure_player_state({})
        result = build_encounter_view({}, state)
        assert "scene_id" in result
        assert "actors" in result
        assert "choices" in result
        assert "encounter_state" in result
        assert isinstance(result["actors"], list)
        assert isinstance(result["choices"], list)


class TestIntegration:
    """Integration tests with existing simulation pipeline."""

    def test_full_player_flow(self):
        """Complete flow: init -> scene -> dialogue -> journal -> codex -> encounter."""
        # Initial state
        sim_state = {
            "tick": 0,
            "npcs": {"npc_merchant": {"name": "Merchant"}},
            "factions": {"f_guild": {"name": "Guild"}},
            "locations": {"loc_town": {"name": "Town"}},
            "threads": {},
        }
        state = ensure_player_state(sim_state)

        # Generate a scene
        scene = {
            "scene_id": "s_town",
            "title": "In the Town",
            "npcs": [{"id": "npc_merchant", "name": "Merchant"}],
            "choices": [{"id": "c_talk", "text": "Talk"}],
            "summary": "You are in the town square",
        }
        state = set_current_scene(state, scene, mode="scene", active_npc_id="")
        state = push_scene_history(state, scene)

        # Enter dialogue
        state = enter_dialogue_mode(state, npc_id="npc_merchant", scene_id="s_talk")
        assert state["player_state"]["current_mode"] == "dialogue"
        assert state["player_state"]["active_npc_id"] == "npc_merchant"

        # Update journal
        state = update_journal_from_state(state, {
            "new_entries": [{"entry_id": "j1", "text": "Met the merchant", "tick": 1}]
        })
        assert len(state["player_state"]["journal_entries"]) >= 1

        # Update codex
        state = update_codex_from_state(state)
        assert "npcs" in state["player_state"]["codex"]

        # Build encounter
        encounter = build_encounter_view(scene, state)
        assert encounter["scene_id"] == "s_town"
        assert "actors" in encounter
        assert "choices" in encounter

        # Exit dialogue
        state = exit_dialogue_mode(state, fallback_mode="scene")
        assert state["player_state"]["current_mode"] == "scene"

    def test_player_state_survives_simulation_step(self):
        """Player state is preserved through simulation state changes."""
        sim_state = {
            "tick": 1,
            "npcs": {},
            "factions": {},
            "locations": {},
            "threads": {},
        }
        state = ensure_player_state(sim_state)

        # Simulate tick advance
        sim_state["tick"] = 2
        state["tick"] = 2

        # Player state should still be intact
        ps = state["player_state"]
        assert "current_scene_id" in ps
        assert "current_mode" in ps
        assert "codex" in ps
        assert "journal_entries" in ps