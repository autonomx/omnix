"""Intent Engine for the Dynamic NPC Intent System.

This module provides the IntentEngine class that drives
the core NPC decision loop: goal generation, planning,
and action selection.

Tier 17.5 Patch: Adds belief-driven decisions, failure tracking,
and NPC-to-NPC interaction support.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .goal_generator import GoalGenerator
from .npc_actor import NPCActor, NPCGoal
from .planner import Planner
from .strategy_profiles import get_strategy_bias


# Action-to-belief mapping (Patch 3)
ACTION_BELIEF_EFFECTS: Dict[str, Dict[str, float]] = {
    "frame_player": {"player_trust": -0.2},
    "sabotage": {"player_trust": -0.1},
    "spread_rumors": {"player_trust": -0.15},
    "assist": {"player_trust": 0.2},
    "gift": {"player_trust": 0.3},
    "defend": {"player_trust": 0.1},
    "attack": {"player_fear": 0.2, "threat": 0.1},
    "fortify": {"player_fear": 0.05},
    "spy": {"player_trust": -0.05},
}


class IntentEngine:
    """Core intent loop for NPCs.

    The IntentEngine manages the full lifecycle of NPC intent:
    1. Generate goals based on world state
    2. Select highest priority goal
    3. Create action plan for the goal
    4. Return next action to execute

    Tier 17.5 Patch: Integrates belief updates from actions and
    failure tracking for adaptive behavior.

    Usage:
        engine = IntentEngine()
        action = engine.update_npc(npc, world_state, tick)
    """

    def __init__(self, goal_regeneration_interval: int = 5):
        """Initialize the IntentEngine.

        Args:
            goal_regeneration_interval: How often to regenerate goals.
        """
        self.goal_gen = GoalGenerator()
        self.planner = Planner()
        self.goal_regeneration_interval = goal_regeneration_interval
        # Track action history for belief updates
        self.action_history: Dict[str, List[Dict[str, Any]]] = {}

    def update_npc(
        self, npc: NPCActor, world: Dict[str, Any], tick: int,
        other_npcs: Optional[List[NPCActor]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update an NPC and return their next action.

        Tier 17.5 Patch: Supports stateful goals and failure tracking.

        Args:
            npc: NPC actor to update.
            world: World state dictionary.
            tick: Current game tick.
            other_npcs: Optional list of other NPCs for interaction (Patch 4).

        Returns:
            Action dict with npc_id, action, and goal, or None if no action.
        """
        # Generate goals if empty or outdated
        if self._should_regenerate_goals(npc, tick):
            raw_goals = self.goal_gen.generate(npc, world)
            # Merge stateful goals
            for goal_data in raw_goals:
                goal_type = goal_data.get("type")
                existing = next(
                    (g for g in npc.goals if g.type == goal_type and g.status == "active"),
                    None,
                )
                if existing:
                    existing.priority = max(existing.priority, goal_data.get("priority", 0))
                else:
                    npc.add_npc_goal(
                        NPCGoal(
                            id=goal_data.get("id", ""),
                            type=goal_type,
                            priority=goal_data.get("priority", 0.5),
                            created_tick=tick,
                        )
                    )

        # Pick highest priority goal (now includes stateful goals)
        goal = npc.select_highest_priority_goal()
        if not goal:
            return None

        # Check for failed goals and replan (Patch 2)
        active_goal = npc.select_best_active_goal()
        if active_goal and active_goal.failed_attempts > 0:
            goal["failed_attempts"] = active_goal.failed_attempts

        # Generate plan if none exists
        if not npc.current_plan:
            npc.current_plan = self.planner.create_plan(npc, goal, world)

        if not npc.current_plan:
            return None

        # Execute next action
        action = npc.current_plan.pop(0)
        npc.last_action_tick = tick

        # Patch 3: Update beliefs based on action
        self._update_beliefs_from_action(npc, action)

        # Patch 4: Process NPC vs NPC interactions
        if other_npcs:
            self._process_npc_interactions(npc, action, other_npcs)

        return {
            "npc_id": npc.id,
            "action": action,
            "goal": goal,
            "tick": tick,
        }

    def update_beliefs_from_action_result(
        self, npc: NPCActor, action: Dict[str, Any], success: bool
    ) -> None:
        """Update beliefs and track failure based on action result.

        Tier 17.5 Patch 2: Records failures for adaptation.

        Args:
            npc: NPC actor.
            action: The action that was executed.
            success: Whether the action succeeded.
        """
        if not success:
            action_type = action.get("type", "")
            goal = npc.select_best_active_goal()
            if goal:
                goal.record_failure()

            npc.record_failure(
                action,
                {
                    "tick": action.get("tick", 0),
                    "goal_type": goal.type if goal else "unknown",
                },
            )
        else:
            # Success - update progress
            goal = npc.select_best_active_goal()
            if goal:
                goal.update_progress(0.1)

    def _update_beliefs_from_action(
        self, npc: NPCActor, action: Dict[str, Any]
    ) -> None:
        """Update NPC beliefs based on action type.

        Tier 17.5 Patch 3: Actions modify belief model.

        Args:
            npc: NPC actor.
            action: Action dict.
        """
        action_type = action.get("type", "")
        effects = ACTION_BELIEF_EFFECTS.get(action_type, {})

        for belief_key, delta in effects.items():
            npc.update_belief(belief_key, delta)

    def _process_npc_interactions(
        self,
        npc: NPCActor,
        action: Dict[str, Any],
        other_npcs: List[NPCActor],
    ) -> None:
        """Process NPC vs NPC interactions.

        Tier 17.5 Patch 4: NPCs react to each other based on actions.

        Args:
            npc: Current NPC.
            action: Action being taken.
            other_npcs: Other NPCs in the world.
        """
        action_type = action.get("type", "")

        for other in other_npcs:
            if other.id == npc.id:
                continue

            # Faction-based reactions
            if action_type == "attack":
                if other.faction != npc.faction:
                    current_threat = other.get_belief("threat", 0.0)
                    other.update_belief("threat", 0.3)
                    # Update relationship
                    npc.update_relationship(other.id, -0.2)
                    other.update_relationship(npc.id, -0.3)
            elif action_type in ("spy", "sabotage", "spread_rumors"):
                # Cross-faction espionage and subversion is threatening
                if other.faction != npc.faction:
                    other.update_belief("threat", 0.15)
                    other.update_relationship(npc.id, -0.15)
                    npc.update_relationship(other.id, -0.1)
            elif action_type in ("assist", "ally", "gift"):
                if other.faction == npc.faction:
                    npc.update_relationship(other.id, 0.15)
                    other.update_relationship(npc.id, 0.2)
            elif action_type == "spy":
                # Other NPCs notice spying
                if other.get_belief("vigilance", 0.0) > 0.5:
                    other.update_belief("suspicion", 0.2)
                    other.update_relationship(npc.id, -0.15)

    def _should_regenerate_goals(self, npc: NPCActor, tick: int) -> bool:
        """Check if NPC should regenerate goals.

        Args:
            npc: NPC actor.
            tick: Current game tick.

        Returns:
            True if goals should be regenerated.
        """
        active_goals = [g for g in npc.goals if g.status == "active"]
        return (
            len(active_goals) == 0
            or (tick - npc.last_action_tick) >= self.goal_regeneration_interval
        )

    def update_all_npcs(
        self, npcs: List[NPCActor], world: Dict[str, Any], tick: int
    ) -> List[Dict[str, Any]]:
        """Update all NPCs and collect their actions.

        Tier 17.5 Patch: Passes all NPCs for interaction processing.

        Args:
            npcs: List of NPC actors.
            world: World state dictionary.
            tick: Current game tick.

        Returns:
            List of action dicts for all NPCs.
        """
        actions = []
        for npc in npcs:
            # Pass other NPCs for interaction (Patch 4)
            others = [n for n in npcs if n.id != npc.id]
            action = self.update_npc(npc, world, tick, other_npcs=others)
            if action is not None:
                actions.append(action)
        return actions

    def force_regeneration(self, npc: NPCActor, world: Dict[str, Any]) -> None:
        """Force goal regeneration for an NPC.

        Args:
            npc: NPC actor.
            world: World state dictionary.
        """
        npc.goals = self.goal_gen.generate(npc, world)

    def get_npc_intent_summary(
        self, npc: NPCActor
    ) -> Dict[str, Any]:
        """Get a summary of NPC's current intent.

        Args:
            npc: NPC actor.

        Returns:
            Dict with goal and plan summary.
        """
        from .npc_actor import NPCGoal

        # Count active goals from mixed types
        active_goal_count = 0
        for g in npc.goals:
            if isinstance(g, NPCGoal):
                if g.status == "active":
                    active_goal_count += 1
            elif isinstance(g, dict):
                active_goal_count += 1  # Dict goals are always active

        top_goal = npc.select_best_active_goal()

        return {
            "npc_id": npc.id,
            "npc_name": npc.name,
            "faction": npc.faction,
            "goal_count": active_goal_count,
            "top_goal": top_goal.to_dict() if top_goal else npc.select_highest_priority_goal(),
            "plan_length": len(npc.current_plan),
            "last_action_tick": npc.last_action_tick,
            "failure_count": len(npc.failure_memory),
            "relationships": dict(npc.relationships),
            "beliefs": dict(npc.beliefs),
        }

    def get_narrative_weight(
        self, action: Dict[str, Any], world: Dict[str, Any]
    ) -> float:
        """Calculate narrative significance of an action.

        Tier 17.5 Patch 5: Narrative significance scoring.

        Args:
            action: Action dict.
            world: World state.

        Returns:
            Narrative weight (0.0-1.0).
        """
        high_impact_actions = {"frame_player", "betray", "attack", "alliance"}
        medium_impact_actions = {"sabotage", "spy", "gift", "defend"}

        action_type = action.get("type", "")

        if action_type in high_impact_actions:
            return 1.0
        elif action_type in medium_impact_actions:
            return 0.6
        else:
            return 0.3

    def is_major_event(
        self, action: Dict[str, Any], world: Dict[str, Any]
    ) -> bool:
        """Check if an action qualifies as a major narrative event.

        Tier 17.5 Patch 5.

        Args:
            action: Action dict.
            world: World state.

        Returns:
            True if action is narratively significant.
        """
        return self.get_narrative_weight(action, world) > 0.8