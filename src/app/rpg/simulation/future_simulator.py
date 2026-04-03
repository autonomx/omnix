"""PHASE 4.5 — Forward Simulation Engine

Simulates multiple candidate futures in parallel and returns
results for scoring and decision-making.

This module enables:
- Running multiple "what-if" scenarios from a single base state
- Comparing outcomes across different action choices
- Feeding results to AI evaluators for scoring

Example:
    simulator = FutureSimulator(sandbox)
    results = simulator.simulate_candidates(
        base_events=history,
        candidates=[
            [attack_event],
            [flee_event],
            [negotiate_event],
        ],
    )
    for candidate, result in results:
        print(f"Candidate {candidate}: tick={result.final_tick}")
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.event_bus import Event
from .sandbox import SimulationResult, SimulationSandbox


@dataclass
class CandidateScore:
    """Score for a candidate simulation.

    Attributes:
        candidate: The original candidate events.
        result: The simulation result.
        score: Numeric score from evaluator (0-1).
        metadata: Additional scoring metadata.
    """

    candidate: List[Event]
    result: SimulationResult
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class FutureSimulator:
    """Run multiple candidate futures and collect results.

    This class manages parallel simulation of multiple candidate
    action sequences, collecting results for comparison and scoring.

    Performance considerations:
    - Each candidate runs in an isolated sandbox
    - max_candidates limits simulation cost
    - Results are returned in insertion order
    """

    def __init__(
        self,
        sandbox: SimulationSandbox,
        max_candidates: int = 5,
        default_max_ticks: int = 5,
    ):
        """Initialize the FutureSimulator.

        Args:
            sandbox: The SimulationSandbox for running simulations.
                     Must be a sandbox instance, not None.
            max_candidates: Maximum number of candidates to simulate.
                           Prevents combinatorial explosion. Default 5.
            default_max_ticks: Default ticks per simulation. Default 5.
        """
        if sandbox is None:
            raise ValueError("sandbox cannot be None")
        self.sandbox = sandbox
        self.max_candidates = max_candidates
        self.default_max_ticks = default_max_ticks

    def simulate_candidates(
        self,
        base_events: List[Event],
        candidates: List[List[Event]],
        max_ticks: Optional[int] = None,
        prune_threshold: Optional[int] = None,
    ) -> List[Tuple[List[Event], SimulationResult]]:
        """Simulate multiple candidate futures.

        Each candidate represents a possible action sequence.
        Results are returned in the same order as candidates.

        Args:
            base_events: The base event history for state reconstruction.
            candidates: List of candidate action sequences to simulate.
                       Each candidate is a list of events.
            max_ticks: Override default ticks per simulation.
            prune_threshold: If set, skip candidates with fewer events
                           than this threshold (garbage branch pruning).

        Returns:
            List of (candidate, result) tuples in insertion order.

        Example:
            candidates = [
                [Event("attack", ...)],
                [Event("flee", ...)],
                [Event("negotiate", ...)],
            ]
            results = simulator.simulate_candidates(history, candidates)
            # Returns [(attack_candidate, attack_result), ...]
        """
        results: List[Tuple[List[Event], SimulationResult]] = []

        # Apply max_candidates limit to prevent explosion
        trimmed_candidates = candidates[: self.max_candidates]

        # Use default ticks if not overridden
        ticks = max_ticks if max_ticks is not None else self.default_max_ticks

        for i, candidate in enumerate(trimmed_candidates):
            # Prune garbage branches early
            if prune_threshold is not None and len(candidate) < prune_threshold:
                continue

            # Run isolated simulation
            result = self.sandbox.run(
                base_events=base_events,
                future_events=candidate,
                max_ticks=ticks,
            )

            results.append((candidate, result))

        return results

    def simulate_and_score(
        self,
        base_events: List[Event],
        candidates: List[List[Event]],
        evaluator: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[CandidateScore]:
        """Simulate candidates and score them with an evaluator.

        This is the main NPC decision-making pipeline:
        1. Simulate each candidate
        2. Score each result with AI/heuristic evaluator
        3. Return sorted scores for easy selection

        Args:
            base_events: The base event history.
            candidates: List of candidate action sequences.
            evaluator: Evaluator with evaluate(events, context) -> float method.
            context: Optional context dictionary for evaluation.

        Returns:
            List of CandidateScore sorted by score descending.
        """
        context = context or {}
        results = self.simulate_candidates(base_events, candidates)

        scores: List[CandidateScore] = []
        for candidate, result in results:
            try:
                score = evaluator.evaluate(result.events, context)
            except Exception:
                # Graceful fallback for evaluator failures
                score = 0.5

            scores.append(
                CandidateScore(
                    candidate=candidate,
                    result=result,
                    score=score,
                    metadata={"candidate_index": len(scores)},
                )
            )

        # Sort by score descending for easy best selection
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    def get_best_candidate(
        self,
        base_events: List[Event],
        candidates: List[List[Event]],
        evaluator: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Event]]:
        """Get the best scoring candidate.

        Convenience method for when you just need the best action sequence.

        Args:
            base_events: The base event history.
            candidates: List of candidate action sequences.
            evaluator: Evaluator with evaluate(events, context) -> float.
            context: Optional context for evaluation.

        Returns:
            The best scoring candidate events, or None if no candidates.
        """
        scores = self.simulate_and_score(base_events, candidates, evaluator, context)
        if scores:
            return scores[0].candidate
        return None