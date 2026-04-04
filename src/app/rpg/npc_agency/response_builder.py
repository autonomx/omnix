"""Phase 7.4 — NPC Response Builder.

Converts NPCDecisionResult into structured action consequence events.
All events follow the standard event bus format.
"""

from __future__ import annotations

from .models import NPCDecisionResult


# Supported NPC response event types
SUPPORTED_NPC_EVENT_TYPES = frozenset({
    "npc_interaction_started",
    "npc_response_agreed",
    "npc_response_refused",
    "npc_response_delayed",
    "npc_response_threatened",
    "npc_response_redirected",
})


class NPCResponseBuilder:
    """Build structured events from an NPC decision result."""

    def build_events(
        self, decision: NPCDecisionResult, mapped_action: dict
    ) -> list[dict]:
        """Convert a decision result into emittable events."""
        outcome = decision.outcome
        builder = {
            "agree": self._build_agree_events,
            "assist": self._build_assist_events,
            "refuse": self._build_refuse_events,
            "delay": self._build_delay_events,
            "threaten": self._build_threat_events,
            "suspicious": self._build_delay_events,
            "redirect": self._build_redirect_events,
        }.get(outcome, self._build_agree_events)

        events = builder(decision, mapped_action)

        # Enforce event whitelist (Phase 7.4 safety)
        for e in events:
            if e.get("type") not in SUPPORTED_NPC_EVENT_TYPES:
                raise ValueError(f"Unsupported NPC response event: {e.get('type')}")

        return events

    def _build_agree_events(
        self, decision: NPCDecisionResult, mapped_action: dict
    ) -> list[dict]:
        npc_id = decision.npc_id
        return [
            self._make_event(
                "npc_interaction_started",
                npc_id=npc_id,
                source="npc_agency",
                mapped_action=mapped_action,
            ),
            self._make_event(
                "npc_response_agreed",
                npc_id=npc_id,
                source="npc_agency",
                summary=decision.summary,
                outcome=decision.outcome,
                modifiers=decision.modifiers,
            ),
        ]

    def _build_refuse_events(
        self, decision: NPCDecisionResult, mapped_action: dict
    ) -> list[dict]:
        npc_id = decision.npc_id
        return [
            self._make_event(
                "npc_interaction_started",
                npc_id=npc_id,
                source="npc_agency",
                mapped_action=mapped_action,
            ),
            self._make_event(
                "npc_response_refused",
                npc_id=npc_id,
                source="npc_agency",
                summary=decision.summary,
                outcome=decision.outcome,
                modifiers=decision.modifiers,
            ),
        ]

    def _build_delay_events(
        self, decision: NPCDecisionResult, mapped_action: dict
    ) -> list[dict]:
        npc_id = decision.npc_id
        return [
            self._make_event(
                "npc_interaction_started",
                npc_id=npc_id,
                source="npc_agency",
                mapped_action=mapped_action,
            ),
            self._make_event(
                "npc_response_delayed",
                npc_id=npc_id,
                source="npc_agency",
                summary=decision.summary,
                outcome=decision.outcome,
                modifiers=decision.modifiers,
            ),
        ]

    def _build_threat_events(
        self, decision: NPCDecisionResult, mapped_action: dict
    ) -> list[dict]:
        npc_id = decision.npc_id
        return [
            self._make_event(
                "npc_interaction_started",
                npc_id=npc_id,
                source="npc_agency",
                mapped_action=mapped_action,
            ),
            self._make_event(
                "npc_response_threatened",
                npc_id=npc_id,
                source="npc_agency",
                summary=decision.summary,
                outcome=decision.outcome,
                modifiers=decision.modifiers,
            ),
        ]

    def _build_assist_events(
        self, decision: NPCDecisionResult, mapped_action: dict
    ) -> list[dict]:
        npc_id = decision.npc_id
        return [
            self._make_event(
                "npc_interaction_started",
                npc_id=npc_id,
                source="npc_agency",
                mapped_action=mapped_action,
            ),
            self._make_event(
                "npc_response_agreed",
                npc_id=npc_id,
                source="npc_agency",
                summary=decision.summary,
                outcome=decision.outcome,
                modifiers=decision.modifiers,
            ),
        ]

    def _build_redirect_events(
        self, decision: NPCDecisionResult, mapped_action: dict
    ) -> list[dict]:
        npc_id = decision.npc_id
        return [
            self._make_event(
                "npc_interaction_started",
                npc_id=npc_id,
                source="npc_agency",
                mapped_action=mapped_action,
            ),
            self._make_event(
                "npc_response_redirected",
                npc_id=npc_id,
                source="npc_agency",
                summary=decision.summary,
                outcome=decision.outcome,
                modifiers=decision.modifiers,
            ),
        ]

    @staticmethod
    def _make_event(event_type: str, **payload_fields: object) -> dict:
        """Create a standard event dict."""
        return {
            "type": event_type,
            "payload": {k: v for k, v in payload_fields.items()},
        }
