"""Prompt Builder with Hard Persona Lock.

Patch 3: Hard Persona Lock
- NPC identity (name, role) is hardcoded into prompt
- Personality traits (aggression, honor, greed) are explicit
- Behavior rules bind traits to expected actions
- Prevents "villager talks like philosopher king" drift
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

VALID_INTENTS = [
    "interact_with_npc",
    "pursue_goal",
    "react_to_event",
    "idle",
]


def build_npc_prompt(context: Dict[str, Any]) -> str:
    """Build a prompt with hard persona lock.

    Patch 3: Identity and personality are explicitly stated
    and bound to behavior rules to prevent drift.

    Args:
        context: Dict with npc, personality, memory, goals, world keys.

    Returns:
        Formatted prompt string for the LLM.
    """
    npc = context.get("npc", {})
    personality = context.get("personality", {})
    memory_summary = context.get("memory_summary", [])
    goals = context.get("goals", [])
    world = context.get("world", {})
    recent_events = context.get("recent_events", [])
    intent_priority = context.get("intent_priority", False)

    lines: List[str] = []

    # ---- IDENTITY (Patch 3: Hard lock) ----
    lines.append("You are this NPC. You MUST stay consistent.")
    lines.append("")
    lines.append("IDENTITY:")
    lines.append(f"Name: {npc.get('name', 'unknown')}")
    lines.append(f"Role: {npc.get('role', 'unknown')}")
    lines.append("")

    # ---- PERSONALITY TRAITS (Patch 3) ----
    lines.append("PERSONALITY TRAITS:")
    lines.append(f"- Aggression: {personality.get('aggression', 0.5)}")
    lines.append(f"- Honor: {personality.get('honor', 0.5)}")
    lines.append(f"- Greed: {personality.get('greed', 0.5)}")
    lines.append("")

    # ---- BEHAVIOR RULES (Patch 3: Binding) ----
    lines.append("Behavior Rules:")
    lines.append("- High aggression -> prefer attack")
    lines.append("- High honor -> avoid betrayal")
    lines.append("- High greed -> prefer trade/reward")
    lines.append("")

    # ---- MEMORY ----
    if memory_summary:
        lines.append("RECENT MEMORIES:")
        for m in memory_summary[:10]:
            if isinstance(m, dict):
                lines.append(
                    f"- {m.get('type', '?')}: "
                    f"{m.get('actor', '?')} -> {m.get('target', '?')}"
                )
            else:
                lines.append(f"- {m}")
        lines.append("")

    # ---- ACTIVE GOALS ----
    if goals:
        lines.append("ACTIVE GOALS:")
        for g in goals:
            if isinstance(g, dict):
                lines.append(
                    f"- {g.get('type', '?')} (priority={g.get('priority', 0):.2f})"
                )
            else:
                lines.append(f"- {g}")
        lines.append("")

    # ---- WORLD STATE ----
    lines.append("WORLD:")
    visible = (
        world.get("visible_entities", [])
        if isinstance(world, dict)
        else world.get("entities", [])
        if isinstance(world, dict)
        else []
    )
    location = (
        world.get("location", "unknown")
        if isinstance(world, dict)
        else "unknown"
    )
    lines.append(f"Location: {location}")
    if visible:
        lines.append("Visible entities:")
        for v in visible[:10]:
            if isinstance(v, dict):
                lines.append(
                    f"  - {v.get('name', v.get('id', '?'))} "
                    f"(role={v.get('role', '?')})"
                )
            else:
                lines.append(f"  - {v}")
    lines.append("")

    # ---- RECENT EVENTS ----
    if recent_events:
        lines.append("RECENT EVENTS:")
        for e in recent_events[:5]:
            if isinstance(e, dict):
                lines.append(
                    f"- {e.get('type', '?')}: "
                    f"{e.get('actor', '?')} -> {e.get('target', '?')}"
                )
        lines.append("")

    # ---- INTENT RULES (Patch 7) ----
    if intent_priority:
        lines.append("INTENT PRIORITY RULES:")
        lines.append(
            "- If another NPC is present and relevant, prioritize interact_with_npc"
        )
        lines.append("- Otherwise, pursue your highest-priority goal")
        lines.append(
            "- React to events if something significant just happened"
        )
        lines.append("- Fall back to idle if none of the above apply")
        lines.append("")

    # ---- OUTPUT FORMAT ----
    lines.append("OUTPUT FORMAT:")
    lines.append("Respond with a JSON object containing:")
    lines.append("{")
    lines.append('  "intent": "interact_with_npc|pursue_goal|react_to_event|idle",')
    lines.append('  "target": "<npc_id or goal or event>",')
    lines.append('  "action": "<action_type>",')
    lines.append('  "dialogue": "<what you say>",')
    lines.append('  "emotion": "<happy|angry|neutral|fearful|suspicious>"')
    lines.append("}")

    return "\n".join(lines)


def build_context(
    npc: Dict[str, Any],
    personality: Dict[str, float],
    memory: Optional[List[Dict[str, Any]]] = None,
    goals: Optional[List[Dict[str, Any]]] = None,
    world: Optional[Dict[str, Any]] = None,
    recent_events: Optional[List[Dict[str, Any]]] = None,
    intent_priority: bool = True,
) -> Dict[str, Any]:
    """Build a prompt context dict.

    Args:
        npc: NPC identity (name, role).
        personality: NPC traits (aggression, honor, greed).
        memory: Memory summary list.
        goals: Active goals list.
        world: World state dict.
        recent_events: Recent events list.
        intent_priority: Whether to include intent priority rules.

    Returns:
        Context dict ready for prompt generation.
    """
    return {
        "npc": npc,
        "personality": personality,
        "memory_summary": memory or [],
        "goals": goals or [],
        "world": world or {},
        "recent_events": recent_events or [],
        "intent_priority": intent_priority,
    }