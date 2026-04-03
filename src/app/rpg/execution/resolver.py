"""Phase 7.3 — Action Resolver.

Main entry point for resolving a selected ChoiceOption into deterministic
events. Does NOT directly call coherence methods — returns events only.
"""

from __future__ import annotations

from typing import Any, Optional

from .consequences import ConsequenceBuilder
from .intent_mapping import ActionIntentMapper
from .models import (
    ActionConsequence,
    ActionResolutionResult,
    ResolvedAction,
    SceneTransition,
)
from .transitions import SceneTransitionBuilder


# Supported event types that this resolver may emit.
SUPPORTED_EVENT_TYPES = frozenset({
    "thread_progressed",
    "npc_interaction_started",
    "scene_transition_requested",
    "recap_requested",
})


class ActionResolver:
    """Resolve a selected ChoiceOption into structured events."""

    def __init__(
        self,
        intent_mapper: Optional[ActionIntentMapper] = None,
        consequence_builder: Optional[ConsequenceBuilder] = None,
        transition_builder: Optional[SceneTransitionBuilder] = None,
    ) -> None:
        self.intent_mapper = intent_mapper or ActionIntentMapper()
        self.consequence_builder = consequence_builder or ConsequenceBuilder()
        self.transition_builder = transition_builder or SceneTransitionBuilder()

    def resolve_choice(
        self,
        option: Any,
        coherence_core: Any,
        gm_state: Any,
    ) -> ActionResolutionResult:
        """Resolve a player-selected option into an ActionResolutionResult.

        Steps:
            1. Map option intent
            2. Build consequences
            3. Build scene transition if needed
            4. Transform consequences + transition into event list
            5. Return structured ActionResolutionResult
        """
        # 1. Map intent
        mapped = self.intent_mapper.map_option(option)

        # 2. Build consequences
        consequences = self.consequence_builder.build(
            mapped_action=mapped,
            coherence_core=coherence_core,
            gm_state=gm_state,
        )

        # 3. Build transition
        transition = self.transition_builder.build(
            mapped_action=mapped,
            coherence_core=coherence_core,
        )

        # 4. Build events
        events = self._build_events(consequences, transition)

        # 5. Assemble result
        option_id = self._get_field(option, "option_id", "unknown")
        action_id = self._resolved_action_id(option)

        resolved = ResolvedAction(
            action_id=action_id,
            option_id=option_id,
            intent_type=mapped.get("intent_type", "unknown"),
            target_id=mapped.get("target_id"),
            summary=mapped.get("summary", ""),
            consequences=consequences,
            transition=transition,
        )

        return ActionResolutionResult(
            resolved_action=resolved,
            events=events,
            trace={
                "mapped_action": mapped,
                "consequence_count": len(consequences),
                "has_transition": transition is not None,
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolved_action_id(self, option: Any) -> str:
        """Generate a deterministic action ID from the option."""
        option_id = self._get_field(option, "option_id", "unknown")
        intent_type = self._get_field(option, "intent_type", "unknown")
        target_id = self._get_field(option, "target_id", "none")
        return f"action:{intent_type}:{option_id}:{target_id}"

    def _build_events(
        self,
        consequences: list[ActionConsequence],
        transition: Optional[SceneTransition],
    ) -> list[dict]:
        """Transform consequences and transition into a flat event list."""
        events: list[dict] = []

        for consequence in consequences:
            events.append({
                "type": consequence.event_type,
                "payload": dict(consequence.payload),
            })

        if transition is not None:
            events.append({
                "type": "scene_transition_requested",
                "payload": {
                    "from_location": transition.from_location,
                    "to_location": transition.to_location,
                    "transition_id": transition.transition_id,
                    "source": "action_resolver",
                },
            })

        return events

    @staticmethod
    def _get_field(option: Any, field: str, default: Any = None) -> Any:
        if isinstance(option, dict):
            return option.get(field, default)
        return getattr(option, field, default)
