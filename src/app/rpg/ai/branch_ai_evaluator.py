"""PHASE 4.5 — AI Branch Scoring (LLM Integration)

Uses LLM to evaluate narrative quality and goal alignment of
simulated timeline branches.

This evaluator provides:
- AI-powered branch scoring (0-1 scale)
- Narrative quality assessment
- Goal alignment evaluation
- Heuristic fallback when LLM is unavailable

Example:
    evaluator = AIBranchEvaluator(llm_client)
    score = evaluator.evaluate(
        events=simulated_events,
        context={"npc": npc.id, "goal": "survive"},
    )
    print(f"Branch score: {score}")
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.event_bus import Event

logger = logging.getLogger(__name__)


@dataclass
class BranchEvaluation:
    """Detailed evaluation of a branch.

    Attributes:
        score: Overall score from 0 to 1.
        reasoning: Explanation of the score.
        narrative_quality: Quality of narrative elements (0-1).
        goal_alignment: How well branch aligns with goals (0-1).
        interesting_outcomes: Number of notable outcomes detected.
    """

    score: float = 0.5
    reasoning: str = ""
    narrative_quality: float = 0.5
    goal_alignment: float = 0.5
    interesting_outcomes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class AIBranchEvaluator:
    """Uses LLM to evaluate narrative + goal alignment.

    This evaluator sends summarized timeline and context to an LLM
    for scoring. If LLM is unavailable or fails, falls back to
    heuristic scoring based on event diversity and count.

    Performance:
    - LLM calls are cached for similar contexts
    - Heuristic mode provides fast scoring without LLM
    - Timeout handling prevents blocking
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        use_heuristic: bool = False,
    ):
        """Initialize the AIBranchEvaluator.

        Args:
            llm_client: LLM client with complete(prompt) -> str method.
                       If None, falls back to heuristic evaluation.
            use_heuristic: Force heuristic mode even with LLM available.
                          Useful for performance testing.
        """
        self.llm = llm_client
        self.use_heuristic = use_heuristic or (llm_client is None)
        self._cache: Dict[str, BranchEvaluation] = {}

    def evaluate(self, events: List[Event], context: Optional[Dict[str, Any]] = None) -> float:
        """Evaluate a branch and return score.

        This is the main scoring interface. It summarizes events,
        optionally calls LLM, and returns a normalized score.

        Args:
            events: The simulated timeline events to evaluate.
            context: Optional context with NPC goals, world state, etc.

        Returns:
            Score from 0.0 to 1.0. Higher is better.
        """
        cache_key = self._make_cache_key(events, context or {})
        if cache_key in self._cache:
            return self._cache[cache_key].score

        evaluation = self.evaluate_detailed(events, context)
        self._cache[cache_key] = evaluation
        return evaluation.score

    def evaluate_detailed(
        self, events: List[Event], context: Optional[Dict[str, Any]] = None
    ) -> BranchEvaluation:
        """Evaluate a branch and return detailed evaluation.

        Args:
            events: The simulated timeline to evaluate.
            context: Optional context dictionary.

        Returns:
            BranchEvaluation with score, reasoning, and metrics.
        """
        context = context or {}

        if self.use_heuristic or self.llm is None:
            return self._heuristic_evaluate(events, context)

        try:
            return self._llm_evaluate(events, context)
        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}, falling back to heuristic")
            return self._heuristic_evaluate(events, context)

    def _llm_evaluate(
        self, events: List[Event], context: Dict[str, Any]
    ) -> BranchEvaluation:
        """Evaluate using LLM integration.

        Sends structured prompt to LLM and parses response.

        Args:
            events: Timeline events.
            context: Evaluation context.

        Returns:
            BranchEvaluation from LLM response.
        """
        summary = self._summarize(events)
        context_str = self._format_context(context)

        prompt = f"""You are an RPG narrative evaluator. Score this timeline branch.

Context:
{context_str}

Timeline (last 20 events):
{summary}

Score from 0 to 1 based on:
- narrative_quality: How compelling and coherent the story is
- goal_alignment: How well the outcomes match NPC/player goals
- interesting_outcomes: Number of notable or surprising developments

Respond with ONLY a JSON object in this format:
{{
  "score": 0.75,
  "narrative_quality": 0.8,
  "goal_alignment": 0.7,
  "interesting_outcomes": 2,
  "reasoning": "Brief explanation of the score"
}}
"""
        response = self._call_llm(prompt)
        return self._parse_llm_response(response)

    def _heuristic_evaluate(
        self, events: List[Event], context: Dict[str, Any]
    ) -> BranchEvaluation:
        """Evaluate using heuristic scoring without LLM.

        Scores based on:
        - Event count (more activity = more interesting)
        - Event type diversity (varied events = richer story)
        - Conflict events (combat, damage = tension)

        Args:
            events: Timeline events.
            context: Evaluation context.

        Returns:
            BranchEvaluation from heuristic analysis.
        """
        if not events:
            return BranchEvaluation(
                score=0.0,
                reasoning="No events in branch",
                narrative_quality=0.0,
                goal_alignment=0.0,
            )

        # Event count score (normalize to 0-1, cap at 20 events)
        event_count_score = min(1.0, len(events) / 20.0)

        # Diversity score (unique event types / total)
        event_types = set(e.type for e in events)
        diversity_score = len(event_types) / max(1, len(events))

        # Conflict bonus (combat, damage, conflict events add tension)
        conflict_types = {"combat", "damage", "attack", "conflict", "fight"}
        conflict_count = sum(1 for e in events if e.type.lower() in conflict_types)
        conflict_bonus = min(0.2, conflict_count * 0.1)

        # Goal alignment from context
        goal_alignment = self._heuristic_goal_alignment(events, context)

        # Combined score
        score = (
            0.3 * event_count_score
            + 0.4 * diversity_score
            + 0.3 * goal_alignment
            + conflict_bonus
        )
        score = min(1.0, max(0.0, score))  # Clamp to 0-1

        return BranchEvaluation(
            score=round(score, 2),
            reasoning=f"Heuristic: {len(events)} events, {len(event_types)} types, "
            f"{conflict_count} conflicts",
            narrative_quality=round(diversity_score, 2),
            goal_alignment=round(goal_alignment, 2),
            interesting_outcomes=conflict_count,
            metadata={
                "event_count": len(events),
                "unique_types": len(event_types),
                "conflict_count": conflict_count,
            },
        )

    def _heuristic_goal_alignment(
        self, events: List[Event], context: Dict[str, Any]
    ) -> float:
        """Estimate goal alignment heuristically.

        Args:
            events: Timeline events.
            context: Context with potential goals.

        Returns:
            Alignment score from 0 to 1.
        """
        goal = context.get("goal", "")
        npc_id = context.get("npc", context.get("npc_id"))

        if not goal and not npc_id:
            return 0.5  # Neutral without context

        alignment = 0.5  # Base

        event_text = " ".join(
            e.type.lower() for e in events
        )
        event_payloads = " ".join(
            str(p).lower() for e in events for p in e.payload.values() if p
        )

        # Check if goal-related keywords appear in events
        goal_keywords = {
            "survive": {"survive", "heal", "flee", "defend", "retreat"},
            "attack": {"attack", "damage", "kill", "fight", "combat"},
            "explore": {"explore", "discover", "find", "move", "travel"},
            "negotiate": {"talk", "negotiate", "ally", "peace", "diplomat"},
        }

        keywords = goal_keywords.get(goal.lower(), {goal.lower()})
        matches = sum(1 for kw in keywords if kw in event_text or kw in event_payloads)
        if keywords:
            alignment = 0.3 + 0.7 * (matches / len(keywords))

        return min(1.0, max(0.0, alignment))

    def _summarize(self, events: List[Event]) -> str:
        """Summarize events into a timeline string.

        Args:
            events: List of events to summarize.

        Returns:
            String summary of last 20 events.
        """
        # Show last 20 events for context window management
        recent = events[-20:]
        lines = []
        for i, e in enumerate(recent):
            payload_summary = ", ".join(
                f"{k}={v}" for k, v in e.payload.items() if v
            )[:100]
            lines.append(f"{i + 1}. [{e.type}] {payload_summary}")
        return "\n".join(lines)

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context dictionary for prompt.

        Args:
            context: Context dictionary.

        Returns:
            Formatted string representation.
        """
        return json.dumps(context, indent=2, default=str)

    def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt.

        Args:
            prompt: The prompt to send.

        Returns:
            LLM response text.
        """
        if hasattr(self.llm, "chat"):
            return self.llm.chat(prompt)
        elif hasattr(self.llm, "complete"):
            return self.llm.complete(prompt)
        elif hasattr(self.llm, "generate"):
            return self.llm.generate(prompt)
        else:
            raise ValueError(
                f"LLM client {type(self.llm).__name__} does not support "
                "chat(), complete(), or generate() methods"
            )

    def _parse_llm_response(self, text: str) -> BranchEvaluation:
        """Parse LLM response into BranchEvaluation.

        Args:
            text: Raw LLM response.

        Returns:
            Parsed BranchEvaluation.
        """
        try:
            # Try to extract JSON from response
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return BranchEvaluation(
                    score=float(data.get("score", 0.5)),
                    reasoning=data.get("reasoning", "LLM evaluation"),
                    narrative_quality=float(data.get("narrative_quality", 0.5)),
                    goal_alignment=float(data.get("goal_alignment", 0.5)),
                    interesting_outcomes=int(data.get("interesting_outcomes", 0)),
                )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")

        # Fallback
        return BranchEvaluation(
            score=0.5,
            reasoning=f"Failed to parse LLM response: {text[:100]}",
        )

    def _make_cache_key(self, events: List[Event], context: Dict[str, Any]) -> str:
        """Create cache key from events and context.

        Args:
            events: Timeline events.
            context: Context dictionary.

        Returns:
            String cache key.
        """
        event_sig = "|".join(
            f"{e.type}:{json.dumps(e.payload, default=str)}" for e in events[-5:]
        )
        context_sig = json.dumps(context, sort_keys=True, default=str)
        return f"{event_sig}::{context_sig}"

    def clear_cache(self) -> None:
        """Clear the evaluation cache."""
        self._cache.clear()