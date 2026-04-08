"""Phase 5 — LLM Scene Engine + NPC Behavior: Regression Tests

Ensures that changes to the scene narrator don't break existing behavior:
- API compatibility with existing data formats
- Backward compatibility with older scene formats
- No breaking changes to response structure
- Edge cases with unusual input
"""

import unittest

from app.rpg.ai.world_scene_narrator import (
    NarrativeResult,
    SceneNarrator,
    parse_choices,
    parse_npc_reaction,
    parse_scene_response,
    play_scene,
)


class TestBackwardCompatibility(unittest.TestCase):
    """Regression tests for backward compatibility."""

    def test_legacy_scene_format_without_id(self):
        """Test that scenes without 'id' field work."""
        scene = {
            "title": "Legacy Scene",
            "summary": "An old-style scene.",
            "actors": ["Hero"],
            "stakes": "Everything.",
        }
        state = {"player_name": "Player", "genre": "classic"}
        result = play_scene(scene, state)
        self.assertIn("narrative", result)
        self.assertIsNone(result["metadata"].get("scene_id"))

    def test_legacy_scene_format_minimal(self):
        """Test minimal scene format from early versions."""
        scene = {"title": "Minimal"}
        result = play_scene(scene, {})
        self.assertIn("narrative", result)
        self.assertIn("choices", result)
        self.assertIsInstance(result["choices"], list)

    def test_response_structure_unchanged(self):
        """Test that response structure matches expected format."""
        scene = {
            "id": "reg_001",
            "title": "Structure Test",
            "summary": "Testing response structure.",
            "actors": ["Tester"],
            "stakes": "API stability.",
            "location": "Test Chamber",
            "tension": "high",
        }
        state = {"player_name": "QA", "genre": "testing"}
        result = play_scene(scene, state)

        # Required top-level keys
        required_keys = {"narrative", "choices", "npc_reactions", "dialogue_blocks", "metadata"}
        self.assertTrue(required_keys.issubset(set(result.keys())))

        # Choices structure
        for choice in result["choices"]:
            self.assertIn("id", choice)
            self.assertIn("text", choice)

        # Dialogue blocks structure
        for block in result["dialogue_blocks"]:
            self.assertIn("speaker", block)
            self.assertIn("text", block)
            self.assertIn("emotion", block)

    def test_npc_reactions_structure_unchanged(self):
        """Test that NPC reaction structure is stable."""
        scene = {
            "id": "reg_002",
            "title": "NPC Test",
            "summary": "Testing NPC reaction structure.",
            "actors": ["NPC One", "NPC Two"],
            "stakes": "Stable structure.",
            "location": "NPC Lab",
            "tension": "moderate",
        }
        state = {"player_name": "Tester", "genre": "science"}
        result = play_scene(scene, state)

        for reaction in result["npc_reactions"]:
            self.assertIn("npc_id", reaction)
            self.assertIn("npc_name", reaction)
            self.assertIn("dialogue", reaction)
            self.assertIn("emotion", reaction)
            self.assertIn("intent", reaction)


class TestEdgeCases(unittest.TestCase):
    """Regression tests for edge cases."""

    def test_very_long_scene_title(self):
        """Test scene with very long title."""
        scene = {
            "id": "edge_001",
            "title": "A" * 1000,
            "summary": "Testing long title.",
            "actors": [],
            "stakes": "Performance.",
            "location": "Test",
            "tension": "low",
        }
        result = play_scene(scene, {})
        self.assertIn("A" * 100, result["narrative"])

    def test_actors_as_string_not_list(self):
        """Test when actors is a string instead of list."""
        scene = {
            "id": "edge_002",
            "title": "String Actors",
            "summary": "Testing string actors.",
            "actors": "Single Actor",
            "stakes": "Type safety.",
            "location": "Test",
            "tension": "low",
        }
        result = play_scene(scene, {})
        self.assertIn("narrative", result)

    def test_actors_as_non_string_object(self):
        """Test when actors is something unexpected."""
        scene = {
            "id": "edge_003",
            "title": "Weird Actors",
            "summary": "Testing weird actor type.",
            "actors": 42,
            "stakes": "Type safety.",
            "location": "Test",
            "tension": "low",
        }
        result = play_scene(scene, {})
        self.assertIn("narrative", result)

    def test_missing_summary(self):
        """Test scene without summary."""
        scene = {
            "id": "edge_004",
            "title": "No Summary",
            "actors": [],
            "stakes": "Missing data.",
            "location": "Test",
            "tension": "low",
        }
        result = play_scene(scene, {})
        self.assertIn("narrative", result)

    def test_stakes_as_dict(self):
        """Test when stakes is a dict instead of string."""
        scene = {
            "id": "edge_005",
            "title": "Dict Stakes",
            "summary": "Testing dict stakes.",
            "actors": [],
            "stakes": {"primary": "Survival", "secondary": "Loot"},
            "location": "Test",
            "tension": "low",
        }
        result = play_scene(scene, {})
        self.assertIn("narrative", result)

    def test_empty_scene(self):
        """Test completely empty scene."""
        scene = {}
        result = play_scene(scene, {})
        self.assertIn("narrative", result)
        self.assertGreater(len(result["choices"]), 0)


