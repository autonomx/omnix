"""Emergence Adapter — Standardizes system metrics for Director consumption.

The EmergenceAdapter analyzes world state, NPCs, and recent outcomes to
produce the four key signals the Director uses to decide interventions:

    1. Stagnation: How many NPCs are idle/nothing is happening
    2. Conflict: Current conflict intensity based on enemy/threat levels
    3. Failure Spike: Recent action failure rate
    4. Divergence: How chaotic/unpredictable the system has become

Each signal is normalized to 0.0-1.0 range for consistent Director thresholds.

Design principle: "The world reacts to system behavior, not just player actions."
"""

from __future__ import annotations

from typing import Any, Dict, List


class EmergenceAdapter:
    """Analyzes system state and produces signals for Director intervention decisions.

    The adapter bridges between the game simulation and the Director's needs.
    It takes raw game state data and converts it to standardized metrics
    (0.0 to 1.0) that the Director uses to decide whether to inject events.

    This is intentionally simple and extensible. Each metric can be
    enhanced independently with more sophisticated analysis.
    """

    # Thresholds for signal normalization
    MAX_IDLE_RATIO = 1.0
    MAX_ENEMY_COUNT = 10
    MAX_DANGER_LEVEL = 10
    MAX_CHAOS = 1.0

    def __init__(
        self,
        idle_threshold: float = 0.0,
        enemy_count_max: int = 10,
        danger_level_max: int = 10,
        chaos_max: float = 1.0,
    ):
        """Initialize EmergenceAdapter.

        Args:
            idle_threshold: Ratio of idle NPCs to start measuring (0=all).
            enemy_count_max: Enemy count value that maps to 1.0 signal.
            danger_level_max: Danger level value that maps to 1.0 signal.
            chaos_max: Chaos value that maps to 1.0 signal.
        """
        self.idle_threshold = idle_threshold
        self.enemy_count_max = enemy_count_max
        self.danger_level_max = danger_level_max
        self.chaos_max = chaos_max

    def analyze(
        self,
        world_state: Dict[str, Any],
        npcs: List[Any],
        outcomes: List[Any],
    ) -> Dict[str, float]:
        """Produce signals from current game state for Director decisions.

        Args:
            world_state: Current world state dictionary.
            npcs: List of NPC objects/entities.
            outcomes: List of recent action outcome objects.

        Returns:
            Dict with signal keys: stagnation, conflict, failure_spike, divergence.
            Values are floats in 0.0-1.0 range.
        """
        return {
            "stagnation": self._stagnation(npcs),
            "conflict": self._conflict(world_state),
            "failure_spike": self._failure(outcomes),
            "divergence": self._divergence(world_state),
        }

    def _stagnation(self, npcs: List[Any]) -> float:
        """Calculate stagnation signal based on idle NPC ratio.

        Stagnation occurs when too many NPCs are doing nothing.
        A stagnation signal above threshold means the Director should
        inject a twist to get things moving.

        Args:
            npcs: List of NPC objects with last_action attribute.

        Returns:
            Stagnation signal 0.0 (all active) to 1.0 (all idle).
        """
        if not npcs:
            return 0.0

        idle_count = 0
        for npc in npcs:
            last_action = getattr(npc, "last_action", "idle")
            if last_action == "idle" or last_action is None:
                idle_count += 1

        ratio = idle_count / len(npcs)
        # Map ratio to 0-1 range, only count above threshold
        return max(0.0, min(1.0, (ratio - self.idle_threshold) / (1.0 - self.idle_threshold)))

    def _conflict(self, world_state: Dict[str, Any]) -> float:
        """Calculate conflict signal based on threat levels.

        High conflict signal tells the Director things are escalating
        and it may choose to intensify further or introduce de-escalation.

        Args:
            world_state: World state dict with enemy_count, danger_level.

        Returns:
            Conflict signal 0.0 (peaceful) to 1.0 (max conflict).
        """
        enemy_count = world_state.get("enemy_count", 0)
        danger_level = world_state.get("danger_level", 0)

        # Combine enemy count and danger level for conflict signal
        enemy_signal = min(1.0, enemy_count / max(self.enemy_count_max, 1))
        danger_signal = min(1.0, danger_level / max(self.danger_level_max, 1))

        # Weighted average
        return (enemy_signal * 0.6) + (danger_signal * 0.4)

    def _failure(self, outcomes: List[Any]) -> float:
        """Calculate failure spike signal from recent outcomes.

        A failure spike means many recent actions have failed.
        The Director may respond with assistance (supply drop) or
        punishment (consequences for recklessness).

        Args:
            outcomes: List of outcome objects with success attribute.

        Returns:
            Failure signal 0.0 (all success) to 1.0 (all failed).
        """
        if not outcomes:
            return 0.0

        failures = 0
        total = 0
        for outcome in outcomes:
            success = getattr(outcome, "success", True)
            if hasattr(outcome, "__dict__"):
                success = getattr(outcome, "success", True)
            elif isinstance(outcome, dict):
                success = outcome.get("success", True)
            else:
                success = bool(outcome)

            total += 1
            if not success:
                failures += 1

        return failures / total if total > 0 else 0.0

    def _divergence(self, world_state: Dict[str, Any]) -> float:
        """Calculate divergence/chaos signal.

        Divergence measures how chaotic or unpredictable the system is.
        High divergence with high stagnation suggests the world has
        fragmented into chaos. The Director may inject a unifying chaos event.

        Args:
            world_state: World state dict with chaos, divergence keys.

        Returns:
            Divergence signal 0.0 (orderly) to 1.0 (maximum chaos).
        """
        chaos = world_state.get("chaos", 0.0)
        divergence = world_state.get("divergence", 0.0)

        # Use whichever is provided, preferring chaos
        combined = max(chaos, divergence, 0.0)
        return min(1.0, combined / max(self.chaos_max, 0.001))