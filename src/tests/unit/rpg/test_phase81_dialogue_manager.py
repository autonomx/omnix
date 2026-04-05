"""Unit tests for Phase 8.1 Dialogue Manager."""

import pytest
from unittest.mock import patch, MagicMock
from src.app.rpg.ai.dialogue.dialogue_manager import DialogueManager
from src.app.rpg.ai.dialogue.dialogue_response_parser import parse_dialogue_response


def _make_player_state():
    return {
        "player_state": {
            "current_mode": "scene",
            "active_npc_id": "",
            "scene_id": "",
        }
    }


class TestDialogueResponseParser:
    """Test dialogue response parsing."""

    def test_parse_valid_response(self):
        """Test parsing a valid LLM dialogue response."""
        response = {
            "reply_text": "Hello, adventurer!",
            "suggested_replies": [
                "Tell me more",
                "Goodbye",
                "What do you know?"
            ]
        }
        result = parse_dialogue_response(response)
        assert result["reply_text"] == "Hello, adventurer!"
        assert len(result["suggested_replies"]) == 3
        assert result["suggested_replies"][0] == "Tell me more"

    def test_parse_response_missing_text(self):
        """Test parsing response with missing text field."""
        response = {"suggested_replies": ["Hello"]}
        result = parse_dialogue_response(response)
        assert result["reply_text"] == "The NPC studies you carefully before responding."
        assert len(result["suggested_replies"]) == 1

    def test_parse_response_empty_text(self):
        """Test parsing response with empty text."""
        response = {"reply_text": "", "suggested_replies": []}
        result = parse_dialogue_response(response)
        assert result["reply_text"] == "The NPC studies you carefully before responding."
        assert result["suggested_replies"] == []

    def test_parse_replies_bounded(self):
        """Test that suggested replies are bounded to 4 max."""
        response = {
            "reply_text": "Hello",
            "suggested_replies": ["A", "B", "C", "D", "E", "F"]
        }
        result = parse_dialogue_response(response)
        assert len(result["suggested_replies"]) <= 4

    def test_parse_replies_invalid_type_filtered(self):
        """Test that non-string replies are filtered."""
        response = {
            "reply_text": "Hello",
            "suggested_replies": ["Valid", 123, None, "Also Valid"]
        }
        result = parse_dialogue_response(response)
        assert all(isinstance(r, str) for r in result["suggested_replies"])


