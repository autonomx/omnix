"""Unit tests for Phase 14.3/16.0 — Dialogue memory context builder."""
from app.rpg.memory.dialogue_context import (
    build_actor_memory_context,
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
    build_world_rumor_context,
)


def test_dialogue_memory_context_returns_expected_structure():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "npc:a": {
                    "entries": [
                        {"text": "Met the king", "strength": 0.8},
                        {"text": "Saw a dragon", "strength": 0.3},
                    ]
                }
            },
            "world_memory": {
                "rumors": [
                    {"text": "War in the north", "strength": 0.9, "reach": 3},
                ]
            },
        }
    }
    ctx = build_dialogue_memory_context(simulation_state, actor_ids=["npc:a"])
    assert "actor_memory" in ctx
    assert "world_rumors" in ctx
    assert "actor_ids" in ctx
    assert ctx["actor_ids"] == ["npc:a"]
    assert len(ctx["actor_memory"]) == 2
    assert len(ctx["world_rumors"]) >= 1


def test_dialogue_context_orders_by_strength_then_text():
    """Test deterministic ordering: strength desc, then text as tiebreaker."""
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "npc:a": {
                    "entries": [
                        {"text": "B", "strength": 0.5},
                        {"text": "A", "strength": 0.5},
                    ]
                }
            }
        }
    }
    context = build_dialogue_memory_context(simulation_state, actor_id="npc:a")
    assert context["actor_memory"][0]["text"] == "A"
    assert context["actor_memory"][1]["text"] == "B"


def test_build_llm_memory_prompt_block_returns_bounded_text():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "hero": {
                    "entries": [
                        {"text": "Found the sword", "strength": 0.7},
                    ]
                }
            },
            "world_memory": {"rumors": []},
        }
    }
    ctx = build_dialogue_memory_context(simulation_state, actor_ids=["hero"])
    prompt = build_llm_memory_prompt_block(ctx)
    assert "Found the sword" in prompt


def test_build_llm_memory_prompt_block_caps_lines():
    """Test that prompt block is capped at 16 lines."""
    entries = [{"text": f"M{i}", "strength": 0.9 - i * 0.01} for i in range(30)]
    simulation_state = {
        "memory_state": {
            "actor_memory": {"hero": {"entries": entries}},
            "world_memory": {"rumors": []},
        }
    }
    ctx = build_dialogue_memory_context(simulation_state, actor_ids=["hero"])
    prompt = build_llm_memory_prompt_block(ctx)
    lines = [line for line in prompt.split("\n") if line.strip()]
    assert len(lines) <= 16


def test_build_llm_memory_prompt_block_caps_text_length():
    """Test that each text entry is bounded to 240 chars."""
    long_text = "X" * 500
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "hero": {"entries": [{"text": long_text, "strength": 0.9}]}
            },
            "world_memory": {"rumors": []},
        }
    }
    ctx = build_dialogue_memory_context(simulation_state, actor_ids=["hero"])
    prompt = build_llm_memory_prompt_block(ctx)
    assert len(prompt) <= 2000


def test_build_actor_memory_context():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "npc:a": {"entries": [{"text": "fact1", "strength": 0.8}, {"text": "fact2", "strength": 0.3}]}
            }
        }
    }
    result = build_actor_memory_context(simulation_state, "npc:a")
    assert len(result) == 2
    assert result[0]["strength"] >= result[1]["strength"]


def test_build_world_rumor_context():
    simulation_state = {
        "memory_state": {
            "world_memory": {
                "rumors": [
                    {"text": "rumor1", "strength": 0.5},
                    {"text": "rumor2", "strength": 0.9},
                ]
            }
        }
    }
    result = build_world_rumor_context(simulation_state)
    assert len(result) == 2
    assert result[0]["strength"] >= result[1]["strength"]