"""
Story Engine — dynamic narrative arc management.

Creates, progresses, and resolves story arcs based on game events.
Arcs move through stages (setup → rising → climax → resolution) and
generate consequences at key transitions to keep the narrative engaging.
"""

import uuid
from typing import Any, Dict, List, Optional

from app.rpg.models import GameSession, PendingConsequence, StoryArc


def update_story_arcs(session: GameSession) -> List[PendingConsequence]:
    """
    Progress all active story arcs and return any consequences they generate.

    Called once per turn after the narrative director runs.
    """
    new_consequences: List[PendingConsequence] = []

    for arc in session.story_arcs:
        if arc.stage == "resolution":
            continue

        # Progress increases each turn
        arc.progress = min(1.0, arc.progress + 0.1)

        # Stage transitions
        if arc.progress > 0.3 and arc.stage == "setup":
            arc.stage = "rising"

        elif arc.progress > 0.7 and arc.stage == "rising":
            arc.stage = "climax"
            new_consequences.append(PendingConsequence(
                trigger_turn=session.turn_count + 1,
                source_event=f"story_climax_{arc.type}",
                narrative=f"The {arc.type} arc reaches its climax...",
                type="narrative",
                visibility="visible",
                importance=1.0,
                chain_id=arc.id,
            ))

        elif arc.progress >= 1.0 and arc.stage == "climax":
            arc.stage = "resolution"

    return new_consequences


def maybe_create_arc(
    session: GameSession,
    event_description: str,
) -> Optional[StoryArc]:
    """
    Inspect an event and create a new story arc if appropriate.

    Returns the new arc or ``None``.
    """
    desc_lower = event_description.lower()

    # Betrayal → revenge arc
    if "betray" in desc_lower or "betrayal" in desc_lower:
        arc = StoryArc(
            id=str(uuid.uuid4()),
            type="revenge",
            stage="setup",
            participants=["player"],
            description="A betrayal has set events in motion...",
        )
        session.story_arcs.append(arc)
        return arc

    # War / battle → war arc
    if "war" in desc_lower or "battle" in desc_lower:
        arc = StoryArc(
            id=str(uuid.uuid4()),
            type="war",
            stage="setup",
            participants=["player"],
            description="The drums of war begin to beat...",
        )
        session.story_arcs.append(arc)
        return arc

    # Mystery / strange / unknown → mystery arc
    if "mystery" in desc_lower or "strange" in desc_lower or "unknown" in desc_lower:
        arc = StoryArc(
            id=str(uuid.uuid4()),
            type="mystery",
            stage="setup",
            participants=["player"],
            description="Something mysterious is afoot...",
        )
        session.story_arcs.append(arc)
        return arc

    return None


def enforce_story(session: GameSession) -> Optional[Dict[str, Any]]:
    """
    Arc-aware narrative enforcement.

    Returns a directive dict when an arc needs the story pushed forward,
    or ``None`` when pacing is fine.
    """
    for arc in session.story_arcs:
        if arc.stage == "setup" and session.narrative_tension < 0.3:
            return {"type": "inciting_incident", "arc_id": arc.id}

        if arc.stage == "climax":
            return {"type": "major_conflict", "arc_id": arc.id}

    return None


def update_npc_goals(session: GameSession) -> List[PendingConsequence]:
    """
    Progress NPC active_goals each turn and fire consequences on completion.
    """
    new_consequences: List[PendingConsequence] = []

    for npc in session.npcs:
        for goal in npc.active_goals:
            ambition = npc.personality_traits.get("ambition", 0.5)
            goal["progress"] = min(1.0, goal.get("progress", 0) + 0.1 * ambition)

            if goal["progress"] >= 1.0:
                target = goal.get("target", "something")
                new_consequences.append(PendingConsequence(
                    trigger_turn=session.turn_count + 1,
                    source_event=f"{npc.name}_goal_complete",
                    narrative=f"{npc.name} achieves their goal regarding {target}.",
                    type="npc",
                    visibility="visible",
                    importance=0.9,
                    effect_diff={
                        "npc_changes": {
                            npc.name: {"current_action": "celebrate"},
                        },
                    },
                ))

        # Remove completed goals
        npc.active_goals = [g for g in npc.active_goals if g.get("progress", 0) < 1.0]

    return new_consequences
