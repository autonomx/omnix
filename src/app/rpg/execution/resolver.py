"""Phase 7.3 / 7.4 / 7.5 / 7.6 / 8.1 — Action Resolver.

Main entry point for resolving a selected ChoiceOption into deterministic
events. Does NOT directly call coherence methods — returns events only.

Phase 7.4 addition: social_contact resolution delegates to NPCAgencyEngine
for decision-driven NPC interaction outcomes.

Phase 7.5 addition: group dynamics metadata preserved in resolved action
metadata and trace.

Phase 7.6 addition: optional social_state_core parameter for passing
persistent social state into NPC agency resolution.

Phase 8.1 addition: optional dialogue_core for structured dialogue response
planning attached to resolved action metadata.
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
    "action_blocked",
    # Phase 7.4 — NPC agency response event types
    "npc_response_agreed",
    "npc_response_refused",
    "npc_response_delayed",
    "npc_response_threatened",
    "npc_response_redirected",
    # Phase 7.5 — Group dynamics event types
    "npc_secondary_supported",
    "npc_secondary_opposed",
    "npc_secondary_observed",
    "rumor_seeded",
})


class ActionResolver:
    """Resolve a selected ChoiceOption into structured events."""

    def __init__(
        self,
        intent_mapper: Optional[ActionIntentMapper] = None,
        consequence_builder: Optional[ConsequenceBuilder] = None,
        transition_builder: Optional[SceneTransitionBuilder] = None,
        npc_agency_engine: Optional[Any] = None,
        dialogue_core: Optional[Any] = None,
        encounter_controller: Optional[Any] = None,
    ) -> None:
        self.intent_mapper = intent_mapper or ActionIntentMapper()
        self.consequence_builder = consequence_builder or ConsequenceBuilder()
        self.transition_builder = transition_builder or SceneTransitionBuilder()
        self.npc_agency_engine = npc_agency_engine
        self.dialogue_core = dialogue_core
        self.encounter_controller = encounter_controller

    def resolve_choice(
        self,
        option: Any,
        coherence_core: Any,
        gm_state: Any,
        social_state_core: Any | None = None,
        arc_control_controller: Any | None = None,
        campaign_memory_core: Any | None = None,
        scene_summary: dict | None = None,
        tick: int | None = None,
    ) -> ActionResolutionResult:
        """Resolve a player-selected option into an ActionResolutionResult.

        Steps:
            1. Map option intent
            2. Evaluate constraints
            3. Evaluate resolution
            4. For social_contact: delegate to NPC agency engine (Phase 7.4)
            5. Build consequences (with evaluation context)
            6. Build scene transition if needed (not for blocked actions)
            7. Transform consequences + transition into event list
            8. Return structured ActionResolutionResult
        """
        # 1. Map intent
        mapped_action = self.intent_mapper.map_option(option)

        # 2. Evaluate constraints
        constraint_evaluation = self._validate_constraints(option, coherence_core)

        # 3. Evaluate resolution
        evaluation = self._evaluate_resolution(
            mapped_action, coherence_core, gm_state, constraint_evaluation
        )

        # 4. Phase 7.4 — Delegate social_contact to NPC agency
        if (
            evaluation.get("outcome") != "blocked"
            and mapped_action.get("resolution_type") == "social_contact"
            and self.npc_agency_engine is not None
        ):
            return self._resolve_social_contact(
                option, mapped_action, coherence_core, gm_state,
                constraint_evaluation, evaluation,
                social_state_core=social_state_core,
                arc_control_controller=arc_control_controller,
                campaign_memory_core=campaign_memory_core,
                scene_summary=scene_summary,
                tick=tick,
            )

        # 5. Build consequences
        consequences = self.consequence_builder.build(
            mapped_action=mapped_action,
            coherence_core=coherence_core,
            gm_state=gm_state,
            evaluation=evaluation,
        )

        # 6. Build transition (only for non-blocked actions)
        transition = None
        if evaluation.get("outcome") != "blocked":
            transition = self.transition_builder.build(
                mapped_action=mapped_action,
                coherence_core=coherence_core,
            )

        # 7. Build events
        events = self._build_events(consequences, transition)

        # 8. Assemble result
        option_id = self._get_field(option, "option_id", "unknown")
        action_id = self._resolved_action_id(option)

        result_metadata: dict[str, Any] = {
            "mapped_action": dict(mapped_action),
            "evaluation": dict(evaluation),
        }

        # Phase 8.2 — Attach encounter context to resolved action metadata
        enc_ctrl = self.encounter_controller
        if enc_ctrl is not None and hasattr(enc_ctrl, "has_active_encounter") and enc_ctrl.has_active_encounter():
            enc_state = enc_ctrl.get_active_encounter()
            if enc_state is not None:
                result_metadata["encounter_id"] = enc_state.encounter_id
                result_metadata["encounter_mode"] = enc_state.mode
            # Propagate encounter_action_type from option metadata
            opt_meta = self._get_field(option, "metadata", {}) or {}
            if isinstance(opt_meta, dict) and opt_meta.get("encounter_action_type"):
                result_metadata["encounter_action_type"] = opt_meta["encounter_action_type"]

        resolved = ResolvedAction(
            action_id=action_id,
            option_id=option_id,
            intent_type=mapped_action.get("intent_type", "unknown"),
            target_id=mapped_action.get("target_id"),
            summary=mapped_action.get("summary", ""),
            outcome=evaluation.get("outcome", "success"),
            consequences=consequences,
            transition=transition,
            metadata=result_metadata,
        )

        return ActionResolutionResult(
            resolved_action=resolved,
            events=events,
            trace={
                "mapped_action": dict(mapped_action),
                "constraint_evaluation": dict(constraint_evaluation),
                "evaluation": dict(evaluation),
                "event_types": [e.get("type") for e in events],
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
        """Transform consequences and transition into a flat event list.

        Transition metadata is merged into the existing scene_transition_requested
        event from consequences (if present) rather than emitting a duplicate.
        """
        events: list[dict] = []

        for consequence in consequences:
            event: dict = {
                "type": consequence.event_type,
                "payload": dict(consequence.payload),
            }
            self._validate_event(event)
            # Enrich scene_transition_requested with transition details
            if (
                transition is not None
                and consequence.event_type == "scene_transition_requested"
            ):
                event["payload"]["from_location"] = transition.from_location
                event["payload"]["to_location"] = transition.to_location
                event["payload"]["transition_id"] = transition.transition_id
            events.append(event)

        return events

    def _validate_constraints(self, option: Any, coherence_core: Any) -> dict:
        """Validate option constraints against the current coherence state.

        Returns a dict with 'allowed' (bool) and 'reasons' (list[str]).
        """
        constraints = (
            option.get("constraints", [])
            if isinstance(option, dict)
            else getattr(option, "constraints", [])
        )
        if not constraints:
            return {"allowed": True, "reasons": []}

        reasons: list[str] = []
        for constraint in constraints:
            if isinstance(constraint, dict):
                constraint_type = constraint.get("constraint_type")
                value = constraint.get("value")
            else:
                constraint_type = getattr(constraint, "constraint_type", None)
                value = getattr(constraint, "value", None)

            if constraint_type == "requires_thread":
                thread_ids = {
                    t.get("thread_id") for t in coherence_core.get_unresolved_threads()
                }
                if value not in thread_ids:
                    reasons.append(f"missing_thread:{value}")
            elif constraint_type == "requires_location":
                scene = coherence_core.get_scene_summary() or {}
                if scene.get("location") != value:
                    reasons.append(f"wrong_location:{value}")

        return {"allowed": not reasons, "reasons": reasons}

    def _evaluate_resolution(
        self,
        mapped_action: dict,
        coherence_core: Any,
        gm_state: Any,
        constraint_evaluation: dict,
    ) -> dict:
        """Evaluate the resolution outcome based on constraints and action type."""
        if not constraint_evaluation.get("allowed", True):
            return {
                "outcome": "blocked",
                "intensity": "low",
                "modifiers": list(constraint_evaluation.get("reasons", [])),
            }

        resolution_type = mapped_action.get("resolution_type")
        if resolution_type == "recap":
            return {"outcome": "success", "intensity": "low", "modifiers": ["recap"]}
        if resolution_type == "location_travel":
            return {
                "outcome": "success",
                "intensity": "medium",
                "modifiers": ["transition"],
            }
        if resolution_type == "thread_progress":
            return {
                "outcome": "success",
                "intensity": "medium",
                "modifiers": ["thread_progress"],
            }
        if resolution_type == "social_contact":
            return {
                "outcome": "success",
                "intensity": "medium",
                "modifiers": ["social_contact"],
            }

        return {"outcome": "success", "intensity": "medium", "modifiers": ["default"]}

    def _validate_event(self, event: dict) -> None:
        """Validate that an event has a supported type and proper shape."""
        event_type = event.get("type")
        if event_type not in SUPPORTED_EVENT_TYPES:
            raise ValueError(
                f"Unsupported event type emitted by ActionResolver: {event_type}"
            )
        if "payload" not in event or not isinstance(event["payload"], dict):
            raise ValueError("ActionResolver emitted event without dict payload")

    @staticmethod
    def _get_field(option: Any, field: str, default: Any = None) -> Any:
        if isinstance(option, dict):
            return option.get(field, default)
        return getattr(option, field, default)

    @staticmethod
    def _get_option_field(option: Any, field: str, default: Any = None) -> Any:
        """Get a field from an option dict or object."""
        if isinstance(option, dict):
            return option.get(field, default)
        return getattr(option, field, default)

    # ------------------------------------------------------------------
    # Phase 7.4 — Invalid social interaction helper
    # ------------------------------------------------------------------

    def _build_invalid_social_result(
        self, option: Any, mapped_action: dict, reason: str
    ) -> ActionResolutionResult:
        """Build an ActionResolutionResult for an invalid social interaction."""    
        consequence = ActionConsequence(
            consequence_id=f"invalid_social:{reason}",
            consequence_type="action_blocked",
            summary="Social interaction failed.",
            event_type="action_blocked",
            payload={"reason": reason},
        )

        resolved = ResolvedAction(
            action_id=self._resolved_action_id(option),
            option_id=self._get_option_field(option, "option_id"),
            intent_type=mapped_action.get("intent_type"),
            target_id=mapped_action.get("target_id"),
            summary="Invalid social interaction",
            outcome="blocked",
            consequences=[consequence],
            metadata={"reason": reason},
        )

        events = self._build_events([consequence], None)

        return ActionResolutionResult(
            resolved_action=resolved,
            events=events,
            trace={"error": reason},
        )

    # ------------------------------------------------------------------
    # Phase 7.4 — NPC Agency social contact resolution
    # ------------------------------------------------------------------

    def _resolve_social_contact(
        self,
        option: Any,
        mapped_action: dict,
        coherence_core: Any,
        gm_state: Any,
        constraint_evaluation: dict,
        evaluation: dict,
        social_state_core: Any | None = None,
        arc_control_controller: Any | None = None,
        campaign_memory_core: Any | None = None,
        scene_summary: dict | None = None,
        tick: int | None = None,
    ) -> ActionResolutionResult:
        """Delegate social_contact resolution to NPC agency engine.

        Returns an ActionResolutionResult with NPC-driven events and
        NPC decision metadata in the trace.
        """
        npc_id = mapped_action.get("target_id")

        # Guard for unknown NPCs (Phase 7.4 safety)
        if not npc_id:
            return self._build_invalid_social_result(option, mapped_action, "missing_npc_id")

        # Check coherence for known NPC
        entity_facts = coherence_core.get_entity_facts(npc_id) if hasattr(coherence_core, "get_entity_facts") else None

        if entity_facts is None:
            return self._build_invalid_social_result(option, mapped_action, f"unknown_npc:{npc_id}")

        # EXPLICIT fallback path when NPC agency engine is missing (Phase 7.4 safety)
        if self.npc_agency_engine is None:
            consequences = self.consequence_builder.build(
                mapped_action, coherence_core, gm_state, evaluation=evaluation
            )
            transition = None

            resolved_action = ResolvedAction(
                action_id=self._resolved_action_id(option),
                option_id=self._get_option_field(option, "option_id"),
                intent_type=mapped_action.get("intent_type"),
                target_id=mapped_action.get("target_id"),
                summary="Fallback social interaction (no NPC agency engine)",
                outcome="success",
                consequences=consequences,
                transition=transition,
                metadata={
                    "mapped_action": dict(mapped_action),
                    "fallback": True,
                },
            )

            events = self._build_events(consequences, transition)

            return ActionResolutionResult(
                resolved_action=resolved_action,
                events=events,
                trace={
                    "fallback": True,
                    "reason": "npc_agency_engine_missing",
                },
            )

        agency_result = self.npc_agency_engine.resolve_social_interaction(
            mapped_action=mapped_action,
            coherence_core=coherence_core,
            gm_state=gm_state,
            social_state_core=social_state_core,
        )

        npc_decision = agency_result.get("decision", {})
        npc_events = agency_result.get("events", [])

        # Phase 7.5 — Group dynamics result
        group_result = agency_result.get("group")

        # FIX #2: Merge group events into the final emitted event list
        group_events: list[dict] = []
        if group_result:
            group_events = group_result.get("events", []) or []

        events = npc_events + group_events

        # Override evaluation outcome with NPC decision (Phase 7.4)
        outcome_map = {
            "agree": "success",
            "assist": "success",
            "refuse": "blocked",
            "threaten": "blocked",
            "delay": "partial",
            "suspicious": "partial",
            "redirect": "partial",
        }

        evaluation["outcome"] = outcome_map.get(
            npc_decision.get("outcome"), evaluation.get("outcome")
        )

        # Build ActionConsequence list from NPC events
        consequences: list[ActionConsequence] = []
        for event in npc_events:
            event_type = event.get("type", "unknown")
            payload = event.get("payload", {})
            npc_id = payload.get("npc_id", "unknown_npc")
            consequences.append(
                ActionConsequence(
                    consequence_id=f"cons:npc:{event_type}:{npc_id}",
                    consequence_type=event_type,
                    summary=payload.get("summary", f"NPC {event_type}"),
                    event_type=event_type,
                    payload=dict(payload),
                    metadata={"npc_decision": dict(npc_decision)},
                )
            )

        # Use NPC decision outcome for the resolved action
        npc_outcome = npc_decision.get("outcome", "success")

        option_id = self._get_field(option, "option_id", "unknown")
        action_id = self._resolved_action_id(option)

        resolved = ResolvedAction(
            action_id=action_id,
            option_id=option_id,
            intent_type=mapped_action.get("intent_type", "unknown"),
            target_id=mapped_action.get("target_id"),
            summary=mapped_action.get("summary", ""),
            outcome=npc_outcome,
            consequences=consequences,
            transition=None,
            metadata={
                "mapped_action": dict(mapped_action),
                "evaluation": dict(evaluation),
                "npc_decision": dict(npc_decision),
                **({"group_dynamics": group_result} if group_result else {}),
            },
        )

        trace: dict = {
            "mapped_action": dict(mapped_action),
            "constraint_evaluation": dict(constraint_evaluation),
            "evaluation": dict(evaluation),
            "npc_decision": dict(npc_decision),
            "event_types": [e.get("type") for e in events],
        }
        if group_result:
            trace["group_event_types"] = [
                e.get("type") for e in group_result.get("events", [])
            ]

        # FIX #3: Validate all events (Phase 7.5 safety)
        for e in events:
            self._validate_event(e)

        # Phase 8.1 — Build structured dialogue response if dialogue_core is available
        self._attach_dialogue_payload(
            resolved, coherence_core, gm_state, npc_decision,
            social_state_core=social_state_core,
            arc_control_controller=arc_control_controller,
            campaign_memory_core=campaign_memory_core,
            scene_summary=scene_summary,
            tick=tick,
        )

        return ActionResolutionResult(
            resolved_action=resolved,
            events=events,
            trace=trace,
        )

    # ------------------------------------------------------------------
    # Phase 8.1 — Dialogue payload attachment
    # ------------------------------------------------------------------

    def _attach_dialogue_payload(
        self,
        resolved: ResolvedAction,
        coherence_core: Any,
        gm_state: Any,
        npc_decision: dict | None,
        social_state_core: Any | None = None,
        arc_control_controller: Any | None = None,
        campaign_memory_core: Any | None = None,
        scene_summary: dict | None = None,
        tick: int | None = None,
    ) -> None:
        """Attach structured dialogue output to resolved action metadata.

        Does nothing when dialogue_core is None, preserving Phase 7.4
        fallback behaviour.
        """
        if self.dialogue_core is None:
            return

        intent_type = resolved.intent_type or ""
        if intent_type not in ("talk_to_npc", "social_contact", "unknown") and resolved.outcome not in (
            "refuse", "threaten", "redirect", "agree", "assist", "delay", "offer",
        ):
            return

        try:
            payload = self.dialogue_core.build_interaction_response(
                speaker_id=resolved.target_id or "",
                listener_id=None,
                coherence_core=coherence_core,
                social_state_core=social_state_core,
                arc_control_controller=arc_control_controller,
                campaign_memory_core=campaign_memory_core,
                scene_summary=scene_summary,
                tick=tick,
                resolved_action=resolved,
                npc_decision=npc_decision,
            )
        except Exception:
            return

        resolved.metadata["dialogue_response"] = payload.get("response")
        resolved.metadata["dialogue_trace"] = payload.get("trace")
        resolved.metadata["dialogue_log_entry"] = payload.get("log_entry")
