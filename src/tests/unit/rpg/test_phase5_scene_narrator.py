"""Phase 5 — LLM Scene Engine + NPC Behavior: Unit Tests

Tests for:
- build_scene_prompt
- build_npc_reaction_prompt
- build_choice_prompt
- parse_scene_response
- parse_npc_reaction
- parse_choices
- SceneNarrator class
- play_scene service function
"""

import unittest
from unittest.mock import MagicMock, patch

from app.rpg.ai.world_scene_narrator import (
    SceneNarrator,
    NPCReaction,
    NarrativeResult,
    build_scene_prompt,
    build_npc_reaction_prompt,
    build_choice_prompt,
    parse_scene_response,
    parse_npc_reaction,
    parse_choices,
    play_scene,
)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SAMPLE_SCENE = {
    "id": "scene_001",
    "title": "The Dark Forest",
    "summary": "You enter a dense, mist-shrouded forest.",
    "actors": ["Guard", "Merchant"],
    "stakes": "Finding the hidden path before nightfall.",
    "location": "The Whispering Woods",
    "tension": "high",
}

SAMPLE_STATE = {
    "player_name": "Aldric",
    "genre": "dark fantasy",
}


class TestBuildScenePrompt(unittest.TestCase):
    """Tests for build_scene_prompt."""

    def test_returns_string_with_scene_info(self):
        prompt = build_scene_prompt(SAMPLE_SCENE, SAMPLE_STATE)
        self.assertIn("The Dark Forest", prompt)
        self.assertIn("mist-shrouded", prompt)
        self.assertIn("Whispering Woods", prompt)
        self.assertIn("Guard", prompt)
        self.assertIn("Aldric", prompt)
        self.assertIn("dark fantasy", prompt)

    def test_default_tone_is_dramatic(self):
        prompt = build_scene_prompt(SAMPLE_SCENE, SAMPLE_STATE)
        self.assertIn("Tone: dramatic", prompt)

    def test_custom_tone(self):
        prompt = build_scene_prompt(SAMPLE_SCENE, SAMPLE_STATE, tone="mysterious")
        self.assertIn("Tone: mysterious", prompt)

    def test_custom_max_paragraphs(self):
        prompt = build_scene_prompt(SAMPLE_SCENE, SAMPLE_STATE, max_paragraphs=5)
        self.assertIn("5 paragraphs", prompt)

    def test_missing_fields_get_defaults(self):
        minimal_scene = {}
        prompt = build_scene_prompt(minimal_scene, {})
        self.assertIn("Untitled Scene", prompt)
        self.assertIn("Unknown", prompt)
        self.assertIn("fantasy", prompt)

    def test_actors_as_dict(self):
        scene = {"title": "Test", "summary": "", "actors": {"Guard": "armed", "Mage": "wise"}}
        prompt = build_scene_prompt(scene, {})
        self.assertIn("Guard: armed", prompt)
        self.assertIn("Mage: wise", prompt)


class TestBuildNpcReactionPrompt(unittest.TestCase):
    """Tests for build_npc_reaction_prompt."""

    def test_returns_string_with_npc_info(self):
        npc = {"name": "Theron", "personality": "cautious", "goals": "protect the village"}
        prompt = build_npc_reaction_prompt(npc, SAMPLE_SCENE, "Narrative text")
        self.assertIn("Theron", prompt)
        self.assertIn("cautious", prompt)
        self.assertIn("protect the village", prompt)

    def test_truncates_long_narrative(self):
        long_narrative = "x" * 2000
        prompt = build_npc_reaction_prompt({}, SAMPLE_SCENE, long_narrative)
        # Narrative in prompt should be truncated to 1000 chars
        self.assertIn("x" * 100, prompt)
        self.assertNotIn("x" * 1500, prompt)

    def test_missing_npc_fields(self):
        npc = {}
        prompt = build_npc_reaction_prompt(npc, {}, "")
        self.assertIn("Unknown NPC", prompt)


class TestBuildChoicePrompt(unittest.TestCase):
    """Tests for build_choice_prompt."""

    def test_returns_string_with_scene_info(self):
        prompt = build_choice_prompt(SAMPLE_SCENE, "Some narrative")
        self.assertIn("The Dark Forest", prompt)
        self.assertIn("hidden path", prompt)

    def test_custom_num_choices(self):
        prompt = build_choice_prompt(SAMPLE_SCENE, "narrative", num_choices=5)
        self.assertIn("5 meaningful choices", prompt)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParseSceneResponse(unittest.TestCase):
    """Tests for parse_scene_response."""

    def test_returns_narrative_and_choices(self):
        result = parse_scene_response("The forest grows dark.")
        self.assertEqual(result["narrative"], "The forest grows dark.")
        self.assertEqual(len(result["choices"]), 3)

    def test_empty_text_fallback(self):
        result = parse_scene_response("")
        self.assertIn("unfolds", result["narrative"])

    def test_strips_whitespace(self):
        result = parse_scene_response("  Hello  ")
        self.assertEqual(result["narrative"], "Hello")


class TestParseNpcReaction(unittest.TestCase):
    """Tests for parse_npc_reaction."""

    def test_parses_all_fields(self):
        text = """REACTION: The guard looks worried.
DIALOGUE: "We need to move fast."
EMOTION: tense
INTENT: act
"""
        result = parse_npc_reaction(text, "npc_1", "Guard")
        self.assertEqual(result.npc_id, "npc_1")
        self.assertEqual(result.npc_name, "Guard")
        self.assertIn("worried", result.reaction)
        self.assertEqual(result.dialogue, "We need to move fast.")
        self.assertEqual(result.emotion, "tense")
        self.assertEqual(result.intent, "act")

    def test_defaults_for_missing_fields(self):
        text = "Nothing formatted here."
        result = parse_npc_reaction(text)
        self.assertEqual(result.emotion, "neutral")
        self.assertEqual(result.intent, "")
        self.assertEqual(result.reaction, "")
        self.assertEqual(result.dialogue, "")

    def test_strips_quotes_from_dialogue(self):
        text = 'DIALOGUE: "Hello world"'
        result = parse_npc_reaction(text)
        self.assertEqual(result.dialogue, "Hello world")


