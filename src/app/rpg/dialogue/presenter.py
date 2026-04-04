"""Phase 8.1 — Dialogue Presenter.

Convert a DialogueResponsePlan into UI-safe payloads.
Strip internal reasoning details not meant for player UI.
Optionally produce GM-safe trace separately.

Read-only — no mutation of any upstream state.
"""

from __future__ import annotations

from typing import Any

from .acts import SUPPORTED_DIALOGUE_ACTS
from .models import DialogueLogEntry, DialoguePresentation, DialogueResponsePlan


# Acts considered meaningful enough to produce a journal log entry.
_JOURNALABLE_ACTS = frozenset({
    "refusal",
    "threat",
    "offer",
    "reveal_hint",
    "agreement",
    "redirect",
    "warn",
})


class DialoguePresenter:
    """Present dialogue plans as player-safe or GM-safe payloads."""

    def present_response(self, plan: DialogueResponsePlan) -> dict:
        """Return a player-safe payload from the plan.

        Strips internal reasoning details (trace, state_drivers, blocked_topics).
        """
        framing = plan.framing or {}
        text_slots = plan.text_slots or {}

        presentation = DialoguePresentation(
            speaker_id=plan.speaker_id,
            listener_id=plan.listener_id,
            act=plan.primary_act,
            tone=framing.get("tone", "neutral"),
            stance=framing.get("stance", "neutral"),
            summary=text_slots.get("summary", ""),
            line=text_slots.get("line", ""),
            choices_hint=list(plan.hint_targets),
        )
        result = presentation.to_dict()
        result["hinted_topics"] = list(plan.hint_targets)
        result["interaction_flags"] = {
            "urgency": framing.get("urgency", "normal"),
            "reveal_level": framing.get("reveal_level", "none"),
        }
        return result

    def present_trace(self, plan: DialogueResponsePlan) -> dict:
        """Return a structured trace for GM/debug use (Phase 8.4)."""
        return {
            "primary_act": plan.primary_act,
            "secondary_acts": list(plan.secondary_acts),
            "state_drivers": dict(plan.state_drivers),
            "decision_reasons": dict(plan.trace),
            "reveal_policy": {
                "reveal_level": plan.framing.get("reveal_level", "none"),
                "allowed_topics": list(plan.allowed_topics),
                "blocked_topics": list(plan.blocked_topics),
                "hint_targets": list(plan.hint_targets),
            },
        }

    def present_log_entry(
        self,
        plan: DialogueResponsePlan,
        tick: int | None = None,
    ) -> dict | None:
        """Return a memory/journal log entry dict, or None if not journalable.

        Only meaningful interaction classes produce a log entry.
        """
        if plan.primary_act not in _JOURNALABLE_ACTS:
            return None

        entry = DialogueLogEntry(
            entry_id=f"dialogue_log:{plan.response_id}",
            tick=tick,
            speaker_id=plan.speaker_id,
            listener_id=plan.listener_id,
            act=plan.primary_act,
            outcome=plan.framing.get("tone", "neutral"),
            summary=plan.text_slots.get("summary", ""),
            line=plan.text_slots.get("line", ""),
            metadata={
                "response_id": plan.response_id,
                "secondary_acts": list(plan.secondary_acts),
            },
        )
        return entry.to_dict()
