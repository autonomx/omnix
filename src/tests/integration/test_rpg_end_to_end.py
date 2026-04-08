"""End-to-end RPG integration test — creates an adventure and runs dialogue rounds.

This test validates the full RPG flow:
1. Create an adventure via the adventure builder service
2. Start the adventure
3. Run several dialogue rounds with mocked LLM responses
4. Verify state consistency throughout

All LLM calls are mocked to ensure deterministic, fast tests.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'app'))

from rpg.ai.dialogue.dialogue_manager import DialogueManager
from rpg.player import ensure_player_state
from rpg.services.adventure_builder_service import (
    build_template_payload,
    get_templates,
    preview_setup,
    start_adventure,
    validate_setup,
)

# ---------------------------------------------------------------------------
# Mock LLM responses
# ---------------------------------------------------------------------------

MOCK_LLM_DIALOGUE_RESPONSE = {
    "reply_text": "Greetings, traveler. What brings you to these lands?",
    "tone": "friendly",
    "intent": "greet",
    "suggested_replies": [
        "I seek adventure.",
        "Tell me about this place.",
        "Who are you?",
    ],
}

MOCK_LLM_DIALOGUE_RESPONSE_2 = {
    "reply_text": "Ah, a seeker of adventure! You've come to the right place. The kingdom has been in turmoil since the old king vanished.",
    "tone": "intrigued",
    "intent": "inform",
    "suggested_replies": [
        "What happened to the king?",
        "Where should I begin?",
        "Are there any dangers?",
    ],
}

MOCK_LLM_DIALOGUE_RESPONSE_3 = {
    "reply_text": "The king disappeared three months ago. Some say he was assassinated, others claim he fled. The factions are vying for power in his absence.",
    "tone": "serious",
    "intent": "reveal",
    "suggested_replies": [
        "Which factions are involved?",
        "Do you have any theories?",
        "What can I do to help?",
    ],
}


def _create_mock_llm_client():
    """Create a mock LLM client that returns deterministic dialogue responses."""
    client = MagicMock()
    response_sequence = [
        MOCK_LLM_DIALOGUE_RESPONSE,
        MOCK_LLM_DIALOGUE_RESPONSE_2,
        MOCK_LLM_DIALOGUE_RESPONSE_3,
    ]
    call_count = [0]

    def mock_generate_json(prompt: str) -> dict:
        idx = call_count[0] % len(response_sequence)
        call_count[0] += 1
        return response_sequence[idx]

    client.generate_json = MagicMock(side_effect=mock_generate_json)
    return client


# ---------------------------------------------------------------------------
# Test adventure setup data
# ---------------------------------------------------------------------------

def _build_test_adventure_payload() -> dict:
    """Build a minimal but valid adventure setup for testing."""
    return {
        "setup_id": "test_adventure_001",
        "title": "The Vanishing King",
        "genre": "fantasy_adventure",
        "setting": "A medieval kingdom in political turmoil",
        "premise": "The king has vanished and factions vie for power. The player must uncover the truth.",
        "starting_location_id": "loc_tavern",
        "starting_npc_ids": ["npc_innkeeper", "npc_merchant"],
        "locations": [
            {
                "location_id": "loc_tavern",
                "name": "The Rusty Flagon Tavern",
                "description": "A cozy tavern where travelers gather for news and rumors.",
                "tags": ["urban", "safe", "social"],
            },
            {
                "location_id": "loc_castle",
                "name": "The Royal Castle",
                "description": "Once the seat of power, now a place of intrigue.",
                "tags": ["urban", "political", "danger"],
            },
        ],
        "npc_seeds": [
            {
                "npc_id": "npc_innkeeper",
                "name": "Bran the Innkeeper",
                "role": "informant",
                "description": "A friendly innkeeper who knows all the local rumors.",
                "goals": ["keep_tavern_running", "gather_rumors"],
            },
            {
                "npc_id": "npc_merchant",
                "name": "Elara the Merchant",
                "role": "trader",
                "description": "A shrewd merchant looking for rare goods.",
                "goals": ["make_profit", "find_rare_goods"],
            },
        ],
        "factions": [
            {
                "faction_id": "faction_nobles",
                "name": "The Noble Council",
                "description": "A council of nobles seeking to seize control of the throne.",
                "goals": ["seize_throne", "maintain_order"],
                "relationships": {"faction_rebels": "hostile"},
            },
            {
                "faction_id": "faction_rebels",
                "name": "The People's Vanguard",
                "description": "A rebel faction seeking to establish a republic.",
                "goals": ["establish_republic", "overthrow_nobles"],
                "relationships": {"faction_nobles": "hostile"},
            },
        ],
        "pacing": {
            "style": "balanced",
            "danger_level": "medium",
            "mystery_weight": 0.3,
            "combat_weight": 0.2,
            "politics_weight": 0.3,
            "social_weight": 0.2,
        },
    }


# ---------------------------------------------------------------------------
# Tests: Adventure Creation
# ---------------------------------------------------------------------------

class TestAdventureCreation:
    """Test the adventure creation flow end-to-end."""

    def test_list_templates(self):
        """Verify that templates are available."""
        templates = get_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0
        # Check that each template has required fields
        for template in templates:
            assert "name" in template
            assert "label" in template

    def test_build_template_payload(self):
        """Verify that a template can be hydrated into a full payload."""
        result = build_template_payload("fantasy_adventure")
        assert result["success"] is True
        assert "setup" in result
        setup = result["setup"]
        assert "genre" in setup
        assert "setting" in setup

    def test_validate_setup_valid(self):
        """Validate a well-formed setup payload."""
        payload = _build_test_adventure_payload()
        result = validate_setup(payload)
        assert result["success"] is True
        validation = result["validation"]
        # Should have no blocking issues
        assert validation["blocking"] is False

    def test_validate_setup_invalid(self):
        """Validate that missing required fields are caught."""
        result = validate_setup({})
        assert result["success"] is True
        validation = result["validation"]
        assert validation["blocking"] is True
        issue_codes = [issue["code"] for issue in validation["issues"]]
        assert "required" in issue_codes

    def test_preview_setup(self):
        """Preview a setup and verify summary is generated."""
        payload = _build_test_adventure_payload()
        result = preview_setup(payload)
        assert result["success"] is True
        assert result["ok"] is True
        preview = result["preview"]
        assert preview["title"] == "The Vanishing King"
        assert preview["counts"]["locations"] == 2
        assert preview["counts"]["npcs"] == 2
        assert preview["counts"]["factions"] == 2

    def test_start_adventure(self):
        """Start an adventure and verify the session is created."""
        payload = _build_test_adventure_payload()
        result = start_adventure(payload)
        assert result["success"] is True
        assert "session_id" in result
        # Result contains the adventure state directly (locations, factions, etc.)
        assert "locations" in result
        assert "factions" in result
        assert "creator" in result
        # Verify the setup was applied
        assert result["creator"]["setup_id"] == "test_adventure_001"


# ---------------------------------------------------------------------------
# Tests: Dialogue Rounds
# ---------------------------------------------------------------------------

class TestDialogueRounds:
    """Test the dialogue system with mocked LLM."""

    def _create_dialogue_manager(self):
        """Create a DialogueManager with a mocked LLM client."""
        mock_llm = _create_mock_llm_client()
        return DialogueManager(llm_client=mock_llm)

    def _create_test_simulation_state(self):
        """Create a minimal simulation state for dialogue testing."""
        return {
            "player_state": {
                "current_mode": "scene",
                "active_npc_id": "",
                "dialogue_state": {},
                "location": {"id": "loc_tavern", "name": "The Rusty Flagon Tavern"},
            },
            "world_state": {
                "time": 0,
                "locations": ["loc_tavern", "loc_castle"],
            },
        }

    def _create_test_npc(self):
        """Create a test NPC for dialogue."""
        return {
            "npc_id": "npc_innkeeper",
            "name": "Bran the Innkeeper",
            "role": "informant",
            "personality": {"sociability": 0.8, "loyalty": 0.6, "aggression": 0.1},
        }

    def _create_test_scene(self):
        """Create a test scene for dialogue context."""
        return {
            "scene_id": "scene_tavern_intro",
            "location_id": "loc_tavern",
            "description": "The tavern is warm and noisy.",
        }

    def _create_test_npc_mind(self):
        """Create a test NPC mind state."""
        return {
            "beliefs": {"player_is_trustworthy": 0.5},
            "goals": ["keep_tavern_running", "gather_rumors"],
            "emotions": {"mood": "neutral"},
        }

    def test_start_dialogue(self):
        """Test starting a dialogue with an NPC."""
        dm = self._create_dialogue_manager()
        state = self._create_test_simulation_state()

        state = dm.start_dialogue(state, "npc_innkeeper", "scene_tavern_intro")

        dialogue_state = state["player_state"]["dialogue_state"]
        assert dialogue_state["active"] is True
        assert dialogue_state["npc_id"] == "npc_innkeeper"
        assert dialogue_state["scene_id"] == "scene_tavern_intro"
        assert dialogue_state["turn_index"] == 0
        assert state["player_state"]["current_mode"] == "dialogue"

    def test_end_dialogue(self):
        """Test ending a dialogue."""
        dm = self._create_dialogue_manager()
        state = self._create_test_simulation_state()

        state = dm.start_dialogue(state, "npc_innkeeper")
        state = dm.end_dialogue(state)

        dialogue_state = state["player_state"]["dialogue_state"]
        assert dialogue_state["active"] is False
        assert state["player_state"]["current_mode"] == "scene"

    def test_send_message_with_mock_llm(self):
        """Test sending a message and receiving an NPC reply with mocked LLM."""
        dm = self._create_dialogue_manager()
        state = self._create_test_simulation_state()
        state = dm.start_dialogue(state, "npc_innkeeper")

        npc = self._create_test_npc()
        scene = self._create_test_scene()
        npc_mind = self._create_test_npc_mind()

        result = dm.send_message(
            simulation_state=state,
            npc=npc,
            scene=scene,
            npc_mind=npc_mind,
            player_message="Hello, what's happening in the kingdom?",
        )

        assert "reply" in result
        reply = result["reply"]
        assert "reply_text" in reply
        assert "suggested_replies" in reply
        assert len(reply["suggested_replies"]) > 0

        # Verify dialogue state was updated
        dialogue_state = result["dialogue_state"]
        assert dialogue_state["turn_index"] == 1
        assert len(dialogue_state["history"]) == 2  # player message + NPC reply

    def test_multiple_dialogue_rounds(self):
        """Test multiple rounds of dialogue with consistent state."""
        dm = self._create_dialogue_manager()
        state = self._create_test_simulation_state()
        state = dm.start_dialogue(state, "npc_innkeeper")

        npc = self._create_test_npc()
        scene = self._create_test_scene()
        npc_mind = self._create_test_npc_mind()

        player_messages = [
            "Hello, what's happening in the kingdom?",
            "I seek adventure. Tell me more.",
            "What happened to the king?",
        ]

        for i, msg in enumerate(player_messages):
            result = dm.send_message(
                simulation_state=state,
                npc=npc,
                scene=scene,
                npc_mind=npc_mind,
                player_message=msg,
            )

            # Update state for next round
            state = result["simulation_state"]
            dialogue_state = result["dialogue_state"]

            # Verify turn index increments
            assert dialogue_state["turn_index"] == i + 1

            # Verify history grows (2 entries per round: player + NPC)
            expected_history_len = 2 * (i + 1)
            assert len(dialogue_state["history"]) == expected_history_len

            # Verify reply is present
            assert "reply_text" in result["reply"]
            assert len(result["reply"]["reply_text"]) > 0

    def test_dialogue_history_capped(self):
        """Test that dialogue history is capped to prevent memory growth."""
        dm = self._create_dialogue_manager()
        state = self._create_test_simulation_state()
        state = dm.start_dialogue(state, "npc_innkeeper")

        npc = self._create_test_npc()
        scene = self._create_test_scene()
        npc_mind = self._create_test_npc_mind()

        # Send many messages to trigger history capping
        for i in range(30):
            result = dm.send_message(
                simulation_state=state,
                npc=npc,
                scene=scene,
                npc_mind=npc_mind,
                player_message=f"Message number {i}",
            )
            state = result["simulation_state"]

        # History should be capped at 40 entries (20 rounds * 2)
        dialogue_state = state["player_state"]["dialogue_state"]
        assert len(dialogue_state["history"]) <= 40


# ---------------------------------------------------------------------------
# Tests: Full End-to-End Game Flow
# ---------------------------------------------------------------------------

class TestEndToEndGameFlow:
    """Test the complete game flow from adventure creation to dialogue."""

    def test_create_adventure_and_start_dialogue(self):
        """Create an adventure and start a dialogue session."""
        # Step 1: Create adventure
        payload = _build_test_adventure_payload()
        result = start_adventure(payload)
        assert result["success"] is True

        # Step 2: Start dialogue
        from rpg.ai.dialogue.dialogue_manager import DialogueManager
        dm = DialogueManager(llm_client=_create_mock_llm_client())

        # Build simulation state from adventure result
        sim_state = {
            "player_state": {
                "current_mode": "scene",
                "active_npc_id": "",
                "dialogue_state": {},
                "location": {"id": "loc_tavern", "name": "The Rusty Flagon Tavern"},
            },
            "world_state": result.get("state", {}),
        }

        sim_state = dm.start_dialogue(sim_state, "npc_innkeeper")
        assert sim_state["player_state"]["dialogue_state"]["active"] is True

    def test_full_game_session(self):
        """Run a complete game session: create adventure, start, play dialogue rounds."""
        # Phase 1: Adventure Creation
        payload = _build_test_adventure_payload()

        # Validate
        validation_result = validate_setup(payload)
        assert validation_result["validation"]["blocking"] is False

        # Preview
        preview_result = preview_setup(payload)
        assert preview_result["ok"] is True
        assert preview_result["preview"]["title"] == "The Vanishing King"

        # Start
        start_result = start_adventure(payload)
        assert start_result["success"] is True
        session_id = start_result.get("session_id")
        assert session_id is not None

        # Phase 2: Dialogue Rounds
        dm = DialogueManager(llm_client=_create_mock_llm_client())

        sim_state = {
            "player_state": {
                "current_mode": "scene",
                "active_npc_id": "",
                "dialogue_state": {},
                "location": {"id": "loc_tavern", "name": "The Rusty Flagon Tavern"},
            },
            "world_state": start_result.get("state", {}),
        }

        # Start dialogue with first NPC
        sim_state = dm.start_dialogue(sim_state, "npc_innkeeper", "scene_tavern_intro")

        npc = {
            "npc_id": "npc_innkeeper",
            "name": "Bran the Innkeeper",
            "role": "informant",
        }
        scene = {"scene_id": "scene_tavern_intro", "location_id": "loc_tavern"}
        npc_mind = {"beliefs": {}, "goals": [], "emotions": {}}

        # Play 3 rounds of dialogue
        dialogue_rounds = []
        player_messages = [
            "Greetings, traveler. What brings you to these lands?",
            "I seek adventure. Tell me about the kingdom.",
            "What happened to the king?",
        ]

        for msg in player_messages:
            result = dm.send_message(
                simulation_state=sim_state,
                npc=npc,
                scene=scene,
                npc_mind=npc_mind,
                player_message=msg,
            )
            sim_state = result["simulation_state"]
            dialogue_rounds.append({
                "player_message": msg,
                "npc_reply": result["reply"]["reply_text"],
                "suggested_replies": result["reply"].get("suggested_replies", []),
            })

        # Verify all rounds completed
        assert len(dialogue_rounds) == 3
        for round_data in dialogue_rounds:
            assert len(round_data["npc_reply"]) > 0
            assert len(round_data["suggested_replies"]) > 0

        # Verify final state
        dialogue_state = sim_state["player_state"]["dialogue_state"]
        assert dialogue_state["turn_index"] == 3
        assert len(dialogue_state["history"]) == 6  # 3 rounds * 2 messages each

        # Phase 3: End dialogue
        sim_state = dm.end_dialogue(sim_state)
        assert sim_state["player_state"]["dialogue_state"]["active"] is False
        assert sim_state["player_state"]["current_mode"] == "scene"

    def test_state_persistence_across_rounds(self):
        """Verify that state is properly maintained across dialogue rounds."""
        dm = DialogueManager(llm_client=_create_mock_llm_client())

        sim_state = {
            "player_state": {
                "current_mode": "scene",
                "active_npc_id": "",
                "dialogue_state": {},
                "location": {"id": "loc_tavern", "name": "The Rusty Flagon Tavern"},
            },
            "world_state": {"time": 0},
        }

        sim_state = dm.start_dialogue(sim_state, "npc_innkeeper")

        npc = {"npc_id": "npc_innkeeper", "name": "Bran"}
        scene = {"scene_id": "scene_1"}
        npc_mind = {"beliefs": {}, "goals": [], "emotions": {}}

        # Send first message
        result1 = dm.send_message(sim_state, npc, scene, npc_mind, "Hello!")
        sim_state = result1["simulation_state"]

        # Send second message
        result2 = dm.send_message(sim_state, npc, scene, npc_mind, "Tell me more.")
        sim_state = result2["simulation_state"]

        # Verify state accumulated properly
        dialogue_state = sim_state["player_state"]["dialogue_state"]
        assert dialogue_state["turn_index"] == 2
        assert len(dialogue_state["history"]) == 4

        # Verify the history contains both player and NPC messages
        speakers = [entry["speaker"] for entry in dialogue_state["history"]]
        assert speakers.count("player") == 2
        assert speakers.count("npc") == 2


# ---------------------------------------------------------------------------
# Tests: Fallback Behavior (no LLM)
# ---------------------------------------------------------------------------

class TestDialogueFallback:
    """Test dialogue fallback when LLM is unavailable."""

    def test_fallback_without_llm(self):
        """Test that dialogue works even without an LLM client."""
        dm = DialogueManager(llm_client=None)
        state = {
            "player_state": {
                "current_mode": "scene",
                "active_npc_id": "",
                "dialogue_state": {},
            },
        }
        state = dm.start_dialogue(state, "npc_test")

        npc = {"npc_id": "npc_test", "name": "Test NPC"}
        scene = {}
        npc_mind = {}

        result = dm.send_message(state, npc, scene, npc_mind, "Hello, I need help.")

        assert "reply" in result
        assert "reply_text" in result["reply"]
        assert "help" in result["reply"]["reply_text"].lower() or "npc" in result["reply"]["reply_text"].lower()

    def test_fallback_suggested_replies(self):
        """Test that fallback provides suggested replies."""
        dm = DialogueManager(llm_client=None)
        state = {
            "player_state": {
                "current_mode": "scene",
                "active_npc_id": "",
                "dialogue_state": {},
            },
        }
        state = dm.start_dialogue(state, "npc_test")

        npc = {"npc_id": "npc_test", "name": "Test NPC"}
        scene = {}
        npc_mind = {}

        result = dm.send_message(state, npc, scene, npc_mind, "Who are you?")

        assert len(result["reply"]["suggested_replies"]) > 0
        assert isinstance(result["reply"]["suggested_replies"], list)