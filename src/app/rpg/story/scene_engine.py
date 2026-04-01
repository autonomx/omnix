"""Scene Engine (Cinematic Layer) — TIER 9: Narrative Intelligence Layer.

This module implements the Scene Engine from Tier 9 of the RPG design specification.

Purpose:
    Convert raw world events into playable narrative scenes with clear stakes,
    participants, and cinematic structure.

The Problem:
    - World events are just data dicts (shortage, coup, battle)
    - No cinematic structure or dramatic tension
    - Player experiences events as isolated incidents, not connected scenes

The Solution:
    SceneEngine transforms raw events into Scene objects with:
    - Type classification (coup, battle, trade, dialogue, crisis)
    - Location and participants
    - Dramatic stakes (what's at risk)
    - Resolution state tracking

Usage:
    engine = SceneEngine()
    scenes = engine.generate_from_events([
        {"type": "coup", "faction": "mages_guild", ...},
        {"type": "shortage", "location": "docks", ...},
    ])

Architecture:
    Raw Events → Scene Classification → Scene Building → Active Scene Tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Scene:
    """A playable narrative scene derived from world events.
    
    Scenes are the atomic unit of narrative experience. They convert
    raw simulation events into structured dramatic moments with
    clear stakes and participants.
    
    Attributes:
        id: Unique scene identifier.
        type: Scene type ("coup", "battle", "trade", "dialogue", "crisis").
        location: Where the scene takes place.
        participants: Character/faction IDs involved.
        description: Scene description/narrative hook.
        stakes: What's at risk in this scene.
        resolved: Whether the scene has been played out.
        resolution: How the scene was resolved (if resolved).
        metadata: Additional scene data.
    """
    
    id: str
    type: str  # "coup", "battle", "trade", "dialogue", "crisis"
    location: str = "unknown"
    participants: List[str] = field(default_factory=list)
    description: str = "A scene unfolds."
    stakes: str = "Unknown"
    resolved: bool = False
    resolution: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def resolve(self, outcome: str) -> None:
        """Mark the scene as resolved with an outcome.
        
        Args:
            outcome: Description of how the scene was resolved.
        """
        self.resolved = True
        self.resolution = outcome
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize scene to dict.
        
        Returns:
            Scene data as dictionary.
        """
        return {
            "id": self.id,
            "type": self.type,
            "location": self.location,
            "participants": list(self.participants),
            "description": self.description,
            "stakes": self.stakes,
            "resolved": self.resolved,
            "resolution": self.resolution,
            "metadata": dict(self.metadata),
        }


