"""Phase 7.4 — NPC Decision Policy.

Deterministic NPC decision engine. No randomness. No LLM calls.
Decides NPC outcome from structured context using simple threshold logic.
"""

from __future__ import annotations

from .models import NPCDecisionContext, NPCDecisionResult

# Thresholds for deterministic decision branching
_HOSTILITY_THRESHOLD = 0.4
_FEAR_THRESHOLD = 0.4
_TRUST_THRESHOLD = 0.3
_RESPECT_THRESHOLD = 0.3
_PRESSURE_THRESHOLD = 0.5


class NPCDecisionPolicy:
    """Deterministic NPC decision policy."""

    def decide(self, context: NPCDecisionContext) -> NPCDecisionResult:
        """Decide NPC outcome from context. No randomness."""
        if context.intent_type == "talk_to_npc":
            return self._decide_talk_to_npc(context)
        return self._default_result(context)

    def _decide_talk_to_npc(self, context: NPCDecisionContext) -> NPCDecisionResult:
        """Core social decision logic for talk_to_npc interactions."""
        base_outcome = self._relationship_bias(context)
        base_outcome = self._apply_gm_focus_modifiers(context, base_outcome)
        base_outcome = self._apply_pacing_modifiers(context, base_outcome)

        modifiers: list[str] = []
        if context.relationship:
            if context.relationship.hostility >= _HOSTILITY_THRESHOLD:
                modifiers.append("high_hostility")
            if context.relationship.fear >= _FEAR_THRESHOLD:
                modifiers.append("high_fear")
            if context.relationship.trust >= _TRUST_THRESHOLD:
                modifiers.append("trusting")
            if context.relationship.respect >= _RESPECT_THRESHOLD:
                modifiers.append("respectful")

        response_type = _OUTCOME_TO_RESPONSE_TYPE.get(
            base_outcome, "social_agreement"
        )

        return NPCDecisionResult(
            npc_id=context.npc_id,
            outcome=base_outcome,
            response_type=response_type,
            summary=f"NPC {context.npc_id} decided to {base_outcome}",
            emitted_event_types=[_OUTCOME_TO_EVENT_TYPE.get(
                base_outcome, "npc_response_agreed"
            )],
            modifiers=modifiers,
        )

    def _apply_gm_focus_modifiers(
        self, context: NPCDecisionContext, base_outcome: str
    ) -> str:
        """Apply GM focus/directive modifiers to the outcome."""
        gm_context = context.gm_context
        if not gm_context:
            return base_outcome

        focus_target = gm_context.get("focus_target")
        if focus_target and focus_target == context.npc_id:
            if base_outcome in ("refuse", "delay"):
                return "redirect"
            if base_outcome == "agree":
                return "assist"
        return base_outcome

    def _apply_pacing_modifiers(
        self, context: NPCDecisionContext, base_outcome: str
    ) -> str:
        """Apply pacing pressure modifiers to the outcome."""
        pacing = context.pacing
        if not pacing:
            return base_outcome

        pressure = float(pacing.get("social_pressure", 0.0))
        if pressure >= _PRESSURE_THRESHOLD:
            if base_outcome == "agree":
                return "delay"
            if base_outcome == "assist":
                return "suspicious"
        return base_outcome

    def _relationship_bias(self, context: NPCDecisionContext) -> str:
        """Determine base outcome from relationship state."""
        if context.relationship is None:
            return "agree"

        rel = context.relationship

        # High hostility + fear → threaten
        if (
            rel.hostility >= _HOSTILITY_THRESHOLD
            and rel.fear >= _FEAR_THRESHOLD
        ):
            return "threaten"

        # High hostility → refuse
        if rel.hostility >= _HOSTILITY_THRESHOLD:
            return "refuse"

        # High fear alone → delay
        if rel.fear >= _FEAR_THRESHOLD:
            return "delay"

        # Positive trust or respect → assist or agree
        if rel.trust >= _TRUST_THRESHOLD and rel.respect >= _RESPECT_THRESHOLD:
            return "assist"
        if rel.trust >= _TRUST_THRESHOLD:
            return "agree"

        # Neutral default
        return "agree"

    def _default_result(self, context: NPCDecisionContext) -> NPCDecisionResult:
        """Fallback result for non-social intents."""
        return NPCDecisionResult(
            npc_id=context.npc_id,
            outcome="agree",
            response_type="social_agreement",
            summary=f"NPC {context.npc_id} agreed by default",
            emitted_event_types=["npc_response_agreed"],
            modifiers=["default"],
        )


# Mapping from outcome to response type
_OUTCOME_TO_RESPONSE_TYPE: dict[str, str] = {
    "agree": "social_agreement",
    "refuse": "social_refusal",
    "delay": "social_delay",
    "threaten": "social_threat",
    "assist": "social_offer",
    "suspicious": "social_delay",
    "redirect": "social_redirect",
}

# Mapping from outcome to event type
_OUTCOME_TO_EVENT_TYPE: dict[str, str] = {
    "agree": "npc_response_agreed",
    "refuse": "npc_response_refused",
    "delay": "npc_response_delayed",
    "threaten": "npc_response_threatened",
    "assist": "npc_response_agreed",
    "suspicious": "npc_response_delayed",
    "redirect": "npc_response_redirected",
}
