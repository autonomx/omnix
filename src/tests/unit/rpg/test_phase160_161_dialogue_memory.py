"""Unit tests for Phase 16.0/16.1 — Dialogue memory shaping + lifecycle automation."""
from app.rpg.memory.dialogue_context import (
    build_actor_memory_context,
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
    build_world_rumor_context,
)
from app.rpg.memory.lifecycle import apply_dialogue_memory_hooks


def test_dialogue_memory_prompt_is_bounded_and_deterministic():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "npc:a": {
                    "entries": [
                        {"text": "B", "strength": 0.5},
                        {"text": "A", "strength": 0.5},
                    ]
                }
            },
            "world_memory": {"rumors": []},
        }
    }
    context = build_dialogue_memory_context(simulation_state, actor_id="npc:a")
    prompt = build_llm_memory_prompt_block(context)
    assert context["actor_memory"][0]["text"] == "A"
    assert len(prompt) <= 2000


def test_apply_dialogue_memory_hooks_decays_and_reinforces():
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": [{"text": "Known fact", "strength": 0.5}]}},
            "world_memory": {"rumors": []},
        }
    }
    out = apply_dialogue_memory_hooks(
        simulation_state,
        actor_id="npc:a",
        player_text="hello there",
    )
    entries = out["memory_state"]["actor_memory"]["npc:a"]["entries"]
    assert len(entries) >= 1


def test_apply_dialogue_memory_hooks_reinforces_with_explicit_text():
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": []}},
            "world_memory": {"rumors": []},
        }
    }
    out = apply_dialogue_memory_hooks(
        simulation_state,
        actor_id="npc:a",
        reinforce_text="important topic",
    )
    entries = out["memory_state"]["actor_memory"]["npc:a"]["entries"]
    texts = [e["text"] for e in entries]
    assert "important topic" in texts


def test_apply_dialogue_memory_hooks_uses_player_text_as_fallback():
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": []}},
            "world_memory": {"rumors": []},
        }
    }
    out = apply_dialogue_memory_hooks(
        simulation_state,
        actor_id="npc:a",
        player_text="fallback text",
    )
    entries = out["memory_state"]["actor_memory"]["npc:a"]["entries"]
    texts = [e["text"] for e in entries]
    assert "fallback text" in texts


def test_apply_dialogue_memory_hooks_decays_existing():
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": [{"text": "old fact", "strength": 0.5}]}},
            "world_memory": {"rumors": [{"text": "old rumor", "strength": 0.8, "reach": 2}]},
        }
    }
    out = apply_dialogue_memory_hooks(
        simulation_state,
        actor_id="npc:a",
        player_text="",
    )
    # Even without reinforcement, decay should run
    entries = out["memory_state"]["actor_memory"]["npc:a"]["entries"]
    assert entries[0]["strength"] < 0.5  # decayed from 0.5
    rumors = out["memory_state"]["world_memory"]["rumors"]
    assert rumors[0]["strength"] < 0.8  # decayed from 0.8


def test_apply_dialogue_memory_hooks_handles_none_state():
    out = apply_dialogue_memory_hooks(
        None,
        actor_id="npc:a",
        player_text="test",
    )
    assert "memory_state" in out


def test_build_actor_memory_context_respects_limit():
    entries = [{"text": f"fact_{i}", "strength": float(i) / 10.0} for i in range(20)]
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": entries}},
        }
    }
    result = build_actor_memory_context(simulation_state, "npc:a", limit=3)
    assert len(result) == 3


def test_build_world_rumor_context_respects_limit():
    rumors = [{"text": f"rumor_{i}", "strength": float(i) / 10.0} for i in range(20)]
    simulation_state = {
        "memory_state": {
            "world_memory": {"rumors": rumors},
        }
    }
    result = build_world_rumor_context(simulation_state, limit=3)
    assert len(result) == 3


def test_build_dialogue_memory_context_with_actor_id_string():
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": [{"text": "fact", "strength": 0.5}]}},
            "world_memory": {"rumors": []},
        }
    }
    ctx = build_dialogue_memory_context(simulation_state, actor_id="npc:a")
    assert ctx["actor_id"] == "npc:a"
    assert len(ctx["actor_memory"]) == 1


def test_build_dialogue_memory_context_with_actor_ids_list():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "npc:a": {"entries": [{"text": "a_fact", "strength": 0.5}]},
                "npc:b": {"entries": [{"text": "b_fact", "strength": 0.7}]},
            },
            "world_memory": {"rumors": []},
        }
    }
    ctx = build_dialogue_memory_context(simulation_state, actor_ids=["npc:a", "npc:b"])
    assert len(ctx["actor_memory"]) == 2
    assert "npc:a" in ctx["actor_ids"]
    assert "npc:b" in ctx["actor_ids"]


def test_build_llm_memory_prompt_block_empty_returns_none_marker():
    ctx = {"actor_memory": [], "world_rumors": []}
    prompt = build_llm_memory_prompt_block(ctx)
    assert "none" in prompt.lower() or "MEMORY CONTEXT" in prompt


def test_build_llm_memory_prompt_block_with_rumors():
    ctx = {
        "actor_memory": [],
        "world_rumors": [{"text": "Plague spreads", "strength": 0.9}],
    }
    prompt = build_llm_memory_prompt_block(ctx)
    assert "Plague spreads" in prompt


def test_lifecycle_hooks_reinforce_text_capped():
    """Reinforce text is capped at 240 chars."""
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": []}},
            "world_memory": {"rumors": []},
        }
    }
    long_text = "x" * 500
    out = apply_dialogue_memory_hooks(
        simulation_state,
        actor_id="npc:a",
        reinforce_text=long_text,
    )
    entries = out["memory_state"]["actor_memory"]["npc:a"]["entries"]
    for e in entries:
        assert len(e["text"]) <= 240
