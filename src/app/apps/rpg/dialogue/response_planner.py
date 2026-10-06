"""Phase 8.1 — Dialogue Response Planner.

Deterministic planning layer that turns a DialogueTurnContext into a
structured DialogueResponsePlan.  No UI formatting responsibility —
presentation is handled by the DialoguePresenter.
"""

from __future__ import annotations

from typing import Any

from .acts import (
    map_arc_pressure_to_reveal_level,
    map_npc_outcome_to_primary_act,
    map_relationship_to_stance,
    map_relationship_to_tone,
    normalize_dialogue_act,
)
from .models import DialogueActDecision, DialogueResponsePlan, DialogueTurnContext

# ------------------------------------------------------------------
# Deterministic line templates keyed by primary act
# ------------------------------------------------------------------

_LINE_TEMPLATES: dict[str, str] = {
    "refusal": "I'm not telling you that.",
    "redirect": "You should speak to someone else about that.",
    "threat": "Leave now, or this gets worse.",
    "agreement": "Very well, I can help with that.",
    "offer": "I have a proposal for you.",
    "reveal_hint": "There's something you should know.",
    "reassure": "Don't worry, things will be fine.",
    "warn": "Be careful — you're treading on dangerous ground.",
    "probe": "Tell me more about what you're looking for.",
    "stall": "I need more time before I can say anything.",
    "question": "What exactly do you want from me?",
    "acknowledge": "I hear you.",
}


