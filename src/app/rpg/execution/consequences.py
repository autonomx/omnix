"""Phase 7.3 — Consequence Builder.

Builds deterministic consequences from mapped action intents.
Only emits supported, meaningful events. Does not invent many new
event types without corresponding reducer support.
"""

from __future__ import annotations

from typing import Any

from .models import ActionConsequence


class ConsequenceBuilder:
    """Build ActionConsequence lists from a mapped action descriptor."""

    def build(
        self,
        mapped_action: dict,
        coherence_core: Any,
        gm_state: Any,
        evaluation: dict | None = None,
    ) -> list[ActionConsequence]:
        evaluation = evaluation or {"outcome": "success", "intensity": "medium", "modifiers": []}
        if evaluation.get("outcome") == "blocked":
            return self._build_blocked_consequences(mapped_action, coherence_core, evaluation)

        resolution_type = mapped_action.get("resolution_type", "")
        builder = {
            "thread_progress": self._build_thread_progress_consequences,
            "social_contact": self._build_social_contact_consequences,
            "location_travel": self._build_location_travel_consequences,
            "recap": self._build_recap_consequences,
        }.get(resolution_type)

        if builder is not None:
            return builder(mapped_action, coherence_core)
        return []

    # ------------------------------------------------------------------
    # Per-type builders
    # ------------------------------------------------------------------

    def _build_thread_progress_consequences(
        self, mapped_action: dict, coherence_core: Any
    ) -> list[ActionConsequence]:
        target_id = mapped_action.get("target_id") or "unknown_thread"
        return [
            self._make_consequence(
                consequence_id=f"cons:thread_progressed:{target_id}",
                consequence_type="thread_progressed",
                summary=f"Progressed investigation on thread {target_id}",
                event_type="thread_progressed",
                payload={
                    "thread_id": target_id,
                    "source": "action_resolver",
                },
            ),
        ]

    def _build_social_contact_consequences(
        self, mapped_action: dict, coherence_core: Any
    ) -> list[ActionConsequence]:
        target_id = mapped_action.get("target_id") or "unknown_npc"
        return [
            self._make_consequence(
                consequence_id=f"cons:npc_interaction:{target_id}",
                consequence_type="npc_interaction_started",
                summary=f"Started interaction with {target_id}",
                event_type="npc_interaction_started",
                payload={
                    "npc_id": target_id,
                    "source": "action_resolver",
                },
            ),
        ]

    def _build_location_travel_consequences(
        self, mapped_action: dict, coherence_core: Any
    ) -> list[ActionConsequence]:
        target_id = mapped_action.get("target_id") or "unknown_location"
        return [
            self._make_consequence(
                consequence_id=f"cons:scene_transition:{target_id}",
                consequence_type="scene_transition_requested",
                summary=f"Requested scene transition to {target_id}",
                event_type="scene_transition_requested",
                payload={
                    "location": target_id,
                    "source": "action_resolver",
                },
            ),
        ]

    def _build_recap_consequences(
        self, mapped_action: dict, coherence_core: Any
    ) -> list[ActionConsequence]:
        return [
            self._make_consequence(
                consequence_id="cons:recap_requested",
                consequence_type="recap_requested",
                summary="Player requested a recap of the current situation",
                event_type="recap_requested",
                payload={
                    "source": "action_resolver",
                },
            ),
        ]

    # ------------------------------------------------------------------
    # Factory helper
    # ------------------------------------------------------------------

    def _make_consequence(
        self,
        consequence_id: str,
        consequence_type: str,
        summary: str,
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> ActionConsequence:
        return ActionConsequence(
            consequence_id=consequence_id,
            consequence_type=consequence_type,
            summary=summary,
            event_type=event_type,
            payload=dict(payload),
            metadata=dict(metadata or {}),
        )

    # ------------------------------------------------------------------
    # Blocked consequence builder
    # ------------------------------------------------------------------

    def _build_blocked_consequences(
        self,
        mapped_action: dict,
        coherence_core: Any,
        evaluation: dict,
    ) -> list[ActionConsequence]:
        target_id = mapped_action.get("target_id")
        intent_type = mapped_action.get("intent_type", "unknown")
        reason = ",".join(evaluation.get("modifiers", []) or []) or "constraints_not_met"
        return [
            self._make_consequence(
                consequence_id=f"blocked:{intent_type}:{target_id or 'none'}",
                consequence_type="action_blocked",
                summary=f"Action '{intent_type}' could not proceed.",
                event_type="action_blocked",
                payload={
                    "intent_type": intent_type,
                    "target_id": target_id,
                    "reason": reason,
                },
                metadata={"evaluation": dict(evaluation)},
            )
        ]
