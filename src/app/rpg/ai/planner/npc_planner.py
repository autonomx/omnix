"""PHASE 4.5 — NPC Decision Loop Integration

NPCPlanner integrates simulation-based planning into NPC decision-making.

Instead of picking random actions, NPCs:
1. Generate 3-5 candidate action sequences
2. Simulate each in an isolated sandbox
3. Score results with AI/heuristic evaluator
4. Choose the best scoring candidate

This creates intentional, narrative-driven NPC behavior.

Example:
    planner = NPCPlanner(simulator, evaluator, config=PlanningConfig())
    best_actions = planner.choose_action(
        base_events=history,
        candidates=candidate_generator.generate(npc, context),
        context={"npc": npc.id, "goal": "attack"},
    )
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...core.event_bus import Event

logger = logging.getLogger(__name__)


@dataclass
class PlanningConfig:
    """Configuration for NPC planning behavior.

    Attributes:
        max_candidates: Maximum candidates to simulate. Default 5.
        max_ticks: Ticks to simulate per candidate. Default 5.
        cooldown_ticks: Minimum ticks between planning cycles. Default 5.
        use_heuristic: Force heuristic scoring (no LLM). Default False.
        min_candidate_events: Minimum events per candidate for pruning. Default 1.
    """

    max_candidates: int = 5
    max_ticks: int = 5
    cooldown_ticks: int = 5
    use_heuristic: bool = False
    min_candidate_events: int = 1


class NPCPlanner:
    """Simulation-based NPC decision planner.

    This planner replaces reactive NPC behavior with forward-looking
    planning. NPCs simulate possible futures and choose intelligently.

    Integration:
    - Called during GameLoop NPC phase
    - Returns best candidate events for emission
    - Cooldown prevents LLM cost explosion

    Performance safeguards:
    - max_candidates limits simulation breadth
    - cooldown_ticks spaces out expensive planning
    - min_candidate_events prunes garbage branches
    """

    def __init__(
        self,
        simulator: Any,
        evaluator: Any,
        config: Optional[PlanningConfig] = None,
    ):
        """Initialize the NPCPlanner.

        Args:
            simulator: FutureSimulator or compatible object with
                      simulate_candidates() or simulate_and_score() method.
            evaluator: AIBranchEvaluator or compatible object with
                      evaluate(events, context) -> float method.
            config: Optional planning configuration.
        """
        self.simulator = simulator
        self.evaluator = evaluator
        self.config = config or PlanningConfig()
        self._cooldown_remaining = 0

    def choose_action(
        self,
        base_events: List[Event],
        candidates: List[List[Event]],
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Event]]:
        """Choose the best action via simulation and scoring.

        This is the main planning entry point. It:
        1. Applies cooldown check (skip planning if cooling down)
        2. Limits candidates to max_candidates
        3. Simulates each candidate in isolation
        4. Scores results with evaluator
        5. Returns highest scoring candidate

        Args:
            base_events: Current game state as event history.
            candidates: List of candidate action sequences.
                       Each candidate is a list of Events.
            context: Optional context dictionary for evaluation
                    (e.g., NPC goals, world state).

        Returns:
            Best candidate events, or None if no candidates available.

        Example:
            candidates = [
                [Event("attack", target="goblin")],
                [Event("flee", direction="north")],
                [Event("negotiate", target="goblin")],
            ]
            best = planner.choose_action(history, candidates, {"goal": "survive"})
        """
        context = context or {}

        # Check cooldown
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            logger.debug("NPC planning on cooldown, skipping")
            if candidates:
                # Fallback to first candidate when cooling down
                return candidates[0]
            return None

        # Empty candidates guard
        if not candidates:
            return None

        # Apply max_candidates limit
        trimmed = candidates[: self.config.max_candidates]

        # Try simulation-based scoring first
        best = self._simulate_and_choose(base_events, trimmed, context)

        # Reset cooldown after successful planning
        if best is not None:
            self._cooldown_remaining = self.config.cooldown_ticks
            return best

        # Fallback: return first candidate if simulation fails
        logger.warning("Simulation planning failed, falling back to first candidate")
        return trimmed[0] if trimmed else None

    def _simulate_and_choose(
        self,
        base_events: List[Event],
        candidates: List[List[Event]],
        context: Dict[str, Any],
    ) -> Optional[List[Event]]:
        """Run simulation and return best candidate.

        Internal method that handles the actual simulation + scoring pipeline.

        Args:
            base_events: Base event history.
            candidates: Trimmed candidate list.
            context: Evaluation context.

        Returns:
            Best candidate or None on failure.
        """
        try:
            # Check if simulator supports simulate_and_score interface
            if hasattr(self.simulator, "simulate_and_score"):
                scores = self.simulator.simulate_and_score(
                    base_events, candidates, self.evaluator, context
                )
                if scores:
                    return scores[0].candidate
                return None

            # Fallback: use simulate_candidates + manual scoring
            elif hasattr(self.simulator, "simulate_candidates"):
                results = self.simulator.simulate_candidates(
                    base_events,
                    candidates,
                    max_ticks=self.config.max_ticks,
                    prune_threshold=self.config.min_candidate_events,
                )

                best_score = -1.0
                best_candidate = None

                for candidate, result in results:
                    try:
                        score = self.evaluator.evaluate(result.events, context)
                    except Exception:
                        score = 0.5

                    if score > best_score:
                        best_score = score
                        best_candidate = candidate

                return best_candidate

            else:
                logger.error(
                    f"Simulator {type(self.simulator).__name__} does not support "
                    "simulate_candidates or simulate_and_score"
                )
                return None

        except Exception as e:
            logger.error(f"Simulation failed: {e}")
            return None

    def reset_cooldown(self) -> None:
        """Reset planning cooldown.

        Call this when NPC circumstances change dramatically
        (e.g., health drops, new enemy appears) to force
        immediate replanning.
        """
        self._cooldown_remaining = 0

    @property
    def is_cooling_down(self) -> bool:
        """Check if planning is on cooldown."""
        return self._cooldown_remaining > 0