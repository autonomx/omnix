"""Goal Generator for the Dynamic NPC Intent System.

This module provides the GoalGenerator class that creates
goals for NPCs based on world state and faction dynamics.

Tier 17.5 Patch: Adds belief-driven goal generation and
goal merging with existing stateful goals.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from .npc_actor import NPCActor, NPCGoal


class GoalGenerator:
    """Generates goals for NPCs based on world state.

    The GoalGenerator evaluates world conditions including
    faction power, player reputation, and NPC traits to
    generate relevant goals for autonomous behavior.

    Tier 17.5 Patch: Goals now merge with existing stateful goals
    and use belief-driven decision making.

    Usage:
        generator = GoalGenerator()
        goals = generator.generate(npc, world_state)
    """

    def generate(self, npc: NPCActor, world: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate goals for an NPC based on world state.

        Args:
            npc: NPC actor to generate goals for.
            world: World state dictionary.

        Returns:
            List of goal dicts with 'type' and 'priority' keys.
        """
        goals: List[Dict[str, Any]] = []

        # React to faction power imbalance
        self._evaluate_faction_power(npc, world, goals)

        # React to player reputation (belief-driven, Patch 3)
        self._evaluate_player_reputation(npc, world, goals)

        # React to world tension
        self._evaluate_world_tension(npc, world, goals)

        # React to NPC traits
        self._evaluate_traits(npc, world, goals)

        # Merge with existing goals
        merged = self._merge_with_existing(npc, goals)

        return merged

    def _merge_with_existing(
        self, npc: NPCActor, new_goals: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge new goals with existing stateful goals.

        Tier 17.5 Patch 1: Prevents goal duplication and
        maintains goal state across regeneration.

        Args:
            npc: NPC actor with existing goals.
            new_goals: Newly generated goals.

        Returns:
            Merged list of goal dicts.
        """
        from .npc_actor import NPCGoal

        merged: List[Dict[str, Any]] = []

        # Get existing active goal types (handle both NPCGoal and dict types)
        existing_types: Dict[str, Any] = {}
        for g in npc.goals:
            if isinstance(g, NPCGoal):
                if g.status == "active":
                    existing_types[g.type] = g
            elif isinstance(g, dict):
                goal_type = g.get("type")
                if goal_type:
                    existing_types[goal_type] = g

        for new_goal in new_goals:
            goal_type = new_goal.get("type")
            if goal_type in existing_types:
                existing = existing_types[goal_type]
                if isinstance(existing, NPCGoal):
                    # Keep highest priority
                    existing.priority = max(existing.priority, new_goal.get("priority", 0))
                    merged.append(existing.to_dict())
                else:
                    # Dict-based goal - update priority
                    existing["priority"] = max(existing.get("priority", 0), new_goal.get("priority", 0))
                    merged.append(dict(existing))
            else:
                goal_copy = dict(new_goal)
                goal_copy["id"] = str(uuid.uuid4())
                merged.append(goal_copy)

        # Include existing goals that weren't regenerated but still active
        for goal in npc.goals:
            if isinstance(goal, NPCGoal):
                if goal.status == "active" and goal.type not in [g["type"] for g in merged]:
                    # Keep long-term goals active if they haven't failed
                    if goal.failed_attempts < 3:
                        merged.append(goal.to_dict())
            elif isinstance(goal, dict):
                goal_type = goal.get("type")
                if goal_type and goal_type not in [g["type"] for g in merged]:
                    merged.append(dict(goal))

        return merged

    def generate_npc_goals(
        self, npc: NPCActor, world: Dict[str, Any], tick: int = 0
    ) -> List[NPCGoal]:
        """Generate stateful NPCGoal objects.

        Tier 17.5 Patch: Creates persistent goals with identity.

        Args:
            npc: NPC actor.
            world: World state.
            tick: Current game tick.

        Returns:
            List of NPCGoal objects.
        """
        raw_goals = self.generate(npc, world)
        npc_goals = []

        for goal_data in raw_goals:
            goal_type = goal_data.get("type")
            existing = next(
                (g for g in npc.goals if g.type == goal_type and g.status == "active"),
                None,
            )

            if existing:
                # Update existing goal
                existing.priority = max(
                    existing.priority, goal_data.get("priority", 0)
                )
                npc_goals.append(existing)
            else:
                # Create new stateful goal
                goal = NPCGoal(
                    id=goal_data.get("id", str(uuid.uuid4())),
                    type=goal_type,
                    priority=goal_data.get("priority", 0.5),
                    created_tick=tick,
                    target=goal_data.get("target"),
                    metadata={
                        k: v for k, v in goal_data.items()
                        if k not in ("type", "priority", "id", "target")
                    },
                )
                npc_goals.append(goal)

        return npc_goals

    def _evaluate_faction_power(
        self, npc: NPCActor, world: Dict[str, Any], goals: List[Dict[str, Any]]
    ) -> None:
        """Evaluate faction power and generate power-related goals.

        Args:
            npc: NPC actor.
            world: World state.
            goals: Goals list to append to.
        """
        factions = world.get("factions", {})
        my_power: float = factions.get(npc.faction, {}).get("power", 1.0)

        if my_power < 0.8:
            goals.append({
                "type": "recover_power",
                "priority": 0.8 - my_power * 0.3,
                "target_faction": npc.faction,
            })
        elif my_power > 0.9:
            goals.append({
                "type": "maintain_dominance",
                "priority": 0.4,
                "target_faction": npc.faction,
            })

    def _evaluate_player_reputation(
        self, npc: NPCActor, world: Dict[str, Any], goals: List[Dict[str, Any]]
    ) -> None:
        """Evaluate player reputation and generate player-related goals.

        Tier 17.5 Patch 3: Uses belief-driven decision making.
        Trust and fear from beliefs override reputation.

        Args:
            npc: NPC actor.
            world: World state.
            goals: Goals list to append to.
        """
        # Patch 3: Use belief model instead of raw reputation
        trust = npc.get_belief("player_trust", 0.0)
        fear = npc.get_belief("player_fear", 0.0)

        if trust > 0.5:
            goals.append({
                "type": "ally_player",
                "priority": trust * 0.8,
            })
        elif trust < -0.3 or fear > 0.5:
            goals.append({
                "type": "undermine_player",
                "priority": 0.7 + fear * 0.3,
            })
        else:
            # Also check world reputation as fallback
            player_rep: float = world.get("player_reputation", 0.0)
            if player_rep > 0.5:
                goals.append({
                    "type": "ally_player",
                    "priority": player_rep * 0.8,
                })
            elif player_rep < -0.3:
                goals.append({
                    "type": "undermine_player",
                    "priority": 0.7,
                })
            else:
                goals.append({
                    "type": "observe_player",
                    "priority": 0.5,
                })

    def _evaluate_world_tension(
        self, npc: NPCActor, world: Dict[str, Any], goals: List[Dict[str, Any]]
    ) -> None:
        """Evaluate world tension and generate tension-related goals.

        Args:
            npc: NPC actor.
            world: World state.
            goals: Goals list to append to.
        """
        tension: float = world.get("global_tension", 0.0)

        if tension > 0.7:
            goals.append({
                "type": "survive",
                "priority": tension,
            })
        elif tension > 0.4:
            goals.append({
                "type": "prepare_conflict",
                "priority": tension * 0.8,
            })

    def _evaluate_traits(
        self, npc: NPCActor, world: Dict[str, Any], goals: List[Dict[str, Any]]
    ) -> None:
        """Evaluate NPC traits and generate trait-driven goals.

        Args:
            npc: NPC actor.
            world: World state.
            goals: Goals list to append to.
        """
        aggression = npc.get_trait("aggression", 0.5)
        curiosity = npc.get_trait("curiosity", 0.5)

        if aggression > 0.7:
            goals.append({
                "type": "aggressive_expansion",
                "priority": aggression * 0.6,
            })

        if curiosity > 0.7:
            goals.append({
                "type": "explore",
                "priority": curiosity * 0.5,
            })

    def generate_emergency_goals(
        self, npc: NPCActor, threat_level: float
    ) -> List[Dict[str, Any]]:
        """Generate emergency goals for NPCs under threat.

        Args:
            npc: NPC actor.
            threat_level: Threat level (0-1).

        Returns:
            List of emergency goal dicts.
        """
        goals = []
        if threat_level > 0.8:
            goals.append({
                "type": "flee",
                "priority": threat_level,
            })
        elif threat_level > 0.5:
            goals.append({
                "type": "defend",
                "priority": threat_level * 0.9,
            })
        return goals
