"""Regression tests for Phase 4 — Scene / Encounter Generator.

Ensures scene generation remains backward-compatible and doesn't break
existing simulation flows.
"""

import pytest

from app.rpg.creator.world_scene_generator import (
    SCENE_TYPE_CONFLICT,
    SCENE_TYPE_ENCOUNTER,
    SCENE_TYPE_POLITICAL,
    SCENE_TYPE_INVESTIGATION,
    SCENE_TYPE_NEGOTIATION,
    generate_scenes_from_incidents,
    generate_scenes_from_simulation,
)
from app.rpg.services import adventure_builder_service as abs


class TestSceneGenerationRegression:
    """Regression tests to ensure scene generation doesn't break existing flows."""

    def test_scenes_key_always_present_in_simulation_response(self):
        """Ensure the scenes key is always in the simulation response, even if empty."""
        payload = {
            "setup_id": "test_regression",
            "title": "Regression",
            "genre": "fantasy",
            "setting": "Test",
            "premise": "Test",
            "factions": [],
            "locations": [],
            "npc_seeds": [],
            "starting_location_id": None,
            "starting_npc_ids": [],
            "metadata": {},
        }
        result = abs.advance_world_simulation(payload)
        assert "scenes" in result
        assert isinstance(result["scenes"], list)

    def test_scene_id_uniqueness(self):
        """Ensure that scene IDs are unique for different incidents."""
        incidents = [
            {"id": "i1", "type": "thread_crisis", "source_id": "t1", "summary": "Crisis 1"},
            {"id": "i2", "type": "thread_crisis", "source_id": "t2", "summary": "Crisis 2"},
        ]
        scenes = generate_scenes_from_incidents(incidents)
        scene_ids = [s["scene_id"] for s in scenes]
        assert len(scene_ids) == len(set(scene_ids))

    def test_scene_type_values_are_valid(self):
        """Ensure scene type values are from the valid set."""
        valid_types = {
            SCENE_TYPE_CONFLICT,
            SCENE_TYPE_ENCOUNTER,
            SCENE_TYPE_POLITICAL,
            SCENE_TYPE_INVESTIGATION,
            SCENE_TYPE_NEGOTIATION,
        }
        incidents = [
            {"id": "i1", "type": "thread_crisis", "source_id": "t1", "summary": "Crisis"},
            {"id": "i2", "type": "location_flashpoint", "source_id": "l1", "summary": "Flash"},
            {"id": "i3", "type": "faction_instability", "source_id": "f1", "summary": "Split"},
        ]
        scenes = generate_scenes_from_incidents(incidents)
        for scene in scenes:
            assert scene["type"] in valid_types

    def test_no_mutation_of_input_incidents(self):
        """Ensure the input incidents list is not mutated."""
        incidents = [
            {"id": "i1", "type": "thread_crisis", "source_id": "t1", "summary": "Crisis"},
        ]
        import copy
        original = copy.deepcopy(incidents)
        generate_scenes_from_incidents(incidents)
        assert incidents == original

    def test_generate_scenes_from_simulation_handles_missing_state(self):
        """Ensure graceful handling when simulation state is missing."""
        result = generate_scenes_from_simulation({})
        assert result == []

    def test_backward_compat_existing_simulation_flow(self):
        """Ensure advance_world_simulation still returns all expected keys."""
        payload = {
            "setup_id": "test_compat",
            "title": "Compat",
            "genre": "fantasy",
            "setting": "Test",
            "premise": "Test",
            "factions": [{"faction_id": "f1", "name": "F1", "description": "", "goals": []}],
            "locations": [{"location_id": "l1", "name": "L1", "description": "", "tags": []}],
            "npc_seeds": [
                {"npc_id": "n1", "name": "N1", "role": "x", "description": "", "goals": [],
                 "faction_id": "", "location_id": "", "must_survive": False}
            ],
            "starting_location_id": "l1",
            "starting_npc_ids": ["n1"],
            "metadata": {
                "simulation_state": {
                    "tick": 0,
                    "threads": [{"id": "t1", "name": "T1", "pressure": 0, "involved_factions": ["f1"]}],
                    "incidents": [],
                }
            },
        }
        result = abs.advance_world_simulation(payload)
        # Check all expected keys from the existing contract are present
        expected_keys = {
            "success", "updated_setup", "simulation_state", "simulation_diff",
            "summary", "graph", "simulation", "inspector", "scenes",
        }
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"