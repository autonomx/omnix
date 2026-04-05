"""Functional tests for Phase 4 — Scene / Encounter Generator.

Tests the scene generator in the context of the adventure builder service.
"""

import pytest

from app.rpg.services import adventure_builder_service as abs


def _minimal_setup():
    """Build a minimal setup payload for testing."""
    return {
        "setup_id": "test_phase4_func",
        "title": "Test Adventure",
        "genre": "fantasy",
        "setting": "Test World",
        "premise": "A test premise",
        "factions": [{"faction_id": "f1", "name": "Rebels", "description": "", "goals": []}],
        "locations": [{"location_id": "loc1", "name": "Market", "description": "", "tags": []}],
        "npc_seeds": [
            {"npc_id": "npc1", "name": "Test NPC", "role": "merchant", "description": "", "goals": [], "faction_id": "", "location_id": "", "must_survive": False}
        ],
        "starting_location_id": "loc1",
        "starting_npc_ids": ["npc1"],
        "metadata": {
            "simulation_state": {
                "tick": 1,
                "incidents": [
                    {
                        "id": "inc_1",
                        "type": "thread_crisis",
                        "source_id": "thread_alpha",
                        "summary": "Tensions are rising between factions",
                        "pressure": 3,
                        "severity": "moderate",
                    }
                ],
            }
        },
    }


class TestSceneGenerationService:
    def test_scenes_present_in_response(self):
        """Verify that advance_world_simulation returns a scenes key."""
        result = abs.advance_world_simulation(_minimal_setup())
        assert result.get("success") is True
        assert "scenes" in result
        assert isinstance(result["scenes"], list)

    def test_scenes_populated_from_incidents(self):
        """Verify that incidents are converted to scenes."""
        result = abs.advance_world_simulation(_minimal_setup())
        scenes = result.get("scenes", [])
        # At least one scene should be generated from our incident
        assert len(scenes) >= 1

    def test_scene_structure(self):
        """Verify generated scenes have the expected structure."""
        result = abs.advance_world_simulation(_minimal_setup())
        scenes = result.get("scenes", [])
        if scenes:
            scene = scenes[0]
            assert "scene_id" in scene
            assert "type" in scene
            assert "title" in scene
            assert "summary" in scene
            assert "actors" in scene
            assert "stakes" in scene
            assert isinstance(scene["actors"], list)

    def test_empty_incidents_produces_empty_scenes(self):
        """Verify that no incidents results in empty scenes list."""
        payload = _minimal_setup()
        payload["metadata"]["simulation_state"]["incidents"] = []
        result = abs.advance_world_simulation(payload)
        assert result.get("scenes") == []