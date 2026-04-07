"""Regression tests for Phase 16.0/16.1 — Dialogue memory + lifecycle."""
from app.rpg.memory.dialogue_context import (
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
)
from app.rpg.memory.lifecycle import apply_dialogue_memory_hooks


def test_regression_empty_simulation_state_no_crash():
    """Empty or None simulation state should not crash."""
    ctx = build_dialogue_memory_context({}, actor_id="npc:a")
    assert ctx["actor_memory"] == []
    assert ctx["world_rumors"] == []

    ctx2 = build_dialogue_memory_context(None, actor_id="npc:a")
    assert ctx2["actor_memory"] == []


def test_regression_none_actor_id_handled():
    """None/empty actor_id should not crash."""
    state = {
        "memory_state": {
            "actor_memory": {},
            "world_memory": {"rumors": []},
        }
    }
    ctx = build_dialogue_memory_context(state, actor_id=None)
    assert ctx["actor_memory"] == []


def test_regression_prompt_block_handles_none_context():
    """Prompt block should handle None context gracefully."""
    prompt = build_llm_memory_prompt_block(None)
    assert "none" in prompt.lower() or "MEMORY CONTEXT" in prompt


def test_regression_lifecycle_no_actor_no_text_no_crash():
    """Lifecycle hooks with no actor/text should not crash."""
    state = {
        "memory_state": {
            "actor_memory": {},
            "world_memory": {"rumors": []},
        }
    }
    out = apply_dialogue_memory_hooks(state, actor_id="", player_text="")
    assert "memory_state" in out


def test_regression_lifecycle_preserves_other_state():
    """Lifecycle hooks should not strip non-memory state."""
    state = {
        "memory_state": {
            "actor_memory": {},
            "world_memory": {"rumors": []},
        },
        "custom_field": "preserved",
    }
    out = apply_dialogue_memory_hooks(state, actor_id="npc:a", player_text="test")
    assert out["custom_field"] == "preserved"


def test_regression_backward_compat_actor_ids_positional():
    """build_dialogue_memory_context should accept actor_ids as keyword."""
    state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": [{"text": "fact", "strength": 0.5}]}},
            "world_memory": {"rumors": []},
        }
    }
    ctx = build_dialogue_memory_context(state, actor_ids=["npc:a"])
    assert len(ctx["actor_memory"]) == 1


def test_regression_prompt_bounded_with_many_entries():
    """Prompt should be bounded even with many memory entries."""
    entries = [{"text": f"memory entry number {i} with some content", "strength": 0.9 - i * 0.01} for i in range(100)]
    state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": entries}},
            "world_memory": {"rumors": [{"text": f"rumor {i}", "strength": 0.5} for i in range(50)]},
        }
    }
    ctx = build_dialogue_memory_context(state, actor_id="npc:a")
    prompt = build_llm_memory_prompt_block(ctx)
    assert len(prompt) <= 2000
    lines = prompt.split("\n")
    assert len(lines) <= 16


def test_regression_decay_does_not_make_strength_negative():
    """Decay should clamp to 0, never go negative."""
    state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": [{"text": "weak", "strength": 0.01}]}},
            "world_memory": {"rumors": []},
        }
    }
    for _ in range(20):
        state = apply_dialogue_memory_hooks(state, actor_id="", player_text="")

    entries = state["memory_state"]["actor_memory"]["npc:a"]["entries"]
    for e in entries:
        assert e["strength"] >= 0.0
