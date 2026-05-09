from tests.rpg.autoplay.player_agent_cache import PlayerAgentDecisionCache
from tests.rpg.autoplay.player_agent_optimization import (
    build_player_agent_context_packet,
    build_player_agent_messages,
    normalize_player_agent_payload,
    player_agent_cache_key,
)


def test_player_agent_context_packet_excludes_large_debug_blobs():
    session = {
        "simulation_state": {
            "scene": {"title": "Tavern", "description": "Warm and crowded."},
            "present_npcs": ["bran"],
            "npcs": {
                "bran": {
                    "name": "Bran",
                    "role": "innkeeper",
                    "huge_debug_blob": "x" * 10000,
                }
            },
            "debug_raw": "x" * 10000,
        }
    }
    packet = build_player_agent_context_packet(
        session=session,
        transcript_tail=[],
        latest_context={"objective": "Find a lead."},
        strategy="balanced_story_player",
        action_diversity_window=8,
    )
    text = str(packet)
    assert packet["scene"]["title"] == "Tavern"
    assert packet["present_npcs"][0]["name"] == "Bran"
    assert "huge_debug_blob" not in text
    assert "debug_raw" not in text


def test_player_agent_messages_are_action_only_and_budgeted():
    packet = {
        "scene": {"title": "Tavern"},
        "recent_turns": [],
        "objectives": {"active_objective": "Talk to Bran."},
    }
    messages, metrics = build_player_agent_messages(context_packet=packet, max_context_chars=1000)
    joined = "\n".join(message["content"] for message in messages)
    assert '"action"' in joined
    assert "Do not narrate" in joined
    assert metrics["total_chars"] > 0


def test_normalize_player_agent_payload_accepts_action_aliases():
    result = normalize_player_agent_payload(
        {
            "next_action": "I ask Bran about the mill.",
            "intent": "ask",
            "target": "Bran",
        }
    )
    assert result["ok"] is True
    assert result["action"] == "I ask Bran about the mill."


def test_player_agent_cache_only_stores_llm_successes():
    cache = PlayerAgentDecisionCache()
    cache.put("a", {"source": "fallback_scripted", "ok": True, "action": "I wait."})
    assert cache.summary()["rejected_stores"] == 1
    assert cache.get("a") is None

    cache.put("b", {"source": "llm_player_agent", "ok": True, "action": "I ask Bran."})
    assert cache.get("b")["action"] == "I ask Bran."
    assert cache.summary()["hits"] == 1


def test_player_agent_cache_key_stable_for_same_context():
    packet = {"scene": {"title": "Tavern"}, "objective": "Ask Bran"}
    assert (
        player_agent_cache_key(context_packet=packet, strategy="balanced")
        == player_agent_cache_key(context_packet=packet, strategy="balanced")
    )


def test_compact_player_agent_context_includes_goal_pressure_and_suggestions():
    packet = build_player_agent_context_packet(
        session={"current_location": "Rusty Flagon Tavern"},
        transcript_tail=[],
        latest_context={
            "suggested_actions": [
                {"command": "I follow the witness lead.", "category": "travel", "priority": 90}
            ],
            "goal_pressure": {"active": True, "directives": ["Advance the quest."]},
            "strategy_guidance": {"anti_stall_active": True},
            "active_objectives": [{"objective_text": "Find the witness"}],
        },
        strategy="goal_directed_quest_runner",
        action_diversity_window=12,
    )

    assert packet["goal_pressure"]["active"] is True
    assert packet["suggested_actions"][0]["command"] == "I follow the witness lead."
    assert packet["objectives"]["active_objectives"][0]["objective_text"] == "Find the witness"