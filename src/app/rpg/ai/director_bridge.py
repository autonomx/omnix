"""Director Bridge — Connects Story Director output to NPC GOAP goals.

This module implements PATCH 2 from the RPG design specification:
"CONNECT DIRECTOR → NPC GOAP"

The problem: GOAP runs independently without considering story direction.
The solution: Inject goals from the Story Director before GOAP planning.

Usage:
    apply_director_to_npcs(session, director_output)

This modifies NPC goal state in place before the planning phase.
"""

from typing import Any, Dict, List, Optional


def apply_director_to_npcs(session, director_output) -> List[str]:
    """Apply Story Director goal updates to NPCs.
    
    This function takes the structured output from the Story Director
    and injects the NPC goal updates directly into the relevant NPCs.
    This happens BEFORE GOAP planning so the planner considers these goals.
    
    Args:
        session: The current game session with NPCs.
        director_output: DirectorOutput instance with goal updates.
        
    Returns:
        List of NPC IDs that were updated.
    """
    updated_npcs = []
    
    for npc_id, goals in director_output.npc_goal_updates.items():
        npc = session.npcs.get(npc_id) if hasattr(session.npcs, 'get') else None
        
        # Fallback: search by attribute for list-based NPC collections
        if npc is None:
            npc = next((n for n in session.npcs if getattr(n, 'id', None) == npc_id), None)
            
        if npc is None:
            continue
        
        # Apply goals to NPC - use a 'goals' attribute for director-injected goals
        # This is separate from the NPC's internal state to allow clear separation
        if not hasattr(npc, 'director_goals'):
            npc.director_goals = []
        
        # Overwrite or merge goals based on design spec
        # The design says "Overwrite or merge goals" - we use overwrite for simplicity
        npc.director_goals = goals
        updated_npcs.append(npc_id)
        
    return updated_npcs


def get_npc_goals(npc) -> List[Dict[str, Any]]:
    """Get the effective goals for an NPC, including director-injected goals.
    
    This helper retrieves goals in priority order:
    1. Director-injected goals (highest priority)
    2. NPC's own goals (from memory, emotions, etc.)
    
    Args:
        npc: The NPC to get goals for.
        
    Returns:
        List of goal dicts in priority order.
    """
    goals = []
    
    # Director goals have highest priority
    if hasattr(npc, 'director_goals') and npc.director_goals:
        goals.extend(npc.director_goals)
        
    # Add NPC's own goals if present
    if hasattr(npc, 'goals') and npc.goals:
        goals.extend(npc.goals)
        
    return goals


def clear_director_goals(session) -> None:
    """Clear all director-injected goals from NPCs.
    
    This should be called at the END of each turn to prevent
    goal accumulation across turns. Director goals are per-turn
    directives, not permanent state.
    
    Args:
        session: The current game session.
    """
    npcs = session.npcs.values() if hasattr(session.npcs, 'values') else session.npcs
    
    for npc in npcs:
        if hasattr(npc, 'director_goals'):
            npc.director_goals = []