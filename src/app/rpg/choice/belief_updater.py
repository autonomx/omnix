"""Belief Updater - Updates NPC beliefs based on player choices.

This module provides the BeliefUpdater class that modifies NPC
memory and belief systems based on player actions. Belief changes
are cumulative and permanent - NPCs remember what players do.

Core principle: Every action changes how NPCs perceive the player.
These perception changes affect future interactions and cannot be
undone.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .choice_models import ConsequenceRecord


class BeliefUpdater:
    """Updates NPC beliefs based on player choices.

    The BeliefUpdater tracks how NPCs feel about each other and
    the player. When a player makes a choice, their relationships
    shift permanently.

    Usage:
        updater = BeliefUpdater()
        updater.apply_consequences(consequences, memory)
    """

    # Default belief values
    DEFAULT_BELIEF = 0.0
    MIN_BELIEF = -1.0
    MAX_BELIEF = 1.0

    # Belief state flags
    HOSTILE_THRESHOLD = -0.5
    FRIENDLY_THRESHOLD = 0.5
    TRUSTED_THRESHOLD = 0.8

    def apply_consequences(
        self,
        consequences: List[ConsequenceRecord],
        memory: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Apply belief update consequences to memory.

        Args:
            consequences: List of ConsequenceRecord objects.
            memory: NPC memory/belief state dict.

        Returns:
            List of applied belief update descriptions.
        """
        applied = []
        for consequence in consequences:
            if consequence.consequence_type == "belief_update":
                effect = self._apply_single(consequence, memory)
                if effect:
                    applied.append(effect)
                    consequence.applied = True
        return applied

    def _apply_single(
        self,
        consequence: ConsequenceRecord,
        memory: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Apply a single belief consequence.

        Args:
            consequence: Consequence record with belief data.
            memory: Memory state dict.

        Returns:
            Effect description dict, or None if not applicable.
        """
        data = consequence.data
        actor = data.get("actor", "")
        target = data.get("target", "")
        delta = data.get("delta", 0.0)

        if not actor or not target:
            return None

        return self.apply(memory, actor, target, delta)

    def apply(
        self,
        memory: Dict[str, Any],
        actor: str,
        target: str,
        effect: float,
    ) -> Dict[str, Any]:
        """Apply a belief update between actor and target.

        Updates the belief value that actor holds about target.
        Positive values mean positive feelings; negative means
        hostility.

        Args:
            memory: NPC memory/belief state dict.
            actor: The NPC/player whose belief is changing.
            target: The entity the belief is about.
            effect: Amount to change belief by (positive or negative).

        Returns:
            Dict with belief update details.
        """
        key = f"{actor}->{target}"

        memory.setdefault("beliefs", {})
        old_belief = memory["beliefs"].get(key, self.DEFAULT_BELIEF)

        # Apply the effect
        new_belief = old_belief + effect

        # Clamp to valid range
        new_belief = max(self.MIN_BELIEF, min(self.MAX_BELIEF, new_belief))
        new_belief = round(new_belief, 4)

        memory["beliefs"][key] = new_belief

        # Determine relationship classification
        old_relation = self._classify_belief(old_belief)
        new_relation = self._classify_belief(new_belief)

        result = {
            "type": "belief_update",
            "key": key,
            "actor": actor,
            "target": target,
            "old_belief": old_belief,
            "new_belief": new_belief,
            "delta": effect,
            "old_relation": old_relation,
            "new_relation": new_relation,
        }

        # Track if relationship changed classification
        if old_relation != new_relation:
            result["relationship_changed"] = True
            result.setdefault("tags", memory.get("tags", []))
            if f"relation_{new_relation}_{key}" not in result["tags"]:
                memory.setdefault("tags", [])
                memory["tags"].append(f"relation_{new_relation}_{key}")

        return result

    def _classify_belief(self, belief: float) -> str:
        """Classify a belief value into a relationship type.

        Args:
            belief: Belief value between -1.0 and 1.0.

        Returns:
            Classification string (hostile, neutral, friendly, trusted).
        """
        if belief <= self.HOSTILE_THRESHOLD:
            return "hostile"
        elif belief >= self.TRUSTED_THRESHOLD:
            return "trusted"
        elif belief >= self.FRIENDLY_THRESHOLD:
            return "friendly"
        else:
            return "neutral"

    def get_belief(
        self,
        memory: Dict[str, Any],
        actor: str,
        target: str,
    ) -> float:
        """Get the current belief value between actor and target.

        Args:
            memory: NPC memory/belief state dict.
            actor: The entity holding the belief.
            target: The entity the belief is about.

        Returns:
            Current belief value, or default if not set.
        """
        key = f"{actor}->{target}"
        beliefs = memory.get("beliefs", {})
        return beliefs.get(key, self.DEFAULT_BELIEF)

    def get_relationship(
        self,
        memory: Dict[str, Any],
        actor: str,
        target: str,
    ) -> str:
        """Get the relationship classification between two entities.

        Args:
            memory: NPC memory/belief state dict.
            actor: The entity holding the belief.
            target: The entity the belief is about.

        Returns:
            Relationship classification string.
        """
        belief = self.get_belief(memory, actor, target)
        return self._classify_belief(belief)

    def is_hostile(
        self,
        memory: Dict[str, Any],
        actor: str,
        target: str,
    ) -> bool:
        """Check if actor is hostile toward target.

        Args:
            memory: NPC memory/belief state dict.
            actor: The entity to check.
            target: The entity being checked about.

        Returns:
            True if actor is hostile toward target.
        """
        belief = self.get_belief(memory, actor, target)
        return belief <= self.HOSTILE_THRESHOLD

    def is_friendly(
        self,
        memory: Dict[str, Any],
        actor: str,
        target: str,
    ) -> bool:
        """Check if actor is friendly toward target.

        Args:
            memory: NPC memory/belief state dict.
            actor: The entity to check.
            target: The entity being checked about.

        Returns:
            True if actor is friendly or trusted toward target.
        """
        belief = self.get_belief(memory, actor, target)
        return belief >= self.FRIENDLY_THRESHOLD

    def is_trusted(
        self,
        memory: Dict[str, Any],
        actor: str,
        target: str,
    ) -> bool:
        """Check if target is trusted by actor.

        Args:
            memory: NPC memory/belief state dict.
            actor: The entity to check.
            target: The entity being checked about.

        Returns:
            True if target is trusted by actor.
        """
        belief = self.get_belief(memory, actor, target)
        return belief >= self.TRUSTED_THRESHOLD

    def get_all_beliefs(
        self,
        memory: Dict[str, Any],
    ) -> Dict[str, float]:
        """Get all belief values.

        Args:
            memory: NPC memory/belief state dict.

        Returns:
            Dict mapping belief keys to values.
        """
        return dict(memory.get("beliefs", {}))

    def get_beliefs_about(
        self,
        memory: Dict[str, Any],
        entity: str,
    ) -> Dict[str, float]:
        """Get all beliefs about a specific entity.

        Args:
            memory: NPC memory/belief state dict.
            entity: Entity to get beliefs about.

        Returns:
            Dict mapping actors to their belief about the entity.
        """
        beliefs = memory.get("beliefs", {})
        result = {}
        for key, value in beliefs.items():
            if key.endswith(f"->{entity}"):
                actor = key.split("->")[0]
                result[actor] = value
        return result

    def get_beliefs_held_by(
        self,
        memory: Dict[str, Any],
        actor: str,
    ) -> Dict[str, float]:
        """Get all beliefs held by a specific actor.

        Args:
            memory: NPC memory/belief state dict.
            actor: Actor whose beliefs to retrieve.

        Returns:
            Dict mapping targets to belief values.
        """
        beliefs = memory.get("beliefs", {})
        result = {}
        for key, value in beliefs.items():
            if key.startswith(f"{actor}->"):
                target = key.split("->")[1]
                result[target] = value
        return result

    def reset_belief(
        self,
        memory: Dict[str, Any],
        actor: str,
        target: str,
    ) -> Optional[float]:
        """Reset a belief to default. WARNING: Use sparingly.

        Note: In normal gameplay, beliefs should not be reset
        as part of the irreversible consequence principle.
        This method is primarily for testing and debugging.

        Args:
            memory: NPC memory/belief state dict.
            actor: The entity whose belief to reset.
            target: The entity the belief is about.

        Returns:
            Old belief value, or None if no belief existed.
        """
        key = f"{actor}->{target}"
        beliefs = memory.get("beliefs", {})
        if key in beliefs:
            old = beliefs.pop(key)
            return old
        return None

    def get_memory_summary(
        self,
        memory: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Get a human-readable summary of all beliefs.

        Args:
            memory: NPC memory/belief state dict.

        Returns:
            Summary dict with belief classifications.
        """
        beliefs = self.get_all_beliefs(memory)
        classified = {}
        for key, value in beliefs.items():
            classified[key] = {
                "belief": value,
                "relation": self._classify_belief(value),
            }
        return {
            "beliefs": classified,
            "tags": memory.get("tags", []),
        }