class SceneEngine:
    """Converts raw world events into playable narrative scenes.
    
    The SceneEngine analyzes incoming events and transforms them into
    structured scenes with dramatic stakes, locations, and participants.
    
    Integration Points:
        - PlayerLoop.step(): After event collection, generates scenes
        - Narrative Renderer: Uses scenes for narrative generation
        - Memory System: Stores resolved scenes for continuity
    
    Usage:
        engine = SceneEngine()
        
        # In game loop
        scenes = engine.generate_from_events(world_events)
        
        # Later, resolve a scene
        for scene in scenes:
            scene.resolve("Player mediated peace")
    """
    
    def __init__(self, max_active_scenes: int = 20):
        """Initialize the SceneEngine.
        
        Args:
            max_active_scenes: Maximum number of simultaneously active scenes.
        """
        self.active_scenes: List[Scene] = []
        self.scene_history: List[Scene] = []
        self.max_active_scenes = max_active_scenes
        self._scene_counter = 0
        
    def generate_from_events(self, events: List[Dict[str, Any]]) -> List[Scene]:
        """Convert raw events into scenes.
        
        Analyzes each event and creates appropriate scene objects.
        Merges related events when possible to avoid scene spam.
        
        Args:
            events: List of world event dicts.
            
        Returns:
            List of newly created Scene objects.
        """
        new_scenes: List[Scene] = []
        
        for event in events:
            event_type = event.get("type", "unknown")
            
            scene = None
            
            if event_type == "coup":
                scene = self._create_coup_scene(event)
            elif event_type == "shortage":
                scene = self._create_crisis_scene(event)
            elif event_type == "faction_conflict":
                scene = self._create_battle_scene(event)
            elif event_type == "faction_alliance":
                scene = self._create_alliance_scene(event)
            elif event_type == "trade":
                scene = self._create_trade_scene(event)
            elif event_type == "player_action":
                scene = self._create_action_scene(event)
            else:
                scene = self._create_generic_scene(event)
            
            if scene:
                new_scenes.append(scene)
        
        # Add to active scenes (respecting max limit)
        self._add_active_scenes(new_scenes)
        
        return new_scenes
    
    def _add_active_scenes(self, scenes: List[Scene]) -> None:
        """Add scenes to active list, respecting max limit.
        
        If adding scenes would exceed the limit, oldest resolved scenes
        are moved to history first.
        
        Args:
            scenes: Scenes to add.
        """
        for scene in scenes:
            # If at limit, move oldest resolved scene to history
            if len(self.active_scenes) >= self.max_active_scenes:
                # Find oldest resolved scene
                for i, active in enumerate(self.active_scenes):
                    if active.resolved:
                        self.scene_history.append(self.active_scenes.pop(i))
                        break
                else:
                    # No resolved scenes, move oldest unresolvable
                    oldest = self.active_scenes.pop(0)
                    self.scene_history.append(oldest)
            
            self.active_scenes.append(scene)
    
    def _create_coup_scene(self, event: Dict[str, Any]) -> Scene:
        """Create a coup scene from event.
        
        Args:
            event: Coup event dict.
            
        Returns:
            Scene representing the coup.
        """
        faction = event.get("faction", "unknown_faction")
        old_leader = event.get("old_leader", "former_leader")
        new_leader = event.get("new_leader", "usurper")
        location = event.get("location", "capital")
        
        return Scene(
            id=f"scene_coup_{self._scene_counter}",
            type="coup",
            location=location,
            participants=[old_leader, new_leader, faction],
            description=f"A violent overthrow of leadership is underway in {faction}.",
            stakes="Control of the faction",
            metadata={"faction": faction, "old_leader": old_leader, "new_leader": new_leader},
        )
    
    def _create_crisis_scene(self, event: Dict[str, Any]) -> Scene:
        """Create a crisis scene from shortage event.
        
        Args:
            event: Shortage event dict.
            
        Returns:
            Scene representing the crisis.
        """
        location = event.get("location", "unknown_location")
        good = event.get("good", "supplies")
        severity = event.get("severity", 0.5)
        
        if severity > 0.8:
            stakes = f"Survival of {location} depends on finding {good}"
        elif severity > 0.5:
            stakes = f"{location} faces serious {good} shortage"
        else:
            stakes = f"Minor {good} shortage in {location}"
        
        return Scene(
            id=f"scene_crisis_{self._scene_counter}",
            type="crisis",
            location=location,
            participants=[location],
            description=f"{location} is running critically low on {good}.",
            stakes=stakes,
            metadata={"good": good, "severity": severity},
        )
    
    def _create_battle_scene(self, event: Dict[str, Any]) -> Scene:
        """Create a battle scene from faction conflict event.
        
        Args:
            event: Faction conflict event dict.
            
        Returns:
            Scene representing the battle.
        """
        factions = event.get("factions", ["unknown_a", "unknown_b"])
        description = event.get("description", "Forces clash in battle")
        importance = event.get("importance", 0.5)
        
        if importance > 0.8:
            stakes = "Decisive engagement that could shift the balance of power"
        elif importance > 0.5:
            stakes = "Significant territorial and strategic stakes"
        else:
            stakes = "Minor skirmish with limited consequences"
        
        return Scene(
            id=f"scene_battle_{self._scene_counter}",
            type="battle",
            location=event.get("location", "battleground"),
            participants=factions,
            description=description,
            stakes=stakes,
            metadata={"power_ratio": event.get("power_ratio", 0.5)},
        )
    
    def _create_alliance_scene(self, event: Dict[str, Any]) -> Scene:
        """Create an alliance scene from event.
        
        Args:
            event: Alliance event dict.
            
        Returns:
            Scene representing the alliance formation.
        """
        factions = event.get("factions", ["unknown_a", "unknown_b"])
        
        return Scene(
            id=f"scene_alliance_{self._scene_counter}",
            type="dialogue",
            location=event.get("location", "neutral_grounds"),
            participants=factions,
            description=event.get("description", "A new alliance is being forged"),
            stakes="Diplomatic unity and shared power",
            metadata={"importance": event.get("importance", 0.5)},
        )
    
    def _create_trade_scene(self, event: Dict[str, Any]) -> Scene:
        """Create a trade scene from event.
        
        Args:
            event: Trade event dict.
            
        Returns:
            Scene representing the trade.
        """
        location_from = event.get("from", "source")
        location_to = event.get("to", "destination")
        good = event.get("good", "goods")
        
        return Scene(
            id=f"scene_trade_{self._scene_counter}",
            type="trade",
            location=location_to,
            participants=[location_from, location_to],
            description=f"A trade route carries {good} from {location_from} to {location_to}",
            stakes="Economic prosperity and political goodwill",
            metadata={"good": good, "from": location_from, "to": location_to},
        )
    
    def _create_action_scene(self, event: Dict[str, Any]) -> Scene:
        """Create a scene from player action.
        
        Args:
            event: Player action event dict.
            
        Returns:
            Scene representing the player's action.
        """
        description = event.get("description", "The player takes action")
        actors = event.get("actors", ["player"])
        
        return Scene(
            id=f"scene_action_{self._scene_counter}",
            type="dialogue",
            location=event.get("location", "current_location"),
            participants=actors,
            description=description,
            stakes="Player agency and world impact",
        )
    
    def _create_generic_scene(self, event: Dict[str, Any]) -> Scene:
        """Create a generic scene from any event.
        
        Args:
            event: Event dict.
            
        Returns:
            Generic scene.
        """
        event_type = event.get("type", "unknown")
        description = event.get("description", event_type)
        actors = event.get("actors", event.get("faction", "unknown"))
        if isinstance(actors, str):
            actors = [actors]
        elif not isinstance(actors, list):
            actors = ["unknown"]
        
        return Scene(
            id=f"scene_generic_{self._scene_counter}",
            type=event_type,
            location=event.get("location", "unknown"),
            participants=actors,
            description=description,
            stakes="Events unfold in the world",
        )
    
    def resolve_scene(self, scene_id: str, outcome: str) -> Optional[Scene]:
        """Resolve an active scene by ID.
        
        Args:
            scene_id: ID of scene to resolve.
            outcome: Description of resolution.
            
        Returns:
            Resolved scene, or None if not found.
        """
        for scene in self.active_scenes:
            if scene.id == scene_id:
                scene.resolve(outcome)
                return scene
        return None
    
    def get_active_scenes(self) -> List[Scene]:
        """Get all currently active scenes.
        
        Returns:
            List of active Scene objects.
        """
        return list(self.active_scenes)
    
    def get_unresolved_scenes(self) -> List[Scene]:
        """Get all unresolved active scenes.
        
        Returns:
            List of unresolved Scene objects.
        """
        return [s for s in self.active_scenes if not s.resolved]
    
    def get_scene_history(self) -> List[Scene]:
        """Get all resolved scenes in history.
        
        Returns:
            List of historical Scene objects.
        """
        return list(self.scene_history)
    
    def clear(self) -> None:
        """Clear all active and historical scenes."""
        self.scene_history.extend(self.active_scenes)
        self.active_scenes.clear()
    
    def reset(self) -> None:
        """Reset scene engine to initial state."""
        self.active_scenes.clear()
        self.scene_history.clear()
        self._scene_counter = 0