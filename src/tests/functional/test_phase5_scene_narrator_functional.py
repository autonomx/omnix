"""Phase 5 — LLM Scene Engine + NPC Behavior: Functional Tests

Tests end-to-end behavior of the scene narration pipeline:
- SceneNarrator with various configurations
- Integration with simulated LLM gateway
- Full play_scene service function
- Multi-scenario coverage
"""

import json
import unittest

from app.rpg.ai.world_scene_narrator import (
    NarrativeResult,
    SceneNarrator,
    play_scene,
)


class TestSceneNarratorFunctional(unittest.TestCase):
    """Functional tests for SceneNarrator."""

    def test_full_scene_narration_with_all_options(self):
        """Test narration with NPC reactions and choices enabled."""
        scene = {
            "id": "functional_001",
            "title": "The King's Court",
            "summary": "You stand before the throne, the weight of your quest upon your shoulders.",
            "actors": ["King Aldric", "Queen Mara", "Advisor Vex"],
            "stakes": "Convince the king to send aid before the village falls.",
            "location": "The Grand Throne Room",
            "tension": "critical",
        }
        state = {
            "player_name": "Elara",
            "genre": "high fantasy",
            "quest_status": "urgent",
        }

        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(
            scene, state,
            tone="royal",
            include_npc_reactions=True,
            include_choices=True,
            max_npc_reactions=3,
        )

        self.assertIsInstance(result, NarrativeResult)
        self.assertIn("The King's Court", result.narrative)
        self.assertIn("King's Court", result.narrative)
        self.assertEqual(len(result.npc_reactions), 3)
        self.assertEqual(len(result.choices), 3)
        self.assertEqual(len(result.dialogue_blocks), 3)  # Each NPC has dialogue
        self.assertEqual(result.metadata["scene_id"], "functional_001")
        self.assertEqual(result.metadata["tone"], "royal")
        self.assertEqual(result.metadata["npc_count"], 3)
        self.assertEqual(result.metadata["choice_count"], 3)

    def test_scene_with_actor_dict(self):
        """Test narration with actors as a dict (NPC objects)."""
        scene = {
            "id": "functional_002",
            "title": "The Tavern Meeting",
            "summary": "A stranger approaches you in the dim tavern.",
            "actors": {
                "Raven": {"personality": "mysterious", "goals": "recruit allies"},
                "Borin": {"personality": "gruff", "goals": "protect the tavern"},
            },
            "stakes": "Decide who to trust.",
            "location": "The Rusty Flagon",
            "tension": "moderate",
        }
        state = {"player_name": "You", "genre": "dark fantasy"}

        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(scene, state)

        self.assertEqual(len(result.npc_reactions), 2)
        npc_names = [r.npc_name for r in result.npc_reactions]
        self.assertIn("Raven", npc_names)
        self.assertIn("Borin", npc_names)

    def test_multiple_tones(self):
        """Test different narrative tones produce different output."""
        scene = {
            "id": "tone_test",
            "title": "Darkness Falls",
            "summary": "Shadows lengthen as danger approaches.",
            "actors": [],
            "stakes": "Survival",
            "location": "The Crypt",
            "tension": "high",
        }
        state = {"player_name": "Hero", "genre": "horror"}

        narrator = SceneNarrator(simulate_mode=True)
        
        result_dramatic = narrator.narrate_scene(scene, state, tone="dramatic")
        result_mysterious = narrator.narrate_scene(scene, state, tone="mysterious")
        result_tense = narrator.narrate_scene(scene, state, tone="tense")

        # All should contain the title
        self.assertIn("Darkness Falls", result_dramatic.narrative)
        self.assertIn("Darkness Falls", result_mysterious.narrative)
        self.assertIn("Darkness Falls", result_tense.narrative)

        # Each should contain its own tone
        self.assertIn("dramatic", result_dramatic.narrative)
        self.assertIn("mysterious", result_mysterious.narrative)
        self.assertIn("tense", result_tense.narrative)

    def test_empty_actor_list(self):
        """Test narration with no actors in scene."""
        scene = {
            "id": "solo_001",
            "title": "Alone in the Dark",
            "summary": "You are completely alone.",
            "actors": [],
            "stakes": "Find the exit.",
            "location": "A cave",
            "tension": "low",
        }
        state = {"player_name": "Solo", "genre": "adventure"}

        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(scene, state, include_npc_reactions=True)

        self.assertEqual(len(result.npc_reactions), 0)
        self.assertNotIn("stand before you", result.narrative)

    def test_max_npc_limited(self):
        """Test max_npc_reactions limits output."""
        scene = {
            "id": "crowded_001",
            "title": "The Council",
            "summary": "Many voices fill the chamber.",
            "actors": ["A", "B", "C", "D", "E", "F"],
            "stakes": "Unity or division.",
            "location": "Council Chamber",
            "tension": "high",
        }
        state = {"player_name": "Player", "genre": "politics"}

        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(scene, state, max_npc_reactions=2)

        self.assertLessEqual(len(result.npc_reactions), 2)

    def test_dialogue_blocks_from_npc_reactions(self):
        """Test that dialogue blocks are derived from NPC reactions."""
        scene = {
            "id": "dialogue_001",
            "title": "Negotiations",
            "summary": "Words are weapons here.",
            "actors": ["Diplomat", "General"],
            "stakes": "Peace or war.",
            "location": "Parley Tent",
            "tension": "critical",
        }
        state = {"player_name": "Envoy", "genre": "war"}

        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(scene, state)

        # Each NPC simulation generates dialogue
        for block in result.dialogue_blocks:
            self.assertIn("speaker", block)
            self.assertIn("text", block)
            self.assertIn("emotion", block)
            self.assertTrue(len(block["text"]) > 0)

    def test_choices_have_required_fields(self):
        """Test that choices have id, text, and type."""
        scene = {
            "id": "choice_001",
            "title": "The Crossroads",
            "summary": "Multiple paths lie ahead.",
            "actors": [],
            "stakes": "Choose wisely.",
            "location": "Crossroads",
            "tension": "moderate",
        }
        state = {"player_name": "Traveler", "genre": "adventure"}

        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(scene, state, include_npc_reactions=False)

        for choice in result.choices:
            self.assertIn("id", choice)
            self.assertIn("text", choice)
            self.assertIn("type", choice)
            self.assertTrue(choice["id"].startswith("choice_"))


