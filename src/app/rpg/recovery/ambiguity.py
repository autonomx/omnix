"""Phase 6.5 — Ambiguity Policy.

Determines how to handle ambiguous player input based on confidence scoring.

Behavior buckets:
  - high confidence  → auto_resolve
  - medium confidence → narrate_uncertainty
  - low confidence   → request_clarification
"""
from __future__ import annotations

from .models import AmbiguityDecision


class AmbiguityPolicy:
    """Decide how to handle ambiguous player actions."""

    def __init__(
        self,
        auto_resolve_threshold: float = 0.8,
        clarify_threshold: float = 0.45,
    ) -> None:
        self.auto_resolve_threshold = auto_resolve_threshold
        self.clarify_threshold = clarify_threshold

    def decide(
        self,
        parser_result: dict | None = None,
        player_input: str | None = None,
        coherence_summary: dict | None = None,
    ) -> AmbiguityDecision:
        """Return an ambiguity decision based on available signals."""
        confidence = self._confidence_from_parser_result(parser_result)
        if confidence is None:
            confidence = self._confidence_from_input_heuristics(player_input)

        if self._should_auto_resolve(confidence):
            return AmbiguityDecision.AUTO_RESOLVE
        if self._should_request_clarification(confidence):
            return AmbiguityDecision.REQUEST_CLARIFICATION
        return AmbiguityDecision.NARRATE_UNCERTAINTY

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _confidence_from_parser_result(self, parser_result: dict | None) -> float | None:
        """Extract confidence from parser result if available."""
        if parser_result is None:
            return None
        confidence = parser_result.get("confidence")
        if confidence is not None:
            return float(confidence)
        return None

    def _confidence_from_input_heuristics(self, player_input: str | None) -> float:
        """Estimate confidence using simple heuristics on raw input."""
        if not player_input:
            return 0.0
        text = player_input.strip()
        if not text:
            return 0.0
        # Very short / single-word inputs are usually clear commands
        if len(text.split()) <= 2:
            return 0.85
        # Question marks often indicate confusion or meta-queries
        if "?" in text:
            return 0.35
        # Long multi-clause inputs may be ambiguous
        if len(text.split()) > 10:
            return 0.5
        return 0.65

    def _should_auto_resolve(self, confidence: float) -> bool:
        return confidence >= self.auto_resolve_threshold

    def _should_request_clarification(self, confidence: float) -> bool:
        return confidence < self.clarify_threshold

    def _should_narrate_uncertainty(self, confidence: float) -> bool:
        return self.clarify_threshold <= confidence < self.auto_resolve_threshold
