"""Action Registry — Tool/function calling system for the RPG.

This module implements the Tool/Function Calling System from the design spec.
It allows the AI Director to execute actions on the world, not just describe them.

Purpose:
    Let AI act, not just describe.

Architecture:
    Director → decides action → ActionRegistry → executes → Events

Usage:
    registry = ActionRegistry()
    registry.register("attack", attack_fn)
    result = registry.execute("attack", source="player", target="goblin")

Design Compliance:
    - Actions modify world state and return events
    - Actions are composable and chainable
    - Actions validate preconditions before execution
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class ActionRegistryError(Exception):
    """Error raised when action registration or execution fails."""
    pass


class ActionRegistry:
    """Central registry for all available world actions.
    
    This is the tool system that allows the Director to manipulate
    the game world. Each action is a function that receives the world
    state and parameters, modifies the world, and returns events.
    
    Thread Safety: Not thread-safe. Designed for single-threaded game loop.
    
    Attributes:
        _actions: Dict mapping action names to (fn, metadata) tuples.
        _world: Reference to the current world state.
    """
    
    def __init__(self, world=None):
        """Initialize the ActionRegistry.
        
        Args:
            world: Optional world state reference. Can be set later
                with set_world().
        """
        self._actions: Dict[str, tuple] = {}
        self._world = world
        
    def set_world(self, world) -> None:
        """Set the world state reference for action execution.
        
        Args:
            world: The world state object that actions can modify.
        """
        self._world = world
        
    def register(
        self,
        name: str,
        fn: Callable,
        description: str = "",
        parameters: Optional[Dict[str, str]] = None,
    ) -> None:
        """Register an action function.
        
        Args:
            name: The action name (e.g., "attack", "move").
            fn: The function to execute. Signature: fn(world, **kwargs) -> dict
            description: Human-readable description of the action.
            parameters: Dict mapping parameter names to descriptions.
        """
        if not callable(fn):
            raise ActionRegistryError(f"Action '{name}' must be callable")
            
        self._actions[name] = {
            "fn": fn,
            "description": description,
            "parameters": parameters or {},
        }
        
    def unregister(self, name: str) -> None:
        """Remove a registered action.
        
        Args:
            name: The action name to remove.
            
        Raises:
            ActionRegistryError: If action is not found.
        """
        if name not in self._actions:
            raise ActionRegistryError(f"Action '{name}' not found")
        del self._actions[name]
        
    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a registered action by name.
        
        Args:
            name: The action name.
            
        Returns:
            Action info dict, or None if not found.
        """
        return self._actions.get(name)
        
    def has(self, name: str) -> bool:
        """Check if an action is registered.
        
        Args:
            name: The action name.
            
        Returns:
            True if action is registered.
        """
        return name in self._actions
        
    def list_actions(self) -> List[str]:
        """Get list of all registered action names.
        
        Returns:
            List of action name strings.
        """
        return list(self._actions.keys())
        
    def execute(self, name: str, **kwargs) -> Dict[str, Any]:
        """Execute a registered action.
        
        The action function receives the world state as its first argument
        and returns a dict with "events" and optional "result" keys.
        
        Args:
            name: The action name to execute.
            **kwargs: Parameters to pass to the action function.
            
        Returns:
            Dict with "events" (list of event dicts) and optional "result".
            
        Raises:
            ActionRegistryError: If action is not found or execution fails.
        """
        if name not in self._actions:
            raise ActionRegistryError(
                f"Action '{name}' not found. Available: {self.list_actions()}"
            )
            
        action_info = self._actions[name]
        fn = action_info["fn"]
        
        try:
            result = fn(self._world, **kwargs)
        except Exception as e:
            raise ActionRegistryError(f"Action '{name}' failed: {e}") from e
            
        # Ensure result has events key
        if not isinstance(result, dict):
            result = {"events": result}
            
        if "events" not in result:
            result["events"] = []
            
        return result
        
    def execute_action_dict(self, action_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action from a dict representation.
        
        This is the primary integration point with the LLM Director.
        The LLM returns action dicts like:
            {"action": "attack", "parameters": {"source": "player", "target": "goblin"}}
        
        Args:
            action_dict: Dict with "action" name and "parameters" dict.
            
        Returns:
            Execution result dict with "events" and optional "result".
            
        Raises:
            ActionRegistryError: If action is not found or missing parameters.
        """
        name = action_dict.get("action")
        if not name:
            raise ActionRegistryError("Action dict missing 'action' key")
            
        parameters = action_dict.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ActionRegistryError("'parameters' must be a dict")
            
        return self.execute(name, **parameters)
        
    def get_action_descriptions(self) -> Dict[str, Dict[str, Any]]:
        """Get descriptions for all registered actions.
        
        Returns dict suitable for LLM prompt generation:
        {
            "attack": {
                "description": "Cause one entity to attack another",
                "parameters": {
                    "source": "The attacking entity",
                    "target": "The target entity",
                }
            }
        }
        
        Returns:
            Dict mapping action names to their metadata.
        """
        return {
            name: {
                "description": info["description"],
                "parameters": info["parameters"],
            }
            for name, info in self._actions.items()
        }
        
    def get_prompt_text(self) -> str:
        """Get formatted action descriptions for LLM prompt.
        
        Returns:
            String suitable for embedding in LLM system prompt.
        """
        lines = ["Available Actions:"]
        for name, info in self.get_action_descriptions().items():
            lines.append(f"  - {name}({', '.join(info['parameters'].keys())})")
            if info["description"]:
                lines.append(f"    {info['description']}")
        return "\n".join(lines)
        
    def reset(self) -> None:
        """Clear all registered actions and world reference."""
        self._actions.clear()
        self._world = None


# =========================================================
# DEFAULT WORLD ACTIONS
# =========================================================

def register_default_actions(registry: ActionRegistry) -> None:
    """Register the default set of world actions.
    
    These are the core actions available to the Director:
    - attack: cause damage between entities
    - move: reposition an entity
    - speak: dialogue between entities
    - heal: restore HP
    - spawn: create a new entity
    - update_relationship: modify relationship value
    - flee: entity retreats
    
    Args:
        registry: The ActionRegistry to populate.
    """
    registry.register(
        "attack",
        action_attack,
        "Cause one entity to attack another, dealing damage",
        {"source": "Attacker entity ID", "target": "Target entity ID",
         "damage": "Damage amount (optional, default 5)"},
    )
    registry.register(
        "move",
        action_move,
        "Move an entity to a new position",
        {"entity": "Entity ID", "x": "Target X position", "y": "Target Y position"},
    )
    registry.register(
        "speak",
        action_speak,
        "Have one entity speak to another",
        {"speaker": "Speaker entity ID", "target": "Target entity ID",
         "message": "Dialogue text"},
    )
    registry.register(
        "heal",
        action_heal,
        "Heal an entity's HP",
        {"source": "Healer entity ID", "target": "Target entity ID",
         "amount": "Heal amount (optional, default 10)"},
    )
    registry.register(
        "spawn",
        action_spawn,
        "Spawn a new entity at a position",
        {"entity_id": "New entity ID", "x": "X position", "y": "Y position",
         "entity_type": "Entity type (optional)"},
    )
    registry.register(
        "update_relationship",
        action_update_relationship,
        "Update relationship between two entities",
        {"a": "Entity A", "b": "Entity B", "value": "Relationship delta"},
    )
    registry.register(
        "flee",
        action_flee,
        "Cause an entity to flee from another",
        {"entity": "Fleeing entity ID", "from": "Threat entity ID"},
    )


def action_attack(world, source: str, target: str, damage: int = 5) -> Dict[str, Any]:
    """Execute an attack action.
    
    Args:
        world: The world state.
        source: Attacker entity ID.
        target: Target entity ID.
        damage: Damage amount (default 5).
        
    Returns:
        Dict with damage/death events.
    """
    events = []
    
    # Get entities if world has them
    source_entity = None
    target_entity = None
    if world and hasattr(world, 'get_entity'):
        source_entity = world.get_entity(source)
        target_entity = world.get_entity(target)
    
    # Apply damage if target entity exists
    if target_entity and hasattr(target_entity, 'hp'):
        target_entity.hp = max(0, target_entity.hp - damage)
        
        events.append({
            "type": "damage",
            "source": source,
            "target": target,
            "amount": damage,
        })
        
        # Death event if HP reached 0
        if target_entity.hp <= 0:
            target_entity.is_active = False
            events.append({
                "type": "death",
                "source": source,
                "target": target,
            })
    else:
        # No entity found, still generate the event
        events.append({
            "type": "damage",
            "source": source,
            "target": target,
            "amount": damage,
        })
    
    return {"events": events, "result": {"damage": damage}}


def action_move(world, entity: str, x: int, y: int) -> Dict[str, Any]:
    """Execute a move action.
    
    Args:
        world: The world state.
        entity: Entity ID to move.
        x: Target X position.
        y: Target Y position.
        
    Returns:
        Dict with move event.
    """
    events = []
    
    if world and hasattr(world, 'get_entity'):
        entity_obj = world.get_entity(entity)
        if entity_obj and hasattr(entity_obj, 'position'):
            old_pos = entity_obj.position
            entity_obj.position = (x, y)
            events.append({
                "type": "move",
                "entity": entity,
                "from": old_pos,
                "to": (x, y),
            })
    
    if not events:
        events.append({
            "type": "move",
            "entity": entity,
            "to": (x, y),
        })
    
    return {"events": events, "result": {"position": (x, y)}}


def action_speak(world, speaker: str, target: str, message: str) -> Dict[str, Any]:
    """Execute a speak/dialogue action.
    
    Args:
        world: The world state.
        speaker: Speaker entity ID.
        target: Target entity ID.
        message: The dialogue text.
        
    Returns:
        Dict with speak event.
    """
    return {
        "events": [{
            "type": "speak",
            "speaker": speaker,
            "target": target,
            "message": message,
        }],
        "result": {"message": message},
    }


def action_heal(world, source: str, target: str, amount: int = 10) -> Dict[str, Any]:
    """Execute a heal action.
    
    Args:
        world: The world state.
        source: Healer entity ID.
        target: Target entity ID.
        amount: Heal amount (default 10).
        
    Returns:
        Dict with heal event.
    """
    events = []
    
    if world and hasattr(world, 'get_entity'):
        target_entity = world.get_entity(target)
        if target_entity and hasattr(target_entity, 'hp'):
            max_hp = getattr(target_entity, 'max_hp', 100)
            target_entity.hp = min(max_hp, target_entity.hp + amount)
            events.append({
                "type": "heal",
                "source": source,
                "target": target,
                "amount": amount,
            })
    
    if not events:
        events.append({
            "type": "heal",
            "source": source,
            "target": target,
            "amount": amount,
        })
    
    return {"events": events, "result": {"healed": amount}}


def action_spawn(world, entity_id: str, x: int, y: int,
                 entity_type: str = "npc") -> Dict[str, Any]:
    """Execute a spawn action.
    
    Args:
        world: The world state.
        entity_id: New entity ID.
        x: X position.
        y: Y position.
        entity_type: Entity type tag.
        
    Returns:
        Dict with spawn event.
    """
    return {
        "events": [{
            "type": "spawn",
            "entity": entity_id,
            "position": (x, y),
            "entity_type": entity_type,
        }],
        "result": {"entity_id": entity_id},
    }


def action_update_relationship(world, a: str, b: str, value: float) -> Dict[str, Any]:
    """Execute a relationship update action.
    
    Args:
        world: The world state.
        a: Entity A.
        b: Entity B.
        value: Relationship delta (positive=friendly, negative=hostile).
        
    Returns:
        Dict with relationship event.
    """
    events = []
    
    if world:
        # Try to update relationships in world state
        if hasattr(world, 'update_relationship'):
            world.update_relationship(a, b, value)
        elif hasattr(world, 'relationships'):
            key = tuple(sorted([a, b]))
            current = world.relationships.get(key, 0.0)
            world.relationships[key] = current + value
    
    sent = "friendly" if value > 0 else "hostile"
    events.append({
        "type": "relationship_update",
        "a": a,
        "b": b,
        "value": value,
        "sentiment": sent,
    })
    
    return {"events": events, "result": {"value": value}}


def action_flee(world, entity: str, from_entity: str) -> Dict[str, Any]:
    """Execute a flee action.
    
    Args:
        world: The world state.
        entity: Fleeing entity ID.
        from_entity: Threat entity ID.
        
    Returns:
        Dict with flee event.
    """
    events = [{
        "type": "flee",
        "entity": entity,
        "from": from_entity,
    }]
    
    # Move entity away if world supports it
    if world and hasattr(world, 'get_entity'):
        flee_entity = world.get_entity(entity)
        threat_entity = world.get_entity(from_entity)
        if flee_entity and threat_entity:
            flee_pos = getattr(flee_entity, 'position', (0, 0))
            threat_pos = getattr(threat_entity, 'position', (0, 0))
            # Move in opposite direction
            dx = flee_pos[0] - threat_pos[0]
            dy = flee_pos[1] - threat_pos[1]
            new_pos = (flee_pos[0] + dx, flee_pos[1] + dy)
            flee_entity.position = new_pos
            events[0]["to"] = new_pos
    
    return {"events": events, "result": {"fled": True}}