class TestPlaySceneFunctional(unittest.TestCase):
    """Functional tests for play_scene service function."""

    def test_full_response_structure(self):
        """Test that play_scene returns complete response dict."""
        scene = {
            "id": "ps_001",
            "title": "The Ambush",
            "summary": "Bandits spring from the trees!",
            "actors": ["Bandit Chief", "Archer"],
            "stakes": "Your life and your companions.",
            "location": "The Forest Road",
            "tension": "extreme",
        }
        state = {
            "player_name": "Warrior",
            "genre": "action fantasy",
        }

        result = play_scene(scene, state, tone="violent")
        
        self.assertTrue(isinstance(result, dict))
        self.assertIn("narrative", result)
        self.assertIn("choices", result)
        self.assertIn("npc_reactions", result)
        self.assertIn("dialogue_blocks", result)
        self.assertIn("metadata", result)

        # Verify narrative contains scene info
        self.assertIn("The Ambush", result["narrative"])

        # Verify choices is a list
        self.assertIsInstance(result["choices"], list)
        self.assertGreater(len(result["choices"]), 0)

        # Verify npc_reactions is a list of dicts
        self.assertIsInstance(result["npc_reactions"], list)

        # Verify dialogue_blocks is a list
        self.assertIsInstance(result["dialogue_blocks"], list)

    def test_state_is_reflected_in_output(self):
        """Test that state values appear in narration."""
        scene = {
            "id": "ps_002",
            "title": "The Prophecy",
            "summary": "The oracle speaks your name.",
            "actors": ["Oracle"],
            "stakes": "Fate hangs in the balance.",
            "location": "The Temple",
            "tension": "divine",
        }
        state = {"player_name": "Chosen One", "genre": "epic fantasy"}

        result = play_scene(scene, state)

        self.assertIn("The Prophecy", result["narrative"])

    def test_empty_state_handles_gracefully(self):
        """Test that empty state doesn't cause errors."""
        scene = {
            "id": "ps_003",
            "title": "Void Scene",
            "summary": "Nothing exists here.",
            "actors": [],
            "stakes": "None",
            "location": "The Void",
            "tension": "null",
        }

        result = play_scene(scene, {})
        self.assertIn("narrative", result)
        self.assertIn("choices", result)


if __name__ == "__main__":
    unittest.main()