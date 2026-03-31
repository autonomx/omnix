"""
Narrative Memory System for the RPG Mode Upgrade.

Tracks narrative continuity across sessions including NPC relationships,
unresolved threads, emotional states, and major events.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class NarrativeMemory:
    """Tracks narrative state across game sessions."""
    relationships: Dict[str, Dict[str, int]] = field(default_factory=dict)  # npc -> player/char -> value
    unresolved_threads: List[Dict[str, Any]] = field(default_factory=list)
    emotional_states: Dict[str, Dict[str, float]] = field(default_factory=dict)  # char -> emotion -> intensity
    major_events: List[Dict[str, Any]] = field(default_factory=list)

    def update_relationship(self, npc_name: str, target: str, change: int) -> None:
        """Update relationship value between NPC and target."""
        if npc_name not in self.relationships:
            self.relationships[npc_name] = {}
        self.relationships[npc_name][target] = self.relationships[npc_name].get(target, 0) + change

    def get_relationship(self, npc_name: str, target: str) -> int:
        """Get relationship value."""
        return self.relationships.get(npc_name, {}).get(target, 0)

    def add_unresolved_thread(self, thread: Dict[str, Any]) -> None:
        """Add an unresolved narrative thread."""
        self.unresolved_threads.append(thread)

    def resolve_thread(self, thread_id: str) -> bool:
        """Mark a thread as resolved. Returns True if found and removed."""
        for i, thread in enumerate(self.unresolved_threads):
            if thread.get("id") == thread_id:
                self.unresolved_threads.pop(i)
                return True
        return False

    def update_emotional_state(self, character: str, emotion: str, intensity: float) -> None:
        """Update emotional state for a character."""
        if character not in self.emotional_states:
            self.emotional_states[character] = {}
        self.emotional_states[character][emotion] = intensity

    def add_major_event(self, event: Dict[str, Any]) -> None:
        """Add a major narrative event."""
        self.major_events.append(event)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationships": dict(self.relationships),
            "unresolved_threads": list(self.unresolved_threads),
            "emotional_states": dict(self.emotional_states),
            "major_events": list(self.major_events),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NarrativeMemory":
        return cls(
            relationships=data.get("relationships", {}),
            unresolved_threads=data.get("unresolved_threads", []),
            emotional_states=data.get("emotional_states", {}),
            major_events=data.get("major_events", []),
        )


def update_narrative_memory(session, scene: Dict[str, Any]) -> None:
    """
    Update narrative memory based on scene events.

    Tracks relationships, unresolved threads, emotional shifts.
    """
    # Update NPC relationships based on scene interactions
    for character in scene.get("characters", []):
        npc_name = character.get("name")
        emotion = character.get("emotion", "neutral")

        # Update emotional state
        session.narrative_memory.update_emotional_state(npc_name, emotion, 0.8)

        # Check for relationship changes in scene
        action = character.get("action", "")
        if "hostile" in action.lower() or "attack" in action.lower():
            session.narrative_memory.update_relationship(npc_name, "player", -5)
        elif "help" in action.lower() or "friendly" in action.lower():
            session.narrative_memory.update_relationship(npc_name, "player", 2)

    # Add major events if scene contains significant narrative moments
    narration = scene.get("narration", "")
    if any(keyword in narration.lower() for keyword in ["betrayal", "death", "alliance", "discovery"]):
        session.narrative_memory.add_major_event({
            "turn": session.turn_count,
            "description": narration[:200] + "..." if len(narration) > 200 else narration,
            "importance": 0.8
        })

    # Track unresolved threads (simplified)
    if "mystery" in narration.lower() or "unknown" in narration.lower():
        session.narrative_memory.add_unresolved_thread({
            "id": f"thread_{session.turn_count}",
            "description": "Unresolved mystery from recent events",
            "created_turn": session.turn_count
        })