class TestParseFunctionsStability(unittest.TestCase):
    """Regression tests for parser stability."""

    def test_parse_scene_response_empty(self):
        """Test parse_scene_response with empty input."""
        result = parse_scene_response("")
        self.assertIsNotNone(result["narrative"])
        self.assertEqual(len(result["choices"]), 3)

    def test_parse_scene_response_none_handling(self):
        """Test parse_scene_response handles empty but non-None input."""
        result = parse_scene_response("   ")
        self.assertIsNotNone(result["narrative"])

    def test_parse_npc_reaction_complex_format(self):
        """Test parsing complex NPC reaction format."""
        text = """REACTION: The guard considers the situation with great concern,
looking around the room for other options before settling on a plan.
DIALOGUE: "I suppose we have no choice. Let's do this quickly,
before they realize what we're up to."
EMOTION: tense
INTENT: act
"""
        result = parse_npc_reaction(text, "guard_01", "Captain Guard")
        self.assertIn("concern", result.reaction)
        self.assertEqual(result.emotion, "tense")
        self.assertEqual(result.intent, "act")

    def test_parse_npc_reaction_lowercase_keys(self):
        """Test that lowercase keys are not matched (case sensitivity)."""
        text = """reaction: lowercase
dialogue: "lowercase"
emotion: sad
intent: flee
"""
        result = parse_npc_reaction(text)
        # Should not match lowercase keys
        self.assertEqual(result.emotion, "neutral")
        self.assertEqual(result.dialogue, "")

    def test_parse_choices_with_various_formats(self):
        """Test parsing choices in various number formats."""
        text = """1. First action
2. Second action
3. Third action
4. Fourth action
"""
        result = parse_choices(text)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]["id"], "choice_1")
        self.assertEqual(result[3]["id"], "choice_4")

    def test_parse_choices_mixed_format(self):
        """Test parsing choices with mixed number formats."""
        text = """1) First option
2) Second option
"""
        result = parse_choices(text)
        self.assertEqual(len(result), 2)


class TestSceneNarratorStability(unittest.TestCase):
    """Regression tests for SceneNarrator class stability."""

    def test_repeated_calls_same_result(self):
        """Test that repeated calls with same input produce consistent results."""
        scene = {
            "id": "stability_001",
            "title": "Stability Test",
            "summary": "Testing stability.",
            "actors": ["Stable Actor"],
            "stakes": "Stability.",
            "location": "Test",
            "tension": "low",
        }
        state = {"player_name": "Tester", "genre": "testing"}

        narrator = SceneNarrator(simulate_mode=True)
        result1 = narrator.narrate_scene(scene, state)
        result2 = narrator.narrate_scene(scene, state)

        # Narrative should be identical
        self.assertEqual(result1.narrative, result2.narrative)
        self.assertEqual(len(result1.choices), len(result2.choices))

    def test_simulate_mode_deterministic(self):
        """Test that simulate mode is deterministic for core fields."""
        narrator = SceneNarrator(simulate_mode=True)
        scene = {
            "id": "det_001",
            "title": "Determinism Test",
            "summary": "Testing deterministic behavior.",
            "actors": ["A", "B"],
            "stakes": "Determinism.",
            "location": "Lab",
            "tension": "moderate",
        }
        state = {"player_name": "Tester", "genre": "science"}

        # Metadata should always have required keys
        result = narrator.narrate_scene(scene, state)
        self.assertIn("tone", result.metadata)
        self.assertIn("choice_count", result.metadata)
        self.assertIn("npc_count", result.metadata)

    def test_narrator_default_tone_dramatic(self):
        """Test that default tone is dramatic."""
        narrator = SceneNarrator(simulate_mode=True)
        scene = {
            "id": "tone_001",
            "title": "Tone Test",
            "summary": "Testing default tone.",
            "actors": [],
            "stakes": "The tone.",
            "location": "Lab",
            "tension": "low",
        }
        state = {}
        result = narrator.narrate_scene(scene, state)
        self.assertIn("dramatic", result.narrative)
        self.assertEqual(result.metadata["tone"], "dramatic")

    def test_narrator_with_no_actors_no_reactions(self):
        """Test that no actors result in no NPC reactions."""
        scene = {
            "id": "no_npc_001",
            "title": "No NPCs",
            "summary": "A scene without NPCs.",
            "actors": [],
            "stakes": "None.",
            "location": "Empty",
            "tension": "low",
        }
        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(scene, {}, include_npc_reactions=True)
        self.assertEqual(len(result.npc_reactions), 0)


if __name__ == "__main__":
    unittest.main()