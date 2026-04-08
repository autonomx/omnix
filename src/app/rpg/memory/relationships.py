"""Relationship Memory System - Persistent relationship state between NPCs.

This system tracks:
- Trust, fear, anger levels between entity pairs
- Relationship updates from events (damage, heal, dialogue, etc.)
- Long-term relationship effects on GOAP goals (grudges, alliances, betrayals)

Architecture:
    event → relationship update → GOAP goal influence → persistent behavior

Example:
    if relationship["anger"] > 0.7:
        goal = "attack_target"  # Grudge-driven behavior
"""

from typing import Any, Dict, List, Optional

# Default relationship attribute ranges (0.0 to 1.0)
RELATIONSHIP_ATTRIBUTES = ["trust", "fear", "anger", "affection", "respect"]
DEFAULT_DECAY_RATE = 0.95  # Per-tick decay factor


def _init_relationship() -> Dict[str, float]:
    """Create a new relationship state with default values."""
    return {
        "trust": 0.3,      # Neutral starting point - not hostile, not trusting
        "fear": 0.0,
        "anger": 0.0,
        "affection": 0.0,
        "respect": 0.3,    # Neutral respect for unknown entities
        "last_update": 0,  # Tick of last update
    }


def get_relationship(npc, target_id: str) -> Dict[str, float]:
    """Get the relationship state between an NPC and target.
    
    Args:
        npc: The NPC whose relationships to access
        target_id: The target entity ID
        
    Returns:
        Dict with relationship attributes (trust, fear, anger, etc.)
    """
    # Check npc.relationships shortcut first (NPC model stores there)
    if hasattr(npc, 'relationships') and target_id in npc.relationships:
        return npc.relationships[target_id]
    
    # Fall back to npc.memory["relationships"]
    if isinstance(npc.memory, dict):
        rels = npc.memory.get("relationships", {})
    else:
        rels = {}
    
    if target_id not in rels:
        rels[target_id] = _init_relationship()
        if isinstance(npc.memory, dict):
            npc.memory["relationships"] = rels
    
    return rels[target_id]


def update_relationship_from_event(npc, event: Dict[str, Any], current_time: int = 0):
    """Update relationship attributes based on an event.
    
    Event-driven relationship updates ensure grudges, trust, and fear
    persist and evolve based on experiences.
    
    Args:
        npc: The NPC whose relationship to update
        event: The event that occurred
        current_time: Current world time
    """
    event_type = event.get("type", "")
    source = event.get("source", event.get("actor", ""))
    target = event.get("target", "")
    amount = event.get("amount", 0)
    
    # Determine which relationship to update (NPC's perspective)
    if npc.id == target:
        # NPC was the target - update relationship with source
        if source:
            rel = get_relationship(npc, source)
            _apply_event_to_relationship(rel, event_type, amount, source, current_time)
    elif npc.id == source:
        # NPC was the source - update relationship with target
        if target:
            rel = get_relationship(npc, target)
            _apply_source_event_to_relationship(rel, event_type, amount, target, current_time)
    
    # Decay all relationships for this NPC
    decay_relationships(npc, current_time)


def _apply_event_to_relationship(
    rel: Dict[str, float],
    event_type: str,
    amount: float,
    other_entity: str,
    current_time: int,
):
    """Apply event effects to relationship where NPC is the recipient."""
    rel["last_update"] = current_time
    
    if event_type == "damage":
        # Being attacked increases anger and fear, decreases trust
        intensity = min(1.0, amount / 20.0)  # Scale by damage amount
        rel["anger"] = min(1.0, rel["anger"] + 0.3 * (1 + intensity))
        rel["trust"] = max(-1.0, rel["trust"] - 0.2 * (1 + intensity))
        rel["fear"] = min(1.0, rel["fear"] + 0.15 * intensity)
        
    elif event_type == "death":
        # Death of ally increases anger at killer and grief
        rel["anger"] = min(1.0, rel["anger"] + 0.5)
        rel["trust"] = max(-1.0, rel["trust"] - 0.4)
        rel["fear"] = min(1.0, rel["fear"] + 0.3)
        
    elif event_type == "heal":
        # Being healed increases trust and affection
        intensity = min(1.0, amount / 30.0)
        rel["trust"] = min(1.0, rel["trust"] + 0.25 * (1 + intensity))
        rel["affection"] = min(1.0, rel["affection"] + 0.2 * (1 + intensity))
        rel["respect"] = min(1.0, rel["respect"] + 0.1 * (1 + intensity))
        
    elif event_type == "dialogue":
        # Dialogue can increase trust slightly based on context
        rel["trust"] = min(1.0, rel["trust"] + 0.05)
        rel["respect"] = min(1.0, rel["respect"] + 0.03)
        
    elif event_type == "betrayal":
        # Betrayal massively damages trust
        rel["trust"] = max(-1.0, rel["trust"] - 0.8)
        rel["anger"] = min(1.0, rel["anger"] + 0.6)
        rel["fear"] = min(1.0, rel["fear"] + 0.3)
        
    elif event_type == "alliance":
        # Alliance formation increases trust and affection
        rel["trust"] = min(1.0, rel["trust"] + 0.4)
        rel["affection"] = min(1.0, rel["affection"] + 0.3)
        rel["respect"] = min(1.0, rel["respect"] + 0.2)


