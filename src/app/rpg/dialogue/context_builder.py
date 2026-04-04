"""Phase 8.1 — Dialogue Context Builder.

Gather dialogue planning context from existing state owners.
No mutation, no generation — only structured extraction and normalization.
"""

from __future__ import annotations

from typing import Any

from .models import DialogueTurnContext

# Maximum number of recent interaction history entries to include.
_MAX_HISTORY_ENTRIES = 5


class DialogueContextBuilder:
    """Build a DialogueTurnContext from existing authoritative state."""

    def build_for_interaction(
        self,
        speaker_id: str,
        listener_id: str | None = None,
        coherence_core: Any = None,
        social_state_core: Any = None,
        arc_control_controller: Any = None,
        resolved_action: Any = None,
        npc_decision: dict | None = None,
        scene_summary: dict | None = None,
        tick: int | None = None,
        history_source: Any = None,
    ) -> DialogueTurnContext:
        """Assemble a complete turn context from upstream state.

        All parameters are optional; missing data produces sparse but
        deterministic defaults.
        """
        # 1. Scene extraction
        scene = self._extract_scene(coherence_core, scene_summary)

        # 2. Speaker / listener extraction
        speaker_state = self._extract_entity_state(coherence_core, speaker_id)
        listener_state = (
            self._extract_entity_state(coherence_core, listener_id)
            if listener_id
            else {}
        )

        # 3. Social extraction
        relationship_state = self._extract_relationship(
            social_state_core, speaker_id, listener_id
        )
        social_context = self._extract_social_context(
            social_state_core, speaker_id, listener_id, scene.get("location")
        )

        # 4. Arc extraction
        arc_context = self._extract_arc_context(arc_control_controller, coherence_core)

        # 5. Interaction history
        interaction_history = self._collect_recent_dialogue_history(
            history_source, speaker_id, listener_id
        )

        # 6. Action / NPC decision normalization
        intent_type = ""
        action_outcome: str | None = None
        tags: list[str] = []
        if resolved_action is not None:
            ra = resolved_action if isinstance(resolved_action, dict) else resolved_action.to_dict() if hasattr(resolved_action, "to_dict") else {}
            intent_type = ra.get("intent_type", "")
            action_outcome = ra.get("outcome")
            tags = list(ra.get("metadata", {}).get("modifiers", []))
        if npc_decision:
            action_outcome = npc_decision.get("outcome", action_outcome)
            if npc_decision.get("response_type"):
                tags.append(npc_decision["response_type"])

        # 7. State drivers normalization
        state_drivers = self._normalize_state_drivers(
            relationship_state, arc_context, scene
        )

        return DialogueTurnContext(
            speaker_id=speaker_id,
            listener_id=listener_id,
            scene_location=scene.get("location"),
            scene_summary=scene,
            speaker_state=speaker_state,
            listener_state=listener_state,
            relationship_state=relationship_state,
            social_context=social_context,
            coherence_context=self._extract_coherence_context(coherence_core),
            arc_context=arc_context,
            interaction_history=interaction_history,
            current_intent_type=intent_type,
            current_action_outcome=action_outcome,
            current_tags=tags,
            metadata={
                "tick": tick,
                "state_drivers": state_drivers,
            },
        )

    # ------------------------------------------------------------------
    # Scene extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_scene(
        coherence_core: Any, passed_summary: dict | None
    ) -> dict:
        if passed_summary:
            return dict(passed_summary)
        if coherence_core is not None and hasattr(coherence_core, "get_scene_summary"):
            return dict(coherence_core.get_scene_summary())
        return {}

    # ------------------------------------------------------------------
    # Entity extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_entity_state(coherence_core: Any, entity_id: str | None) -> dict:
        """Deterministic lookup — never invent missing NPC data."""
        if not entity_id or coherence_core is None:
            return {"known": False, "role": "unknown", "status": "unknown"}
        if hasattr(coherence_core, "get_entity_facts"):
            facts = coherence_core.get_entity_facts(entity_id)
            if facts is None:
                return {"known": False, "role": "unknown", "status": "unknown"}
            if isinstance(facts, dict):
                return {"known": True, **facts}
            return {"known": True, "facts": facts}
        return {"known": False, "role": "unknown", "status": "unknown"}

    # ------------------------------------------------------------------
    # Social extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_relationship(
        social_state_core: Any,
        speaker_id: str,
        listener_id: str | None,
    ) -> dict:
        if not listener_id or social_state_core is None:
            return {}
        state = social_state_core.get_state() if hasattr(social_state_core, "get_state") else None
        if state is None:
            return {}
        query = social_state_core.query if hasattr(social_state_core, "query") else None
        if query is None:
            return {}
        rel = query.get_relationship(state, speaker_id, listener_id)
        return dict(rel) if rel else {}

    @staticmethod
    def _extract_social_context(
        social_state_core: Any,
        speaker_id: str,
        listener_id: str | None,
        location: str | None,
    ) -> dict:
        """Read reputation, rumors, alliances relevant to the interaction."""
        if social_state_core is None:
            return {}
        state = social_state_core.get_state() if hasattr(social_state_core, "get_state") else None
        if state is None:
            return {}
        query = social_state_core.query if hasattr(social_state_core, "query") else None
        if query is None:
            return {}

        context: dict[str, Any] = {}
        context["speaker_rumors"] = query.get_active_rumors_for_subject(state, speaker_id)
        if listener_id:
            context["listener_rumors"] = query.get_active_rumors_for_subject(state, listener_id)
            rep = query.get_reputation(state, listener_id, speaker_id)
            if rep:
                context["reputation"] = rep
            alliance = query.get_alliance(state, speaker_id, listener_id)
            if alliance:
                context["alliance"] = alliance
        return context

    # ------------------------------------------------------------------
    # Coherence extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_coherence_context(coherence_core: Any) -> dict:
        if coherence_core is None:
            return {}
        ctx: dict[str, Any] = {}
        if hasattr(coherence_core, "get_unresolved_threads"):
            ctx["unresolved_threads"] = coherence_core.get_unresolved_threads()
        if hasattr(coherence_core, "get_active_tensions"):
            ctx["active_tensions"] = coherence_core.get_active_tensions()
        return ctx

    # ------------------------------------------------------------------
    # Arc extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_arc_context(
        arc_control_controller: Any, coherence_core: Any
    ) -> dict:
        if arc_control_controller is None:
            return {}
        if hasattr(arc_control_controller, "build_director_context"):
            return dict(arc_control_controller.build_director_context(coherence_core))
        return {}

    # ------------------------------------------------------------------
    # Interaction history
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_recent_dialogue_history(
        history_source: Any,
        speaker_id: str,
        listener_id: str | None,
    ) -> list[dict[str, Any]]:
        """Build bounded recent interaction history from explicit state.

        Uses journal entries from CampaignMemoryCore if available.
        Deterministic ordering by entry_id.
        """
        if history_source is None:
            return []
        entries: list[dict] = []
        if hasattr(history_source, "journal_entries"):
            for entry in history_source.journal_entries:
                e = entry.to_dict() if hasattr(entry, "to_dict") else dict(entry)
                entity_ids = e.get("entity_ids", [])
                if speaker_id in entity_ids or (listener_id and listener_id in entity_ids):
                    entries.append(e)
        # Deterministic ordering by entry_id, then take last N
        entries.sort(key=lambda e: e.get("entry_id", ""))
        return entries[-_MAX_HISTORY_ENTRIES:]

    # ------------------------------------------------------------------
    # State drivers normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_state_drivers(
        relationship_state: dict,
        arc_context: dict,
        scene: dict,
    ) -> dict:
        """Produce normalized driver labels the planner can use."""
        trust = float(relationship_state.get("trust", 0.0))
        hostility = float(relationship_state.get("hostility", 0.0))
        fear = float(relationship_state.get("fear", 0.0))
        respect = float(relationship_state.get("respect", 0.0))

        # Determine reveal pressure from arc context
        due_reveals = arc_context.get("due_reveals", [])
        reveal_pressure = "high" if due_reveals else "none"

        # Scene tension from tensions list
        tensions = scene.get("active_tensions", [])
        scene_tension = "high" if len(tensions) >= 2 else "low" if not tensions else "medium"

        return {
            "openness": "high" if trust >= 0.6 and hostility < 0.3 else "low" if hostility >= 0.5 else "medium",
            "hostility": "high" if hostility >= 0.6 else "medium" if hostility >= 0.3 else "low",
            "trust": "high" if trust >= 0.6 else "medium" if trust >= 0.3 else "low",
            "fear": "high" if fear >= 0.6 else "medium" if fear >= 0.3 else "low",
            "respect": "high" if respect >= 0.6 else "medium" if respect >= 0.3 else "low",
            "reveal_pressure": reveal_pressure,
            "scene_tension": scene_tension,
            "urgency": "high" if scene_tension == "high" else "normal",
            "interaction_mode": "social",
        }
