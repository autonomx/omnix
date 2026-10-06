"""Phase 7.4 / 7.5 / 7.6 — NPC Agency Engine.

Orchestrates context building, policy decision, and response building
for NPC social interactions. Returns a structured payload for resolver
integration and debugging.

Phase 7.5 addition: optional GroupDynamicsEngine integration for
multi-actor secondary reactions and rumor seeding.

Phase 7.6 addition: optional social_state_core integration for
reading persistent social state into relationship building and context.
"""

from __future__ import annotations

from typing import Any, Optional

from .decision_policy import NPCDecisionPolicy
from .faction_context import FactionContextBuilder
from .models import NPCDecisionContext
from .relationship_state import RelationshipStateBuilder
from .response_builder import NPCResponseBuilder


class NPCAgencyEngine:
    """Orchestrate NPC social interaction resolution."""

    def __init__(
        self,
        relationship_builder: Optional[RelationshipStateBuilder] = None,
        faction_builder: Optional[FactionContextBuilder] = None,
        decision_policy: Optional[NPCDecisionPolicy] = None,
        response_builder: Optional[NPCResponseBuilder] = None,
        group_dynamics_engine: Optional[Any] = None,
    ) -> None:
        self.relationship_builder = relationship_builder or RelationshipStateBuilder()
        self.faction_builder = faction_builder or FactionContextBuilder()
        self.decision_policy = decision_policy or NPCDecisionPolicy()
        self.response_builder = response_builder or NPCResponseBuilder()
        self.group_dynamics_engine = group_dynamics_engine

    def resolve_social_interaction(
        self,
        mapped_action: dict,
        coherence_core: Any,
        gm_state: Any,
        control_output: dict | None = None,
        social_state_core: Any | None = None,
    ) -> dict:
        """Resolve a social interaction through NPC agency.

        Returns a structured payload:
            {
                "context": {...},
                "decision": {...},
                "events": [...],
                "group": {...},   # optional, Phase 7.5
            }
        """
        context = self._build_context(
            mapped_action, coherence_core, gm_state, control_output, social_state_core
        )
        decision = self.decision_policy.decide(context)
        events = self.response_builder.build_events(decision, mapped_action)

        result: dict[str, Any] = {
            "context": context.to_dict(),
            "decision": decision.to_dict(),
            "events": events,
        }

        # Phase 7.5 — Resolve group dynamics if engine is available
        primary_npc_id = mapped_action.get("target_id")
        if (
            self.group_dynamics_engine is not None
            and primary_npc_id
        ):
            group_result = self.group_dynamics_engine.resolve_group_dynamics(
                primary_npc_id=primary_npc_id,
                primary_decision=decision.to_dict(),
                coherence_core=coherence_core,
            )
            # FIX #8: Do not emit empty group payloads
            if not group_result.get("events"):
                group_result = None
            if group_result is not None:
                result["group"] = group_result
                # Merge group events into the primary event list
                result["events"] = events + group_result.get("events", [])

        return result

    def _build_context(
        self,
        mapped_action: dict,
        coherence_core: Any,
        gm_state: Any,
        control_output: dict | None = None,
        social_state_core: Any | None = None,
    ) -> NPCDecisionContext:
        """Assemble full decision context from available state."""
        npc_id = mapped_action.get("target_id") or "unknown_npc"
        target_id = mapped_action.get("target_id")
        intent_type = mapped_action.get("intent_type", "talk_to_npc")

        # Build relationship view (Phase 7.6: with persistent social state)
        relationship = self.relationship_builder.build(
            npc_id=npc_id,
            target_id=target_id,
            coherence_core=coherence_core,
            social_state_core=social_state_core,
        )

        # Build faction alignment
        faction_alignment = self.faction_builder.build(
            npc_id=npc_id,
            coherence_core=coherence_core,
        )

        # Gather scene summary
        scene_summary = self._get_scene_summary(coherence_core)

        # Gather known facts about this NPC
        known_facts = self._get_npc_facts(npc_id, coherence_core)

        # Gather commitments
        commitments = self._get_commitments(npc_id, coherence_core)

        # Gather recent consequences
        recent_consequences = self._get_recent_consequences(npc_id, coherence_core)

        # GM context
        gm_context = self._get_gm_context(npc_id, gm_state)

        # Pacing context
        pacing = {}
        if control_output and isinstance(control_output, dict):
            pacing = dict(control_output.get("pacing", {}))

        # Phase 7.6 — Build social view metadata if social state is available
        context_metadata: dict[str, Any] = {}
        if social_state_core is not None:
            try:
                social_query = social_state_core.get_query()
                social_state = social_state_core.get_state()
                social_view = social_query.build_npc_social_view(
                    social_state, npc_id, target_id
                )
                context_metadata["social_view"] = social_view
            except (AttributeError, TypeError) as e:
                context_metadata["social_view_error"] = str(e)

        return NPCDecisionContext(
            npc_id=npc_id,
            intent_type=intent_type,
            target_id=target_id,
            scene_summary=scene_summary,
            known_facts=known_facts,
            commitments=commitments,
            recent_consequences=recent_consequences,
            relationship=relationship,
            faction_alignment=faction_alignment,
            pacing=pacing,
            gm_context=gm_context,
            metadata=context_metadata,
        )

    def _get_scene_summary(self, coherence_core: Any) -> dict:
        """Safely get scene summary from coherence."""
        try:
            summary = coherence_core.get_scene_summary()
            return dict(summary) if isinstance(summary, dict) else {}
        except (AttributeError, TypeError):
            return {}

    def _get_npc_facts(self, npc_id: str, coherence_core: Any) -> dict:
        """Extract known facts about the NPC from coherence."""
        facts: dict[str, Any] = {}
        try:
            state = coherence_core.get_state()
            for fid, fact in state.stable_world_facts.items():
                subject = fact.subject if hasattr(fact, "subject") else ""
                if subject == npc_id:
                    predicate = (
                        fact.predicate if hasattr(fact, "predicate") else str(fid)
                    )
                    value = fact.value if hasattr(fact, "value") else None
                    facts[predicate] = value
        except (AttributeError, TypeError):
            pass
        return facts

    def _get_commitments(self, npc_id: str, coherence_core: Any) -> list[dict]:
        """Extract active commitments involving this NPC."""
        result: list[dict] = []
        try:
            state = coherence_core.get_state()
            for cid, commitment in state.commitments.items():
                actor = (
                    commitment.actor_id
                    if hasattr(commitment, "actor_id")
                    else commitment.get("actor_id")
                )
                if actor == npc_id:
                    if hasattr(commitment, "to_dict"):
                        result.append(commitment.to_dict())
                    else:
                        result.append(dict(commitment))
        except (AttributeError, TypeError):
            pass
        return result

    def _get_recent_consequences(
        self, npc_id: str, coherence_core: Any
    ) -> list[dict]:
        """Extract recent consequences involving this NPC."""
        result: list[dict] = []
        try:
            state = coherence_core.get_state()
            consequences = getattr(state, "recent_consequences", [])
            for c in consequences:
                c_dict = c.to_dict() if hasattr(c, "to_dict") else dict(c)
                entity_ids = c_dict.get("entity_ids", [])
                if npc_id in entity_ids:
                    result.append(c_dict)
        except (AttributeError, TypeError):
            pass
        return result

    def _get_gm_context(self, npc_id: str, gm_state: Any) -> dict:
        """Extract GM context relevant to this NPC."""
        context: dict[str, Any] = {}
        try:
            if hasattr(gm_state, "get_focus_target"):
                focus_target = gm_state.get_focus_target()
                if focus_target:
                    context["focus_target"] = focus_target
            if hasattr(gm_state, "find_directives_for_npc"):
                directives = gm_state.find_directives_for_npc(npc_id)
                if directives:
                    context["npc_directives"] = [
                        d.to_dict() if hasattr(d, "to_dict") else dict(d)
                        for d in directives
                    ]
        except (AttributeError, TypeError):
            pass
        return context