def _apply_source_event_to_relationship(
    rel: Dict[str, float],
    event_type: str,
    amount: float,
    other_entity: str,
    current_time: int,
):
    """Apply event effects to relationship where NPC is the source (actor).
    
    When NPC attacks someone, their relationship changes differently
    than when they are attacked.
    """
    rel["last_update"] = current_time
    
    if event_type == "damage":
        # Attacking someone decreases trust and respect
        rel["trust"] = max(-1.0, rel["trust"] - 0.1)
        rel["respect"] = max(-1.0, rel["respect"] - 0.05)
        # May increase fear if target is strong
        rel["fear"] = min(1.0, rel["fear"] + 0.05)
        
    elif event_type == "heal":
        # Healing someone increases trust and affection
        rel["trust"] = min(1.0, rel["trust"] + 0.15)
        rel["affection"] = min(1.0, rel["affection"] + 0.1)
        
    elif event_type == "dialogue":
        # Talking increases trust slightly
        rel["trust"] = min(1.0, rel["trust"] + 0.03)


def decay_relationships(npc, current_time: int, stale_threshold: int = 10):
    """Decay all relationships that haven't been updated recently.
    
    Relationships naturally decay toward neutrality over time unless
    reinforced by new events.
    
    Args:
        npc: The NPC whose relationships to decay
        current_time: Current world time
        stale_threshold: Ticks without update before decay begins
    """
    # Get all relationship targets
    targets = []
    if hasattr(npc, 'relationships'):
        targets = list(npc.relationships.keys())
    elif isinstance(npc.memory, dict):
        targets = list(npc.memory.get("relationships", {}).keys())
    
    for target_id in targets:
        rel = get_relationship(npc, target_id)
        
        # Only decay if relationship hasn't been updated recently
        last_update = rel.get("last_update", 0)
        if current_time - last_update < stale_threshold:
            continue
        
        # Decay toward neutral values
        for attr in RELATIONSHIP_ATTRIBUTES:
            if attr == "last_update":
                continue
            current = rel.get(attr, 0.0)
            neutral = 0.3 if attr in ("trust", "respect") else 0.0
            rel[attr] = current * DEFAULT_DECAY_RATE + neutral * (1 - DEFAULT_DECAY_RATE)


def get_relationship_goal_override(
    npc,
    target_id: str,
    current_time: int = 0,
) -> Optional[Dict[str, Any]]:
    """Check if relationship state should override normal GOAP goals.
    
    This is what creates persistent grudges, alliances, and betrayals.
    
    Args:
        npc: The NPC to check
        target_id: The target entity to evaluate relationship with
        current_time: Current world time
        
    Returns:
        Dict with forced goal if relationship warrants it, or None
    """
    rel = get_relationship(npc, target_id)
    
    # Grudge-based attack urge
    if rel.get("anger", 0) > 0.7:
        return {
            "type": "attack_target",
            "target": target_id,
            "reason": "grudge",
            "force": rel["anger"] * 0.8,
        }
    
    # Fear-based avoidance
    if rel.get("fear", 0) > 0.7:
        return {
            "type": "flee_target",
            "target": target_id,
            "reason": "fear",
            "force": rel["fear"] * 0.6,
        }
    
    # Trust-based alliance support
    if rel.get("trust", 0) > 0.7 and rel.get("affection", 0) > 0.5:
        return {
            "type": "protect_target",
            "target": target_id,
            "reason": "alliance",
            "force": rel["trust"] * 0.5,
        }
    
    # Extreme distrust - avoid interaction
    if rel.get("trust", 0) < -0.7:
        return {
            "type": "avoid_target",
            "target": target_id,
            "reason": "distrust",
            "force": abs(rel["trust"]) * 0.4,
        }
    
    return None


def get_relationship_summary(npc, target_id: str) -> str:
    """Get human-readable relationship summary for grounding.
    
    Args:
        npc: The NPC
        target_id: The target entity
        
    Returns:
        String summarizing the relationship state
    """
    rel = get_relationship(npc, target_id)
    
    # Determine relationship labels
    trust_label = "trusting" if rel.get("trust", 0) > 0.5 else ("distrustful" if rel.get("trust", 0) < -0.3 else "neutral")
    anger_label = "angry" if rel.get("anger", 0) > 0.5 else ("calm" if rel.get("anger", 0) < 0.3 else "tense")
    fear_label = "afraid" if rel.get("fear", 0) > 0.5 else ("brave" if rel.get("fear", 0) < 0.3 else "wary")
    
    return f"{trust_label}, {anger_label}, {fear_label} toward {target_id}"


def get_all_relationship_summaries(npc) -> List[Dict[str, Any]]:
    """Get summaries of all relationships for grounding block.
    
    Args:
        npc: The NPC
        
    Returns:
        List of dicts with target_id and relationship summary
    """
    summaries = []
    
    # Collect all relationship targets
    targets = set()
    if hasattr(npc, 'relationships'):
        targets.update(npc.relationships.keys())
    if isinstance(npc.memory, dict):
        targets.update(npc.memory.get("relationships", {}).keys())
    
    for target_id in targets:
        summaries.append({
            "entity": npc.id,
            "target": target_id,
            "summary": get_relationship_summary(npc, target_id),
            "trust": get_relationship(npc, target_id).get("trust", 0),
            "anger": get_relationship(npc, target_id).get("anger", 0),
            "fear": get_relationship(npc, target_id).get("fear", 0),
        })
    
    return summaries