class TestParseChoices(unittest.TestCase):
    """Tests for parse_choices."""

    def test_parses_numbered_choices(self):
        text = """1. Attack the enemy
2. Run away
3. Talk things over
"""
        result = parse_choices(text)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["text"], "Attack the enemy")
        self.assertEqual(result[1]["type"], "dialogue")

    def test_fallback_for_invalid(self):
        text = "No valid choices here."
        result = parse_choices(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "Take action")

    def test_uses_parenthesis_format(self):
        text = """1) Fight
2) Flee
"""
        result = parse_choices(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "Fight")


# ---------------------------------------------------------------------------
# SceneNarrator tests
# ---------------------------------------------------------------------------

class TestSceneNarrator(unittest.TestCase):
    """Tests for SceneNarrator class."""

    def test_simulate_mode_returns_simulated(self):
        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(SAMPLE_SCENE, SAMPLE_STATE)
        self.assertIn("The Dark Forest", result.narrative)
        self.assertIsInstance(result.choices, list)
        self.assertIsInstance(result.npc_reactions, list)

    def test_no_llm_gateway_falls_back_to_simulation(self):
        narrator = SceneNarrator()
        result = narrator.narrate_scene(SAMPLE_SCENE, SAMPLE_STATE)
        self.assertIn("The Dark Forest", result.narrative)
        self.assertEqual(len(result.choices), 3)

    def test_include_npc_reactions_false(self):
        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(SAMPLE_SCENE, SAMPLE_STATE, include_npc_reactions=False)
        self.assertEqual(len(result.npc_reactions), 0)
        self.assertEqual(len(result.dialogue_blocks), 0)

    def test_include_choices_false(self):
        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(SAMPLE_SCENE, SAMPLE_STATE, include_choices=False)
        self.assertEqual(len(result.choices), 0)

    def test_tone_override(self):
        narrator = SceneNarrator(simulate_mode=True, default_tone="calm")
        result = narrator.narrate_scene(SAMPLE_SCENE, SAMPLE_STATE, tone="tense")
        self.assertIn("tense", result.narrative)

    def test_metadata_includes_counts(self):
        narrator = SceneNarrator(simulate_mode=True)
        result = narrator.narrate_scene(SAMPLE_SCENE, SAMPLE_STATE)
        self.assertEqual(result.metadata["tone"], "dramatic")
        self.assertEqual(result.metadata["choice_count"], 3)

    def test_llm_gateway_called_when_available(self):
        mock_gateway = MagicMock()
        mock_gateway.call.return_value = "LLM narrative response"
        narrator = SceneNarrator(llm_gateway=mock_gateway)
        result = narrator.narrate_scene(
            {"title": "Test", "summary": "Summary", "actors": [], "stakes": "Stakes"},
            SAMPLE_STATE,
            include_npc_reactions=False,
            include_choices=False,
        )
        mock_gateway.call.assert_called()
        self.assertEqual(result.narrative, "LLM narrative response")

    def test_llm_gateway_failure_falls_back(self):
        mock_gateway = MagicMock()
        mock_gateway.call.side_effect = RuntimeError("LLM error")
        narrator = SceneNarrator(llm_gateway=mock_gateway)
        result = narrator.narrate_scene(
            {"title": "Test", "summary": "Summary", "actors": [], "stakes": "Stakes"},
            SAMPLE_STATE,
            include_npc_reactions=False,
            include_choices=False,
        )
        self.assertIn("Test", result.narrative)


# ---------------------------------------------------------------------------
# play_scene service function tests
# ---------------------------------------------------------------------------

class TestPlayScene(unittest.TestCase):
    """Tests for play_scene service function."""

    def test_returns_dict_with_narrative(self):
        result = play_scene(SAMPLE_SCENE, SAMPLE_STATE)
        self.assertIn("narrative", result)
        self.assertIn("choices", result)
        self.assertIn("npc_reactions", result)
        self.assertIn("dialogue_blocks", result)
        self.assertIn("metadata", result)

    def test_custom_tone(self):
        result = play_scene(SAMPLE_SCENE, SAMPLE_STATE, tone="mysterious")
        self.assertIn("The Dark Forest", result["narrative"])

    def test_with_llm_gateway(self):
        mock_gateway = MagicMock()
        mock_gateway.call.return_value = "LLM response"
        result = play_scene(
            {"title": "Test", "summary": "Summary", "actors": [], "stakes": "Stakes"},
            SAMPLE_STATE,
            llm_gateway=mock_gateway,
        )
        mock_gateway.call.assert_called()


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestDataclasses(unittest.TestCase):
    """Tests for dataclass models."""

    def test_npc_reaction_defaults(self):
        r = NPCReaction(npc_id="1", npc_name="Test")
        self.assertEqual(r.dialogue, "")
        self.assertEqual(r.emotion, "neutral")
        self.assertEqual(r.intent, "")

    def test_narrative_result_defaults(self):
        r = NarrativeResult(narrative="Hello")
        self.assertEqual(r.narrative, "Hello")
        self.assertEqual(r.choices, [])
        self.assertEqual(r.npc_reactions, [])
        self.assertEqual(r.dialogue_blocks, [])
        self.assertEqual(r.metadata, {})


if __name__ == "__main__":
    unittest.main()