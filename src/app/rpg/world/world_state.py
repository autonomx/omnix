"""World State — Explicit world state management layer.

This module implements the Explicit World State Layer from the design spec.
It provides a serializable view of the world that the Director uses
for decision-making and that tools use for modification.

Purpose:
    Maintain explicit world state that all systems can read and modify.
    Director decisions are based on this state, not implicit assumptions.

Architecture:
    Events → World State Updates → Director Decisions → Tool Execution
                   ↕
            WorldState.serialize() → LLM Prompt

Usage:
    world = WorldState()
    world.add_entity("player", {"hp": 100, "position": (0, 0)})
    world.update_relationship("player", "goblin", -0.5)
    state = world.serialize()  # For LLM prompt

Design Compliance:
    - Serializable for LLM prompts
    - Entity tracking
    - Relationship tracking
    - Time tracking
    - Sync with memory events
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple


class WorldState:
    """Explicit representation of the game world state.
    
    This is the ground truth of the world that all systems reference.
    The Director uses this for decision-making. Tools modify this.
    Memory events update this.
    
    Attributes:
        entities: Dict mapping entity IDs to their properties.
        relationships: Dict mapping (entity_a, entity_b) → relationship value.
        time: Current world time (ticks).
        flags: Arbitrary world flags (e.g., "alert_level").
        locations: Dict mapping location names to positions.
        history: Recent world events for context.
    """
    
    def __init__(self):
        """Initialize an empty world state."""
        self.entities: Dict[str, Dict[str, Any]] = {}
        self.relationships: Dict[Tuple[str, str], float] = {}
        self.time: int = 0
        self.flags: Dict[str, Any] = {}
        self.locations: Dict[str, Tuple[int, int]] = {}
        self.history: List[Dict[str, Any]] = []
        
        # Entity existence tracking
        self._active_entities: Set[str] = set()
        
    # =========================================================
    # ENTITY MANAGEMENT
    # =========================================================
    
    def add_entity(self, entity_id: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """Add an entity to the world state.
        
        Args:
            entity_id: Unique entity identifier.
            properties: Dict of entity properties (hp, position, etc).
        """
        self.entities[entity_id] = properties or {}
        self._active_entities.add(entity_id)
        
    def remove_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Remove an entity from the world state.
        
        Args:
            entity_id: Entity to remove.
            
        Returns:
            The entity's properties if it existed, None otherwise.
        """
        if entity_id in self.entities:
            self._active_entities.discard(entity_id)
            return self.entities.pop(entity_id)
        return None
        
    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get entity properties.
        
        Args:
            entity_id: Entity identifier.
            
        Returns:
            Entity properties dict, or None if not found.
        """
        return self.entities.get(entity_id)
        
    def update_entity(self, entity_id: str, properties: Dict[str, Any]) -> None:
        """Update entity properties.
        
        Args:
            entity_id: Entity to update.
            properties: Properties to merge (overwrites existing keys).
        """
        if entity_id in self.entities:
            self.entities[entity_id].update(properties)
        else:
            self.add_entity(entity_id, properties)
            
    def has_entity(self, entity_id: str) -> bool:
        """Check if an entity exists.
        
        Args:
            entity_id: Entity identifier.
            
        Returns:
            True if entity exists.
        """
        return entity_id in self.entities
        
    def get_active_entities(self) -> Set[str]:
        """Get all active entity IDs.
        
        Returns:
            Set of active entity IDs.
        """
        return self._active_entities.copy()
        
    def apply_event(self, event: Dict[str, Any]) -> None:
        """Apply an event to update world state.
        
        This is the primary way the world state changes.
        Events from the event bus are applied here.
        
        Args:
            event: Event dict to apply.
        """
        etype = event.get("type", "")
        
        if etype == "damage":
            self._apply_damage(event)
        elif etype == "death":
            self._apply_death(event)
        elif etype == "heal":
            self._apply_heal(event)
        elif etype == "move":
            self._apply_move(event)
        elif etype == "spawn":
            self._apply_spawn(event)
        elif etype == "relationship_update":
            self._apply_relationship_update(event)
            
        # Record event in history
        self.history.append(event)
        if len(self.history) > 100:
            self.history = self.history[-100:]
            
    def _apply_damage(self, event: Dict[str, Any]) -> None:
        """Apply damage event.
        
        Args:
            event: Damage event dict.
        """
        target = event.get("target")
        amount = event.get("amount", 0)
        
        if target in self.entities:
            current_hp = self.entities[target].get("hp", 0)
            self.entities[target]["hp"] = max(0, current_hp - amount)
            
    def _apply_death(self, event: Dict[str, Any]) -> None:
        """Apply death event.
        
        Args:
            event: Death event dict.
        """
        target = event.get("target")
        if target in self.entities:
            self.entities[target]["hp"] = 0
            self.entities[target]["is_active"] = False
            self._active_entities.discard(target)
            
    def _apply_heal(self, event: Dict[str, Any]) -> None:
        """Apply heal event.
        
        Args:
            event: Heal event dict.
        """
        target = event.get("target")
        amount = event.get("amount", 0)
        
        if target in self.entities:
            current_hp = self.entities[target].get("hp", 0)
            max_hp = self.entities[target].get("max_hp", 100)
            self.entities[target]["hp"] = min(max_hp, current_hp + amount)
            
    def _apply_move(self, event: Dict[str, Any]) -> None:
        """Apply move event.
        
        Args:
            event: Move event dict.
        """
        entity = event.get("entity")
        to_pos = event.get("to")
        
        if entity in self.entities and to_pos:
            self.entities[entity]["position"] = to_pos
            
    def _apply_spawn(self, event: Dict[str, Any]) -> None:
        """Apply spawn event.
        
        Args:
            event: Spawn event dict.
        """
        entity_id = event.get("entity") or event.get("entity_id")
        position = event.get("position")
        entity_type = event.get("entity_type", "npc")
        
        if entity_id:
            props = {
                "entity_type": entity_type,
                "is_active": True,
            }
            if position:
                props["position"] = position
            self.add_entity(entity_id, props)
            
    def _apply_relationship_update(self, event: Dict[str, Any]) -> None:
        """Apply relationship update event.
        
        Args:
            event: Relationship event dict.
        """
        a = event.get("a")
        b = event.get("b")
        value = event.get("value", 0)
        
        if a and b:
            self.update_relationship(a, b, value)
        
    # =========================================================
    # RELATIONSHIP MANAGEMENT
    # =========================================================
    
    def update_relationship(self, a: str, b: str, delta: float) -> None:
        """Update relationship between two entities.
        
        Positive values = friendly, negative = hostile.
        
        Args:
            a: First entity.
            b: Second entity.
            delta: Relationship change delta.
        """
        key = self._relationship_key(a, b)
        current = self.relationships.get(key, 0.0)
        self.relationships[key] = current + delta
        # Clamp to [-1, 1]
        self.relationships[key] = max(-1.0, min(1.0, self.relationships[key]))
        
    def get_relationship(self, a: str, b: str) -> float:
        """Get current relationship value.
        
        Args:
            a: First entity.
            b: Second entity.
            
        Returns:
            Float relationship value (-1=hostile, 1=friendly).
        """
        key = self._relationship_key(a, b)
        return self.relationships.get(key, 0.0)
        
    def get_all_relationships(self, entity: str) -> Dict[str, float]:
        """Get all relationships for an entity.
        
        Args:
            entity: Entity to get relationships for.
            
        Returns:
            Dict mapping other entity IDs to relationship values.
        """
        result = {}
        for (a, b), value in self.relationships.items():
            if a == entity:
                result[b] = value
            elif b == entity:
                result[a] = value
        return result
        
    def has_hostile_relationship(self, a: str, b: str, threshold: float = -0.3) -> bool:
        """Check if two entities have a hostile relationship.
        
        Args:
            a: First entity.
            b: Second entity.
            threshold: Threshold below which is considered hostile.
            
        Returns:
            True if relationship is below threshold.
        """
        return self.get_relationship(a, b) < threshold
        
    def has_friendly_relationship(self, a: str, b: str, threshold: float = 0.3) -> bool:
        """Check if two entities have a friendly relationship.
        
        Args:
            a: First entity.
            b: Second entity.
            threshold: Threshold above which is considered friendly.
            
        Returns:
            True if relationship is above threshold.
        """
        return self.get_relationship(a, b) > threshold
        
    @staticmethod
    def _relationship_key(a: str, b: str) -> Tuple[str, str]:
        """Get canonical relationship key (sorted).
        
        Args:
            a: First entity.
            b: Second entity.
            
        Returns:
            Tuple with entities in sorted order.
        """
        return tuple(sorted([a, b]))
        
    # =========================================================
    # SERIALIZATION (FOR LLM PROMPTS)
    # =========================================================
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize world state for LLM prompt.
        
        Returns compact representation including:
        - Active entities with key properties
        - Relationships
        - Current time and flags
        
        Returns:
            Dict suitable for JSON serialization and LLM consumption.
        """
        # Only include relevant entity properties
        entity_summary = {}
        for eid, props in self.entities.items():
            entity_summary[eid] = {
                "hp": props.get("hp"),
                "is_active": props.get("is_active", True),
                "position": props.get("position"),
            }
            # Include entity_type if present
            if "entity_type" in props:
                entity_summary[eid]["entity_type"] = props["entity_type"]
                
        # Relationships as readable strings
        rel_summary = {}
        for (a, b), value in self.relationships.items():
            key = f"{a}↔{b}"
            rel_summary[key] = round(value, 2)
            
        return {
            "entities": entity_summary,
            "relationships": rel_summary,
            "time": self.time,
            "flags": self.flags.copy(),
            "locations": dict(self.locations),
        }
        
    def serialize_for_prompt(self) -> str:
        """Serialize world state as human-readable text for LLM prompt.
        
        Returns:
            Formatted string representation.
        """
        lines = ["## World State"]
        lines.append(f"Time: {self.time}")
        lines.append("")
        
        # Entities
        lines.append("### Entities")
        for eid, props in self.entities.items():
            status = "ALIVE" if props.get("is_active", True) else "DEAD"
            hp = props.get("hp", "??")
            pos = props.get("position", "?")
            lines.append(f"- {eid}: {status}, HP={hp}, Pos={pos}")
        lines.append("")
        
        # Relationships
        if self.relationships:
            lines.append("### Relationships")
            for (a, b), value in self.relationships.items():
                sentiment = "hostile" if value < -0.2 else "friendly" if value > 0.2 else "neutral"
                lines.append(f"- {a} ↔ {b}: {sentiment} ({value:.2f})")
            lines.append("")
            
        # Flags
        if self.flags:
            lines.append("### Flags")
            for key, value in self.flags.items():
                lines.append(f"- {key}: {value}")
            lines.append("")
            
        return "\n".join(lines)
        
    def to_short_summary(self) -> str:
        """Get a very short world summary for tight token budgets.
        
        Returns:
            Single line summary of world state.
        """
        active = sum(1 for p in self.entities.values() if p.get("is_active", True))
        hostile = sum(1 for v in self.relationships.values() if v < -0.3)
        return f"World T={self.time}: {active} active entities, {hostile} hostile pairs"
        
    # =========================================================
    # LIFECYCLE
    # =========================================================
    
    def advance_time(self, delta: int = 1) -> None:
        """Advance world time.
        
        Args:
            delta: Time increment (default 1 tick).
        """
        self.time += delta
        
    def reset(self) -> None:
        """Reset world state to empty."""
        self.entities.clear()
        self.relationships.clear()
        self.time = 0
        self.flags.clear()
        self.locations.clear()
        self.history.clear()
        self._active_entities.clear()
        
    @classmethod
    def from_session(cls, session) -> 'WorldState':
        """Create a WorldState from a game session.
        
        Extracts entity and relationship data from a session object.
        
        Args:
            session: Game session with NPCs and world data.
            
        Returns:
            Populated WorldState instance.
        """
        ws = cls()
        
        # Extract entities from NPCs
        if hasattr(session, 'npcs'):
            for npc in session.npcs:
                props = {
                    "hp": getattr(npc, 'hp', 100),
                    "max_hp": getattr(npc, 'max_hp', 100),
                    "position": getattr(npc, 'position', (0, 0)),
                    "is_active": getattr(npc, 'is_active', True),
                    "entity_type": "npc",
                }
                ws.add_entity(npc.id, props)
                
        # Extract player if present
        if hasattr(session, 'player'):
            player = session.player
            props = {
                "hp": getattr(player, 'hp', 100),
                "max_hp": getattr(player, 'max_hp', 100),
                "position": getattr(player, 'position', (0, 0)),
                "is_active": True,
                "entity_type": "player",
            }
            ws.add_entity("player", props)
            
        # Extract world time
        if hasattr(session, 'world'):
            ws.time = getattr(session.world, 'time', 0)
            
        # Extract flags
        if hasattr(session, 'world'):
            ws.flags["alert_level"] = getattr(session.world, 'alert_level', 0)
            ws.flags["size"] = getattr(session.world, 'size', (0, 0))
            
        return ws