class DialogueResponsePlanner:
    """Plan structured dialogue responses from turn context."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_act(self, context: DialogueTurnContext) -> DialogueActDecision:
        """Classify the dialogue act from structured state.

        Priority order (explicit and stable):
            1. Blocked / refusal states
            2. Threat / hostility states
            3. Redirect / stall states
            4. Offer / agreement states
            5. Reveal hint if arc permits
            6. Question / probe fallback
        """
        drivers = context.metadata.get("state_drivers", {})
        rel = context.relationship_state

        # NPC agency outcome takes priority when present
        outcome = context.current_action_outcome or ""
        primary_from_outcome = map_npc_outcome_to_primary_act(outcome)

        # 1. Blocked / refusal
        if outcome in ("refuse", "blocked"):
            primary = "refusal"
        # 2. Threat / high hostility
        elif outcome == "threaten" or drivers.get("hostility") == "high":
            primary = "threat"
        # 3. Redirect / stall
        elif outcome == "redirect":
            primary = "redirect"
        elif outcome == "delay":
            primary = "stall"
        # 4. Offer / agreement
        elif outcome in ("agree", "assist"):
            primary = "agreement"
        elif outcome == "offer":
            primary = "offer"
        # 5. Reveal hint if arc permits
        elif drivers.get("reveal_pressure") in ("high", "medium") and drivers.get("trust") != "low":
            primary = "reveal_hint"
        # 6. NPC outcome fallback
        elif primary_from_outcome != "acknowledge":
            primary = primary_from_outcome
        # 7. Question / probe fallback
        elif context.current_intent_type in ("question", "investigate"):
            primary = "probe"
        else:
            primary = "acknowledge"

        primary = normalize_dialogue_act(primary)

        # Secondary acts
        secondary: list[str] = []
        if primary != "reveal_hint" and drivers.get("reveal_pressure") == "high":
            secondary.append("reveal_hint")
        if primary not in ("warn", "threat") and drivers.get("scene_tension") == "high":
            secondary.append("warn")

        tone = self._determine_tone(context, rel, drivers)
        stance = self._determine_stance(context, rel, drivers)
        reveal_level = map_arc_pressure_to_reveal_level(context.arc_context)

        urgency = drivers.get("urgency", "normal")

        return DialogueActDecision(
            primary_act=primary,
            secondary_acts=secondary,
            intent_alignment=context.current_intent_type or "neutral",
            tone=tone,
            stance=stance,
            reveal_level=reveal_level,
            urgency=urgency,
            metadata={"outcome": outcome, "drivers": dict(drivers)},
        )

    def build_plan(self, context: DialogueTurnContext) -> DialogueResponsePlan:
        """Build a complete response plan from context."""
        decision = self.classify_act(context)

        allowed = self._build_allowed_topics(context, decision)
        blocked = self._build_blocked_topics(context, decision)
        hints = self._build_hint_targets(context, decision)
        text_slots = self._build_text_slots(context, decision)
        trace = self._build_trace(context, decision)

        response_id = (
            f"dlg:{context.speaker_id}:{context.listener_id or 'none'}"
            f":{decision.primary_act}"
            f":{context.metadata.get('tick', 'none')}"
        )

        return DialogueResponsePlan(
            response_id=response_id,
            speaker_id=context.speaker_id,
            listener_id=context.listener_id,
            primary_act=decision.primary_act,
            secondary_acts=list(decision.secondary_acts),
            framing={
                "tone": decision.tone,
                "stance": decision.stance,
                "reveal_level": decision.reveal_level,
                "urgency": decision.urgency,
            },
            state_drivers=dict(context.metadata.get("state_drivers", {})),
            allowed_topics=allowed,
            blocked_topics=blocked,
            hint_targets=hints,
            text_slots=text_slots,
            trace=trace,
            metadata={
                "act_decision": decision.to_dict(),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_tone(
        context: DialogueTurnContext,
        rel: dict[str, Any],
        drivers: dict[str, Any],
    ) -> str:
        if rel:
            return map_relationship_to_tone(rel)
        if drivers.get("hostility") == "high":
            return "hostile"
        return "neutral"

    @staticmethod
    def _determine_stance(
        context: DialogueTurnContext,
        rel: dict[str, Any],
        drivers: dict[str, Any],
    ) -> str:
        if rel:
            return map_relationship_to_stance(rel)
        if drivers.get("fear") == "high":
            return "defensive"
        return "neutral"

    @staticmethod
    def _build_allowed_topics(
        context: DialogueTurnContext,
        decision: DialogueActDecision,
    ) -> list[str]:
        """Determine what the NPC may mention."""
        topics: list[str] = []
        if decision.reveal_level in ("medium", "high"):
            for arc in context.arc_context.get("active_arcs", []):
                topics.append(arc.get("arc_id", ""))
        # Location is always safe
        if context.scene_location:
            topics.append(context.scene_location)
        return [t for t in topics if t]

    @staticmethod
    def _build_blocked_topics(
        context: DialogueTurnContext,
        decision: DialogueActDecision,
    ) -> list[str]:
        """Determine what the NPC should avoid mentioning."""
        blocked: list[str] = []
        if decision.reveal_level == "none":
            for arc in context.arc_context.get("active_arcs", []):
                arc_id = arc.get("arc_id", "")
                if arc_id:
                    blocked.append(arc_id)
        return blocked

    @staticmethod
    def _build_hint_targets(
        context: DialogueTurnContext,
        decision: DialogueActDecision,
    ) -> list[str]:
        """Build hint targets from due reveals."""
        if decision.reveal_level not in ("medium", "high"):
            return []
        hints: list[str] = []
        for reveal in context.arc_context.get("due_reveals", []):
            target = reveal.get("reveal_id") or reveal.get("target", "")
            if target:
                hints.append(target)
        return hints

    @staticmethod
    def _build_text_slots(
        context: DialogueTurnContext,
        decision: DialogueActDecision,
    ) -> dict[str, str]:
        """Build deterministic text slots from the plan."""
        line = _LINE_TEMPLATES.get(decision.primary_act, "...")
        summary = f"{decision.primary_act} ({decision.tone}/{decision.stance})"

        # Customize redirect line if we have a target
        if decision.primary_act == "redirect" and context.listener_id:
            line = "Talk to someone else about that."

        return {
            "line": line,
            "summary": summary,
        }

    @staticmethod
    def _build_trace(
        context: DialogueTurnContext,
        decision: DialogueActDecision,
    ) -> dict[str, Any]:
        """Build an explicit trace showing why this act was selected."""
        return {
            "selected_act": decision.primary_act,
            "outcome_source": context.current_action_outcome or "none",
            "drivers": dict(context.metadata.get("state_drivers", {})),
            "relationship_present": bool(context.relationship_state),
            "arc_reveal_level": decision.reveal_level,
            "intent_type": context.current_intent_type,
            "secondary_acts": list(decision.secondary_acts),
        }
