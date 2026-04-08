"""Director Types — Structured output contract for Story Director.

This module defines the DirectorOutput class that serves as the
formal contract between the Story Director and the rest of the system.

The design spec requires structured output, not text:
    - npc_goal_updates: Goals to inject into NPCs
    - story_events: Narrative events to inject
    - world_state_updates: Global state changes
    - tension_delta: Tension adjustment
"""

from typing import Any, Dict, List, Optional


class DirectorOutput:
    """Structured output from the Story Director's decision cycle.
    
    This is the authoritative command structure that the Story Director
    produces each turn. It replaces the old text-based approach with
    a formal contract that other systems can consume reliably.
    
    Attributes:
        npc_goal_updates: Dict mapping NPC IDs to lists of goal dicts
            to inject into those NPCs. Example:
            {"npc_1": [{"type": "attack", "target": "player"}]}
        story_events: List of narrative events that should be added
            to the event stream. These are story-level events, not
            mechanical events like "damage" or "move".
        world_state_updates: Dict of key-value pairs to update in
            the global world state. Applied before NPC planning.
        tension_delta: Amount to adjust global tension by. Can be
            positive (escalate) or negative (de-escalate).
    """
    
    def __init__(
        self,
        npc_goal_updates: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        story_events: Optional[List[Dict[str, Any]]] = None,
        world_state_updates: Optional[Dict[str, Any]] = None,
        tension_delta: float = 0.0,
        future_beats: Optional[List[Dict[str, Any]]] = None,
    ):
        """Initialize DirectorOutput with structured data.
        
        Args:
            npc_goal_updates: Goals to inject into NPCs.
            story_events: Narrative events to inject.
            world_state_updates: Global state changes.
            tension_delta: Tension adjustment.
            future_beats: Planned story beats for future turns (GAP 1 fix).
                Each beat has {"turn": +N, "event": {...}} for forward planning.
        """
        self.npc_goal_updates = npc_goal_updates or {}
        self.story_events = story_events or []
        self.world_state_updates = world_state_updates or {}
        self.tension_delta = tension_delta
        self.future_beats = future_beats or []
        
    def has_npc_updates(self) -> bool:
        """Check if there are NPC goal updates."""
        return bool(self.npc_goal_updates)
        
    def has_story_events(self) -> bool:
        """Check if there are story events to inject."""
        return bool(self.story_events)
        
    def has_world_updates(self) -> bool:
        """Check if there are world state updates."""
        return bool(self.world_state_updates)
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "npc_goal_updates": self.npc_goal_updates,
            "story_events": self.story_events,
            "world_state_updates": self.world_state_updates,
            "tension_delta": self.tension_delta,
            "future_beats": self.future_beats,
        }
        
    @classmethod
    def empty(cls) -> 'DirectorOutput':
        """Create an empty DirectorOutput (no changes).
        
        Returns:
            Empty DirectorOutput with no updates.
        """
        return cls()