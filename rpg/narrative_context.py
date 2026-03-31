def build_context(session):
    phase = update_phase(session.narrative_state["tension"])

    session.narrative_state["phase"] = phase

    return {
        "world_summary": session.world.summary if session.world else "",
        "active_arcs": session.story_arcs,
        "npc_states": [
            {
                "id": npc.id,
                "emotion": npc.emotional_state,
                "goal": npc.goal,
                "hp": npc.hp
            }
            for npc in session.npcs
        ],
        "recent_events": session.recent_events[-10:],
        "player_profile": session.player.profile if session.player else {},
        "tone": session.config.tone,
        "tension": session.narrative_state["tension"],
        "phase": phase
    }


def update_tension(current, change):
    delta = {
        "increase": 0.1,
        "decrease": -0.1,
        "twist": 0.2,
        "stable": 0.0
    }[change]

    return max(0.0, min(1.0, current + delta))


def update_phase(tension):
    if tension < 0.3:
        return "setup"
    elif tension < 0.6:
        return "rising"
    elif tension < 0.85:
        return "climax"
    return "resolution"