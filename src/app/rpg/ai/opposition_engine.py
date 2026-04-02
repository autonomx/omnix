"""Opposition Engine for the Dynamic NPC Intent System.

This module provides the OppositionEngine class that applies
NPC actions to the world, interfering with quests and affecting
the game state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    # Avoid circular imports - use type hints only
    from ..quest.quest_engine import QuestEngine


class OppositionEngine:
    """Applies NPC actions to interfere with player and world.

    The OppositionEngine interprets NPC actions and applies their
    effects to quests, factions, and world state.

    Usage:
        engine = OppositionEngine()
        result = engine.apply(npc_action, quest_engine, world)
    """

    # Action effects configuration
    ACTION_EFFECTS: Dict[str, Dict[str, Any]] = {
        "sabotage": {
            "quest_impact": -0.2,
            "description": "Slows quest progress",
        },
        "spy": {
            "quest_impact": -0.05,
            "intel_gain": 0.1,
            "description": "Gathers intel, minor interference",
        },
        "assist": {
            "quest_impact": 0.2,
            "description": "Accelerates quest progress",
        },
        "attack": {
            "tension_impact": 0.1,
            "faction_impact": -0.05,
            "description": "Increases global tension",
        },
        "expand": {
            "faction_power_impact": 0.03,
            "description": "Increases faction power",
        },
        "recruit": {
            "faction_power_impact": 0.02,
            "description": "Recruits for faction",
        },
        "fortify": {
            "defensive_power_impact": 0.05,
            "description": "Fortifies faction position",
        },
        "frame_player": {
            "reputation_impact": -0.1,
            "description": "Damages player reputation",
        },
        "spread_rumors": {
            "reputation_impact": -0.05,
            "tension_impact": 0.03,
            "description": "Spreads rumors about player",
        },
        "gift": {
            "reputation_impact": 0.1,
            "description": "Improves relations with player",
        },
    }

    def apply(
        self,
        npc_action: Dict[str, Any],
        quest_engine: Any,  # QuestEngine
        world: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply an NPC action to the world.

        Args:
            npc_action: Action dict from intent engine.
            quest_engine: QuestEngine instance.
            world: World state dictionary.

        Returns:
            Result dict with action type and effects applied.
        """
        action_type = npc_action.get("action", {}).get("type", "")
        effects = self._get_action_effects(action_type)

        # Apply effects based on action type
        results = self._apply_effects(action_type, effects, quest_engine, world, npc_action)

        return {
            "type": "npc_action",
            "action": action_type,
            "npc_id": npc_action.get("npc_id"),
            "effects": results,
        }

    def _get_action_effects(self, action_type: str) -> Dict[str, Any]:
        """Get effect configuration for an action type.

        Args:
            action_type: Action type string.

        Returns:
            Dict of effect values.
        """
        return self.ACTION_EFFECTS.get(
            action_type,
            {"description": f"Unknown action: {action_type}"},
        )

    def _apply_effects(
        self,
        action_type: str,
        effects: Dict[str, Any],
        quest_engine: Any,  # QuestEngine
        world: Dict[str, Any],
        npc_action: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Apply effects to world and quests.

        Args:
            action_type: Action type.
            effects: Effect configuration.
            quest_engine: QuestEngine instance.
            world: World state.
            npc_action: The original NPC action dict.

        Returns:
            List of applied effects.
        """
        results: List[Dict[str, Any]] = []

        # Sabotage quests - reduce progress
        if action_type == "sabotage":
            results.extend(self._apply_sabotage(quest_engine, effects))

        # Help player quests - increase progress
        if action_type == "assist":
            results.extend(self._apply_assist(quest_engine, effects))

        # Increase tension
        if action_type in ("attack", "spread_rumors"):
            results.append(self._apply_tension(world, effects))

        # Modify faction power
        if action_type in ("expand", "recruit"):
            results.append(self._apply_faction_power(npc_action, world, effects))

        # Modify player reputation
        if action_type in ("frame_player", "spread_rumors", "gift"):
            results.append(self._apply_reputation(world, effects))

        return results

    def _apply_sabotage(
        self, quest_engine: Any, effects: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply sabotage effects to active quests.

        Args:
            quest_engine: QuestEngine instance.
            effects: Effect configuration.

        Returns:
            List of sabotage effect results.
        """
        results = []
        quest_impact = effects.get("quest_impact", -0.2)

        if hasattr(quest_engine, "tracker"):
            active_quests = quest_engine.tracker.get_active_quests()
            for quest in active_quests:
                if hasattr(quest, "arc_progress"):
                    quest.arc_progress = max(0.0, quest.arc_progress + quest_impact)
                    results.append({
                        "type": "quest_sabotage",
                        "quest_id": quest.id if hasattr(quest, "id") else "unknown",
                        "impact": quest_impact,
                    })

        return results

    def _apply_assist(
        self, quest_engine: Any, effects: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply assistance effects to active quests.

        Args:
            quest_engine: QuestEngine instance.
            effects: Effect configuration.

        Returns:
            List of assistance effect results.
        """
        results = []
        quest_impact = effects.get("quest_impact", 0.2)

        if hasattr(quest_engine, "tracker"):
            active_quests = quest_engine.tracker.get_active_quests()
            for quest in active_quests:
                if hasattr(quest, "arc_progress"):
                    quest.arc_progress = min(1.0, quest.arc_progress + quest_impact)
                    results.append({
                        "type": "quest_assistance",
                        "quest_id": quest.id if hasattr(quest, "id") else "unknown",
                        "impact": quest_impact,
                    })

        return results

    def _apply_tension(
        self, world: Dict[str, Any], effects: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply tension effects to world state.

        Args:
            world: World state dictionary.
            effects: Effect configuration.

        Returns:
            Tension effect result.
        """
        tension_impact = effects.get("tension_impact", 0.1)
        current_tension = world.get("global_tension", 0.0)
        world["global_tension"] = min(1.0, current_tension + tension_impact)

        return {
            "type": "tension_change",
            "old_value": current_tension,
            "new_value": world["global_tension"],
            "impact": tension_impact,
        }

    def _apply_faction_power(
        self, npc_action: Dict[str, Any], world: Dict[str, Any], effects: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply faction power effects to world state.

        Args:
            npc_action: NPC action dict with faction info.
            world: World state dictionary.
            effects: Effect configuration.

        Returns:
            Faction power effect result.
        """
        faction_impact = effects.get("faction_power_impact", 0.03)
        faction = "unknown"
        if npc_action and "faction" in npc_action:
            faction = npc_action["faction"]
        elif npc_action and "goal" in npc_action and "faction" in npc_action.get("goal", {}):
            faction = npc_action["goal"].get("faction", "unknown")

        if "factions" not in world:
            world["factions"] = {}
        if faction not in world["factions"]:
            world["factions"][faction] = {"power": 0.5}

        current_power = world["factions"][faction].get("power", 0.5)
        world["factions"][faction]["power"] = min(1.0, current_power + faction_impact)

        return {
            "type": "faction_power_change",
            "faction": faction,
            "old_value": current_power,
            "new_value": world["factions"][faction]["power"],
            "impact": faction_impact,
        }

    def _apply_reputation(
        self, world: Dict[str, Any], effects: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply reputation effects to world state.

        Args:
            world: World state dictionary.
            effects: Effect configuration.

        Returns:
            Reputation effect result.
        """
        rep_impact = effects.get("reputation_impact", 0.1)
        current_rep = world.get("player_reputation", 0.0)
        world["player_reputation"] = max(-1.0, min(1.0, current_rep + rep_impact))

        return {
            "type": "reputation_change",
            "old_value": current_rep,
            "new_value": world["player_reputation"],
            "impact": rep_impact,
        }