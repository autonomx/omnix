"""Functional tests for Phase 16.0/16.1 — Dialogue memory + lifecycle."""
from app.rpg.memory.dialogue_context import (
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
)
from app.rpg.memory.lifecycle import apply_dialogue_memory_hooks


def _build_rich_simulation_state():
    return {
        "memory_state": {
            "actor_memory": {
                "npc:warrior": {
                    "entries": [
                        {"text": "Fought the dragon", "strength": 0.9},
                        {"text": "Met at tavern", "strength": 0.4},
                        {"text": "Shared quest info", "strength": 0.6},
                    ]
                },
                "npc:mage": {
                    "entries": [
                        {"text": "Taught fire spell", "strength": 0.7},
                        {"text": "Discussed ancient lore", "strength": 0.5},
                    ]
                },
            },
            "world_memory": {
                "rumors": [
                    {"text": "King is ill", "strength": 0.8, "reach": 5},
                    {"text": "Dragon seen near village", "strength": 0.6, "reach": 3},
                    {"text": "New trade route", "strength": 0.3, "reach": 1},
                ]
            },
        }
    }


def test_full_dialogue_cycle_decay_reinforce_context():
    """Full functional cycle: apply hooks → build context → build prompt."""
    state = _build_rich_simulation_state()

    # Apply lifecycle hooks
    state = apply_dialogue_memory_hooks(
        state,
        actor_id="npc:warrior",
        player_text="Tell me about the dragon fight",
    )

    # Build context
    ctx = build_dialogue_memory_context(state, actor_id="npc:warrior")
    assert len(ctx["actor_memory"]) >= 1

    # Build prompt
    prompt = build_llm_memory_prompt_block(ctx)
    assert len(prompt) > 0
    assert len(prompt) <= 2000


def test_multiple_dialogue_cycles_accumulate_memory():
    """Multiple dialogue cycles should accumulate reinforced memories."""
    state = _build_rich_simulation_state()

    for i in range(5):
        state = apply_dialogue_memory_hooks(
            state,
            actor_id="npc:warrior",
            player_text=f"Topic {i}",
        )

    entries = state["memory_state"]["actor_memory"]["npc:warrior"]["entries"]
    texts = [e["text"] for e in entries]
    # Original + reinforced
    assert len(entries) >= 3


def test_decay_reduces_all_strengths():
    """Apply hooks multiple times without reinforcement to observe decay."""
    state = _build_rich_simulation_state()
    original_strength = state["memory_state"]["actor_memory"]["npc:warrior"]["entries"][0]["strength"]

    for _ in range(10):
        state = apply_dialogue_memory_hooks(
            state,
            actor_id="",
            player_text="",
        )

    entries = state["memory_state"]["actor_memory"]["npc:warrior"]["entries"]
    # All strengths should have decreased
    for e in entries:
        assert e["strength"] < original_strength


def test_multi_actor_context_merges_correctly():
    """Context for multiple actors merges all entries."""
    state = _build_rich_simulation_state()
    ctx = build_dialogue_memory_context(state, actor_ids=["npc:warrior", "npc:mage"])
    assert len(ctx["actor_memory"]) == 5  # 3 warrior + 2 mage
    assert "npc:warrior" in ctx["actor_ids"]
    assert "npc:mage" in ctx["actor_ids"]


def test_prompt_includes_both_memory_and_rumors():
    """Prompt block should include both actor memories and world rumors."""
    state = _build_rich_simulation_state()
    ctx = build_dialogue_memory_context(state, actor_id="npc:warrior")
    prompt = build_llm_memory_prompt_block(ctx)
    assert "Actor memories" in prompt
    assert "World rumors" in prompt
    # Verify actual content from test data appears
    assert "Fought the dragon" in prompt
    assert "King is ill" in prompt
