"""Planner for the Dynamic NPC Intent System.

This module provides the Planner class that converts
NPC goals into actionable plans based on strategy profiles.

Tier 17.5 Patch: Adds adaptive planning with failure replanning
and belief-driven action selection.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from .npc_actor import NPCActor, NPCGoal
from .strategy_profiles import STRATEGY_PROFILES, get_strategy_bias


class Planner:
    """Creates action plans for NPCs based on goals and traits.

    The Planner evaluates NPC goals, applies strategy profile biases,
    and generates sequences of actions that NPCs can execute.

    Tier 17.5 Patch 2: Adds adaptive planning with failure tracking
    and fallback strategies when plans fail repeatedly.

    Usage:
        planner = Planner()
        plan = planner.create_plan(npc, goal, world)
    """

    # Action templates for different goal types
    ACTION_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
        "recover_power": [
            {"type": "recruit", "weight": 1.0},
            {"type": "gather_resources", "weight": 0.8},
            {"type": "expand", "weight": 0.6},
            {"type": "fortify", "weight": 0.5},
        ],
        "maintain_dominance": [
            {"type": "patrol", "weight": 0.7},
            {"type": "demonstrate_power", "weight": 0.8},
            {"type": "intimidate_rivals", "weight": 0.6},
        ],
        "ally_player": [
            {"type": "assist", "weight": 0.9},
            {"type": "gift", "weight": 0.7},
            {"type": "defend", "weight": 0.8},
            {"type": "share_intel", "weight": 0.5},
        ],
        "undermine_player": [
            {"type": "spy", "weight": 0.8},
            {"type": "sabotage", "weight": 0.9},
            {"type": "frame_player", "weight": 0.6},
            {"type": "spread_rumors", "weight": 0.7},
        ],
        "observe_player": [
            {"type": "watch", "weight": 0.9},
            {"type": "gather_intel", "weight": 0.8},
            {"type": "report", "weight": 0.6},
        ],
        "survive": [
            {"type": "hide", "weight": 0.9},
            {"type": "evade", "weight": 0.8},
            {"type": "fortify", "weight": 0.7},
        ],
        "prepare_conflict": [
            {"type": "arm", "weight": 0.8},
            {"type": "train", "weight": 0.7},
            {"type": "form_alliances", "weight": 0.6},
        ],
        "aggressive_expansion": [
            {"type": "attack", "weight": 0.9},
            {"type": "conquer", "weight": 0.8},
            {"type": "raze", "weight": 0.5},
        ],
        "explore": [
            {"type": "scout", "weight": 0.9},
            {"type": "map", "weight": 0.7},
            {"type": "discover", "weight": 0.6},
        ],
        "flee": [
            {"type": "retreat", "weight": 1.0},
            {"type": "evade_pursuers", "weight": 0.8},
        ],
        "defend": [
            {"type": "fortify", "weight": 0.9},
            {"type": "hold_position", "weight": 0.8},
            {"type": "call_backup", "weight": 0.6},
        ],
    }

    # Fallback strategies for when plans fail (Patch 2)
    FALLBACK_STRATEGIES: Dict[str, List[Dict[str, Any]]] = {
        "undermine_player": [
            {"type": "retreat", "weight": 1.0},
            {"type": "reassess", "weight": 0.8},
            {"type": "new_strategy", "weight": 0.6},
        ],
        "aggressive_expansion": [
            {"type": "fortify", "weight": 1.0},
            {"type": "diplomacy", "weight": 0.7},
            {"type": "consolidate", "weight": 0.5},
        ],
        "default": [
            {"type": "retreat", "weight": 1.0},
            {"type": "reassess", "weight": 0.8},
            {"type": "new_strategy", "weight": 0.6},
        ],
    }

    def create_plan(
        self,
        npc: NPCActor,
        goal: Dict[str, Any],
        world: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Create an action plan for an NPC based on a goal.

        Tier 17.5 Patch 2: Checks for repeated failures and
        adapts strategy accordingly.

        Args:
            npc: NPC actor to create plan for.
            goal: Goal dict with 'type' and 'priority' keys.
            world: Optional world state for context.

        Returns:
            List of action dicts the NPC will execute.
        """
        goal_type = goal.get("type", "")
        failed_attempts = goal.get("failed_attempts", 0)

        # Patch 2: Check for repeated failures
        if failed_attempts > 2:
            return self._fallback_strategy(npc, goal)

        # Also check NPC failure memory
        similar_failures = npc.get_similar_failures(goal_type)
        if similar_failures > 2:
            return self._fallback_strategy(npc, goal)

        template = self.ACTION_TEMPLATES.get(goal_type, [])

        if not template:
            return self._create_generic_plan(goal)

        # Apply strategy biases
        strategy = npc.get_trait("strategy", "diplomatic")
        biased_actions = self._apply_strategy_bias(npc, strategy, template)

        # Patch 3: Apply belief-driven adjustments
        biased_actions = self._apply_belief_adjustments(npc, biased_actions)

        # Select top actions based on weights and NPC capability
        plan = self._select_plan_actions(npc, biased_actions)

        return plan

    def _fallback_strategy(
        self, npc: NPCActor, goal: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate fallback strategy after repeated failures.

        Tier 17.5 Patch 2: When plans fail multiple times, NPCs
        switch to more cautious approach.

        Args:
            npc: NPC actor.
            goal: Failed goal dict.

        Returns:
            Fallback action plan.
        """
        goal_type = goal.get("type", "")
        fallback = self.FALLBACK_STRATEGIES.get(
            goal_type, self.FALLBACK_STRATEGIES["default"]
        )

        # Adjust based on NPC traits
        intelligence = npc.get_trait("intelligence", 0.5)
        if intelligence > 0.7:
            # Smart NPCs try new strategies
            fallback = [
                {"type": "reassess", "weight": 1.0},
                {"type": "adapt", "weight": 0.8},
                {"type": "new_approach", "weight": 0.6},
            ]
        else:
            # Less intelligent NPCs retreat
            fallback = [
                {"type": "retreat", "weight": 1.0},
                {"type": "reassess", "weight": 0.8},
                {"type": "wait", "weight": 0.5},
            ]

        return [{**a, "target_faction": npc.faction} for a in fallback]

    def _apply_strategy_bias(
        self,
        npc: NPCActor,
        strategy: str,
        actions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Apply strategy profile bias to action weights.

        Args:
            npc: NPC actor.
            strategy: Strategy profile name.
            actions: List of action dicts.

        Returns:
            Adjusted action list with modified weights.
        """
        bias = get_strategy_bias(strategy)

        adjusted = []
        for action in actions:
            action_type = action["type"]
            weight = action["weight"]

            # Apply bias if exists
            attack_bias = bias.get("attack_bias", 1.0)
            diplomacy_bias = bias.get("diplomacy_bias", 1.0)
            randomness = bias.get("randomness", 0.0)

            if action_type in ("attack", "conquer", "aggressive_expansion"):
                weight *= attack_bias
            elif action_type in ("assist", "ally", "gift", "defend"):
                weight *= diplomacy_bias

            # Add randomness if present
            if randomness > 0:
                weight *= 1.0 + random.uniform(-randomness, randomness)

            weight = max(0.0, min(1.0, weight))  # Clamp
            adjusted.append({**action, "weight": weight})

        # Sort by adjusted weight
        return sorted(adjusted, key=lambda a: a["weight"], reverse=True)

    def _apply_belief_adjustments(
        self,
        npc: NPCActor,
        actions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Apply belief-driven adjustments to action weights.

        Tier 17.5 Patch 3: Beliefs about player and world affect
        action preferences.

        Args:
            npc: NPC actor.
            actions: Action list.

        Returns:
            Adjusted action list.
        """
        trust = npc.get_belief("player_trust", 0.0)
        fear = npc.get_belief("player_fear", 0.0)

        adjusted = []
        for action in actions:
            action_type = action["type"]
            weight = action.get("weight", 0.5)

            # Trust affects cooperation actions
            if trust > 0.5 and action_type in ("assist", "gift", "ally"):
                weight *= 1.3
            elif trust < -0.3 and action_type in ("undermine", "sabotage", "spy"):
                weight *= 1.3

            # Fear affects defensive actions
            if fear > 0.5 and action_type in ("fortify", "hide", "evade"):
                weight *= 1.2

            adjusted.append({**action, "weight": max(0.0, min(1.0, weight))})

        return sorted(adjusted, key=lambda a: a["weight"], reverse=True)

    def _select_plan_actions(
        self, npc: NPCActor, actions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Select actions for the plan based on NPC capabilities.

        Args:
            npc: NPC actor.
            actions: Biased action list.

        Returns:
            Selected action plan.
        """
        # Select up to 3 actions, weighted by NPC traits
        aggression = npc.get_trait("aggression", 0.5)
        intelligence = npc.get_trait("intelligence", 0.5)

        selected: List[Dict[str, Any]] = []
        for action in actions:
            if len(selected) >= 3:
                break

            action_type = action["type"]
            weight = action["weight"]

            # Aggressive NPCs prefer combat actions
            if aggression > 0.7 and action_type in ("attack", "conquer"):
                weight *= 1.3

            # Intelligent NPCs prefer indirect actions
            if intelligence > 0.7 and action_type in ("spy", "sabotage", "frame_player"):
                weight *= 1.2

            action_copy = {**action}
            action_copy["target_faction"] = npc.faction
            selected.append(action_copy)

        return selected

    def _create_generic_plan(self, goal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create a generic plan for unknown goal types.

        Args:
            goal: Goal dict.

        Returns:
            Generic action plan.
        """
        return [
            {"type": "observe", "weight": 0.5},
            {"type": "evaluate", "weight": 0.4},
            {"type": "adapt", "weight": 0.3},
        ]

    def create_plan_for_npc_goal(
        self,
        npc: NPCActor,
        goal: NPCGoal,
        world: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Create a plan from a stateful NPCGoal.

        Tier 17.5 Patch: Works with persistent goals.

        Args:
            npc: NPC actor.
            goal: Stateful NPCGoal.
            world: Optional world state.

        Returns:
            Action plan list.
        """
        goal_dict = goal.to_dict()
        return self.create_plan(npc, goal_dict, world)