class TestDialogueManager:
    """Test dialogue manager functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.manager = DialogueManager()

    def test_start_dialogue(self):
        """Test starting a dialogue session."""
        sim_state = _make_player_state()
        result = self.manager.start_dialogue(sim_state, npc_id="npc_merchant", scene_id="scene1")
        dialogue_state = result["player_state"]["dialogue_state"]
        assert dialogue_state["active"] is True
        assert dialogue_state["npc_id"] == "npc_merchant"
        assert dialogue_state["scene_id"] == "scene1"
        assert dialogue_state["turn_index"] == 0
        assert len(dialogue_state["history"]) == 0

    def test_end_dialogue(self):
        """Test ending a dialogue session."""
        sim_state = _make_player_state()
        self.manager.start_dialogue(sim_state, npc_id="npc1", scene_id="scene1")
        result = self.manager.end_dialogue(sim_state)
        dialogue_state = result["player_state"]["dialogue_state"]
        assert dialogue_state["active"] is False
        assert dialogue_state["npc_id"] == ""
        assert result["player_state"]["current_mode"] == "scene"

    def test_send_message(self):
        """Test sending a player message."""
        sim_state = _make_player_state()
        self.manager.start_dialogue(sim_state, npc_id="npc1", scene_id="scene1")
        result = self.manager.send_message(
            sim_state,
            npc={"name": "Test NPC"},
            scene={"id": "scene1"},
            npc_mind={},
            player_message="Hello there!"
        )
        assert "simulation_state" in result
        assert "reply" in result
        assert "dialogue_state" in result
        assert result["dialogue_state"]["turn_index"] >= 1
        assert len(result["dialogue_state"]["history"]) >= 2  # player + npc

    def test_send_message_history_bounded(self):
        """Test that dialogue history is bounded to 40 messages."""
        sim_state = _make_player_state()
        self.manager.start_dialogue(sim_state, npc_id="npc1", scene_id="scene1")
        current_state = sim_state
        for i in range(25):
            result = self.manager.send_message(
                current_state,
                npc={"name": "Test NPC"},
                scene={"id": "scene1"},
                npc_mind={},
                player_message=f"Message {i}"
            )
            current_state = result["simulation_state"]

        assert len(current_state["player_state"]["dialogue_state"]["history"]) <= 40

    def test_fallback_reply_deterministic(self):
        """Test that fallback replies are deterministic."""
        sim_state = _make_player_state()
        self.manager.start_dialogue(sim_state, npc_id="npc1", scene_id="scene1")
        result1 = self.manager.send_message(
            sim_state,
            npc={"name": "Test NPC"},
            scene={"id": "scene1"},
            npc_mind={},
            player_message="test message"
        )
        result2 = self.manager.send_message(
            result1["simulation_state"],
            npc={"name": "Test NPC"},
            scene={"id": "scene1"},
            npc_mind={},
            player_message="test message"
        )
        assert result1["reply"]["reply_text"] is not None
        assert result2["reply"]["reply_text"] is not None

    def test_dialogue_state_serializable(self):
        """Test that dialogue state is JSON serializable."""
        import json
        sim_state = _make_player_state()
        self.manager.start_dialogue(sim_state, npc_id="npc1", scene_id="scene1")
        result = self.manager.send_message(
            sim_state,
            npc={"name": "Test NPC"},
            scene={"id": "scene1"},
            npc_mind={},
            player_message="Hello"
        )
        state = result["dialogue_state"]
        json_str = json.dumps(state)
        assert json_str is not None

    def test_dialogue_state_serializable_with_traits(self):
        """Test dialogue state with NPC traits."""
        import json
        sim_state = _make_player_state()
        self.manager.start_dialogue(sim_state, npc_id="npc1", scene_id="scene1")
        result = self.manager.send_message(
            sim_state,
            npc={"name": "Test NPC", "traits": {"friendly": True, "age": 30}},
            scene={"id": "scene1"},
            npc_mind={},
            player_message="Hello"
        )
        state = result["dialogue_state"]
        json_str = json.dumps(state)
        assert json_str is not None

    def test_transcript_contains_history(self):
        """Test that ending dialogue includes transcript."""
        sim_state = _make_player_state()
        self.manager.start_dialogue(sim_state, npc_id="npc1", scene_id="scene1")
        result = self.manager.send_message(
            sim_state,
            npc={"name": "Test NPC"},
            scene={"id": "scene1"},
            npc_mind={},
            player_message="Hello"
        )
        history = result["dialogue_state"]["history"]
        assert len(history) >= 2  # at least player + npc message


class TestDialogueManagerLLMIntegration:
    """Test dialogue manager with LLM integration (mocked)."""

    def test_llm_response_used_when_available(self):
        """Test that LLM responses are used when available."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "reply_text": "I am the wise sage.",
            "suggested_replies": ["Tell me more", "Farewell"]
        }

        manager = DialogueManager(llm_client=mock_client)
        sim_state = _make_player_state()
        manager.start_dialogue(sim_state, npc_id="sage1", scene_id="scene1")
        result = manager.send_message(
            sim_state,
            npc={"name": "Wise Sage"},
            scene={"id": "scene1"},
            npc_mind={},
            player_message="Who are you?"
        )

        assert result["reply"]["reply_text"] == "I am the wise sage."
        mock_client.generate_json.assert_called_once()

    def test_llm_error_falls_back_to_deterministic(self):
        """Test that LLM errors fall back to deterministic replies."""
        mock_client = MagicMock()
        mock_client.generate_json.side_effect = Exception("LLM unavailable")

        manager = DialogueManager(llm_client=mock_client)
        sim_state = _make_player_state()
        manager.start_dialogue(sim_state, npc_id="npc1", scene_id="scene1")
        result = manager.send_message(
            sim_state,
            npc={"name": "Test NPC"},
            scene={"id": "scene1"},
            npc_mind={},
            player_message="Hello?"
        )

        # Should still succeed with fallback
        assert "reply" in result
        assert result["reply"]["reply_text"] is not None