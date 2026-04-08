"""Narrative Mapper — Converts mechanical events to narrative events.

This module implements PATCH 4 from the RPG design specification:
"ADD NARRATIVE EVENT LAYER"

The problem: Events are purely mechanical (damage, move, etc.) and
lack narrative context for memory and scene generation.
The solution: A transformer that converts mechanical events into
narrative events with summaries, tags, and emotional context.

Usage:
    narrative_events = to_narrative_events(events)
    events.extend(narrative_events)

The narrative events can then be consumed by:
- Memory system (for NPC recollection)
- Scene generation (for grounded narration)
- LLM prompts (for context-rich storytelling)
"""

from typing import Any, Dict, List, Optional

# Event type to narrative template mapping
NARRATIVE_TEMPLATES = {
    "damage": {
        "type": "narrative_event",
        "summary": "{source} strikes {target}",
        "tags": ["combat", "violence"],
    },
    "death": {
        "type": "narrative_event",
        "summary": "{target} has fallen",
        "tags": ["combat", "death"],
    },
    "critical_hit": {
        "type": "narrative_event",
        "summary": "{source} lands a devastating blow on {target}",
        "tags": ["combat", "critical"],
    },
    "heal": {
        "type": "narrative_event",
        "summary": "{source} heals {target}",
        "tags": ["support", "healing"],
    },
    "move": {
        "type": "narrative_event",
        "summary": "{source} moves to {position}",
        "tags": ["movement"],
    },
    "npc_action": {
        "type": "narrative_event",
        "summary": "{npc_id} performs {action}",
        "tags": ["action"],
    },
    "assist": {
        "type": "narrative_event",
        "summary": "{source} assists {target}",
        "tags": ["support", "alliance"],
    },
    "betrayal": {
        "type": "narrative_event",
        "summary": "{source} betrays {target}",
        "tags": ["betrayal", "conflict"],
    },
    "alliance_formed": {
        "type": "narrative_event",
        "summary": "{source} forms an alliance with {target}",
        "tags": ["alliance", "diplomacy"],
    },
}


def to_narrative_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a mechanical event to a narrative event.
    
    Takes a raw event dict and produces a narrative version with
    human-readable summary and categorical tags.
    
    Args:
        event: Raw event dict (e.g., {"type": "damage", "source": "guard", ...}).
        
    Returns:
        Narrative event dict, or None if no mapping exists.
    """
    event_type = event.get("type", "")
    
    # Direct story events are already narrative
    if event_type == "story_event":
        return {
            "type": "narrative_event",
            "summary": event.get("summary", event.get("text", "")),
            "tags": event.get("tags", ["story"]),
        }
    
    template = NARRATIVE_TEMPLATES.get(event_type)
    if not template:
        return None
    
    result = dict(template)
    
    # Build summary from template with event data
    summary = result["summary"]
    try:
        summary = summary.format(**event)
    except KeyError:
        # Some events may not have all required fields
        summary = f"{event_type} event occurred"
        
    result["summary"] = summary
    result["original_event"] = event_type
    result["tick"] = event.get("tick")
    
    return result


def to_narrative_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert a list of mechanical events to narrative events.
    
    Args:
        events: List of raw event dicts.
        
    Returns:
        List of narrative event dicts (only successfully converted events).
    """
    narrative_events = []
    
    for event in events:
        ne = to_narrative_event(event)
        if ne is not None:
            narrative_events.append(ne)
            
    return narrative_events


def enrich_events_with_narrative(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Enrich event list with narrative versions (in-place extension).
    
    This is the main entry point for PATCH 4. It adds narrative
    events to the existing event list so they flow through to
    memory and scene generation.
    
    Usage in game loop:
        events = convert_actions_to_events(session, npc_actions)
        events.extend(director_output.story_events)
        enrich_events_with_narrative(events)  # PATCH 4
        
    Args:
        events: List of events to enrich (modified in place).
        
    Returns:
        The enriched events list (same object, modified).
    """
    narrative = to_narrative_events(events)
    events.extend(narrative)
    return events