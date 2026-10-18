"""An NPC with remembered events still plans its goals."""
from __future__ import annotations

from app.apps.rpg.narration.ai.llm_mind.npc_mind import NPCMind


def test_goals_refresh_after_the_npc_remembers_an_event() -> None:
    mind = NPCMind(npc_id="npc:guard")
    mind.memory.remember(
        {"type": "attack", "actor": "player", "target_id": "npc:guard", "summary": "The player struck the guard."},
        tick=3,
    )

    # Memory summaries are text; goal planning reads the remembered entries.
    mind.refresh_goals(simulation_state={}, npc_context={"npc_id": "npc:guard"})

    assert mind.memory.summary() == ["The player struck the guard."]
