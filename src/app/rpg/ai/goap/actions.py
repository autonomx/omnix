class Action:
    def __init__(self, name, cost, preconditions, effects):
        self.name = name
        self.cost = cost
        self.preconditions = preconditions  # dict
        self.effects = effects  # dict

    def is_applicable(self, state):
        for k, v in self.preconditions.items():
            if state.get(k) != v:
                return False
        return True

    def apply(self, state):
        new_state = dict(state)
        new_state.update(self.effects)
        return new_state


def build_memory_based_state(npc, context: dict = None) -> dict:
    """Build GOAP state dict from NPC's memories and relationships.
    
    This creates memory-based preconditions that make planning context-aware.
    
    Args:
        npc: The NPC to build state for
        context: Optional context dict to merge
        
    Returns:
        State dict with memory-derived values
    """
    state = context if context else {}
    
    # Default values
    state.setdefault("has_target", False)
    state.setdefault("enemy_visible", False)
    state.setdefault("target_in_range", False)
    state.setdefault("low_hp", npc.hp < 30 if hasattr(npc, 'hp') else False)
    state.setdefault("safe", True)
    state.setdefault("has_hostile_memory", False)
    state.setdefault("has_ally", False)
    state.setdefault("has_healer_nearby", False)
    
    # Memory-based preconditions
    memories = npc.memory.get("events", []) if isinstance(npc.memory, dict) else []
    relationships = npc.memory.get("relationships", {}) if isinstance(npc.memory, dict) else {}
    
    # Check for hostile memories (anyone with anger > 0.5 or damage events)
    hostile_targets = []
    for target_id, rel in relationships.items():
        if rel.get("anger", 0) > 0.5:
            hostile_targets.append(target_id)
    
    # Also check for damage event patterns
    damage_sources = set()
    for mem in memories:
        if mem.get("type") == "damage" and mem.get("target") == npc.id:
            damage_sources.add(mem.get("source", mem.get("actor", "")))
    
    hostile_targets.extend(list(damage_sources))
    hostile_targets = list(set(hostile_targets))
    
    if hostile_targets:
        state["has_hostile_memory"] = True
        state["hostile_targets"] = hostile_targets
    
    # Check for ally relationships (trust > 0.5)
    allies = []
    for target_id, rel in relationships.items():
        if rel.get("trust", 0) > 0.5:
            allies.append(target_id)
    
    if allies:
        state["has_ally"] = True
        state["allies"] = allies
    
    # Check for healing memories (potential healer allies)
    heal_sources = set()
    for mem in memories:
        if mem.get("type") == "heal" and mem.get("target") == npc.id:
            heal_sources.add(mem.get("source", mem.get("actor", "")))
    
    if heal_sources:
        state["has_healer_nearby"] = True
        state["healers"] = list(heal_sources)
    
    return state


def move_to_target(npc, target):
    """Move NPC toward target using directional movement.
    
    Computes the direction vector and moves one step toward target.
    Uses Euclidean movement for smooth positioning.
    
    Args:
        npc: The NPC to move.
        target: The target entity to move toward.
        
    Returns:
        Event dict representing the move action, or None if already at target.
    """
    tx, ty = target.position
    x, y = npc.position
    
    dx = tx - x
    dy = ty - y
    
    step = 1.0
    dist = max(0.001, (dx**2 + dy**2) ** 0.5)
    
    # Already at target (within step distance)
    if dist <= step:
        return None
    
    # Move one step toward target
    npc.position = (
        x + (dx / dist) * step,
        y + (dy / dist) * step
    )
    
    return {
        "type": "move",
        "source": npc.id,
        "target": target.id,
        "position": npc.position,
    }


def default_actions():
    """Return default GOAP actions for NPCs.
    
    Returns:
        List of Action objects representing available NPC actions.
    """
    return [
        Action(
            "attack",
            cost=2,
            preconditions={"enemy_visible": True, "target_in_range": True},
            effects={"enemy_hp": "reduced"}
        ),
        Action(
            "move_to_target",
            cost=1,
            preconditions={"has_target": True, "target_in_range": False},
            effects={"target_in_range": True}
        ),
        Action(
            "flee",
            cost=1,
            preconditions={"low_hp": True},
            effects={"safe": True}
        ),
        Action(
            "approach",
            cost=1,
            preconditions={"enemy_visible": False, "has_target": True},
            effects={"enemy_visible": True}
        ),
        Action(
            "idle",
            cost=3,
            preconditions={},
            effects={}
        )
    ]
