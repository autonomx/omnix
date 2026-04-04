"""Phase 7.4 — Relationship State Builder.

Derives an NPCRelationshipView from coherence facts and recent consequences.
Keeps logic simple and deterministic — no randomness, no LLM calls.
"""

from __future__ import annotations

from typing import Any

from .models import NPCRelationshipView


class RelationshipStateBuilder:
    """Build a relationship snapshot from coherence state."""

    def build(
        self,
        npc_id: str,
        target_id: str | None,
        coherence_core: Any,
    ) -> NPCRelationshipView:
        """Derive relationship view from coherence facts and consequences."""
        relationship_fact = self._extract_relationship_fact(
            npc_id, target_id, coherence_core
        )
        recent_consequences = self._get_recent_consequences(npc_id, coherence_core)

        return NPCRelationshipView(
            npc_id=npc_id,
            target_id=target_id,
            trust=self._derive_trust(relationship_fact, recent_consequences),
            fear=self._derive_fear(relationship_fact, recent_consequences),
            hostility=self._derive_hostility(relationship_fact, recent_consequences),
            respect=self._derive_respect(relationship_fact, recent_consequences),
        )

    def _extract_relationship_fact(
        self, npc_id: str, target_id: str | None, coherence_core: Any
    ) -> dict | None:
        """Look up a relationship fact from coherence stable_world_facts."""
        if target_id is None:
            return None
        try:
            state = coherence_core.get_state()
            fact_id = f"rel:{npc_id}:{target_id}"
            fact = state.stable_world_facts.get(fact_id)
            if fact is not None:
                return fact.to_dict() if hasattr(fact, "to_dict") else dict(fact)
        except (AttributeError, TypeError):
            pass
        return None

    def _get_recent_consequences(
        self, npc_id: str, coherence_core: Any
    ) -> list[dict]:
        """Extract recent consequences involving this NPC."""
        try:
            state = coherence_core.get_state()
            consequences = getattr(state, "recent_consequences", [])
            result = []
            for c in consequences:
                c_dict = c.to_dict() if hasattr(c, "to_dict") else dict(c)
                entity_ids = c_dict.get("entity_ids", [])
                if npc_id in entity_ids:
                    result.append(c_dict)
            return result
        except (AttributeError, TypeError):
            return []

    def _derive_trust(
        self, relationship_fact: dict | None, recent_consequences: list[dict]
    ) -> float:
        """Derive trust score from fact and consequences."""
        base = 0.0
        if relationship_fact is not None:
            value = relationship_fact.get("value")
            if isinstance(value, dict):
                base = float(value.get("trust", 0.0))
            elif isinstance(value, str) and value in ("ally", "friend"):
                base = 0.5
        for c in recent_consequences:
            ctype = c.get("consequence_type", "")
            if ctype in ("npc_response_agreed", "npc_interaction_started"):
                base += 0.1
        return max(-1.0, min(1.0, base))

    def _derive_fear(
        self, relationship_fact: dict | None, recent_consequences: list[dict]
    ) -> float:
        """Derive fear score from fact and consequences."""
        base = 0.0
        if relationship_fact is not None:
            value = relationship_fact.get("value")
            if isinstance(value, dict):
                base = float(value.get("fear", 0.0))
        for c in recent_consequences:
            ctype = c.get("consequence_type", "")
            if ctype in ("npc_response_threatened", "character_died"):
                base += 0.2
        return max(-1.0, min(1.0, base))

    def _derive_hostility(
        self, relationship_fact: dict | None, recent_consequences: list[dict]
    ) -> float:
        """Derive hostility score from fact and consequences."""
        base = 0.0
        if relationship_fact is not None:
            value = relationship_fact.get("value")
            if isinstance(value, dict):
                base = float(value.get("hostility", 0.0))
            elif isinstance(value, str) and value in ("enemy", "hostile"):
                base = 0.5
        for c in recent_consequences:
            ctype = c.get("consequence_type", "")
            if ctype in ("npc_response_threatened", "npc_response_refused"):
                base += 0.1
        return max(-1.0, min(1.0, base))

    def _derive_respect(
        self, relationship_fact: dict | None, recent_consequences: list[dict]
    ) -> float:
        """Derive respect score from fact and consequences."""
        base = 0.0
        if relationship_fact is not None:
            value = relationship_fact.get("value")
            if isinstance(value, dict):
                base = float(value.get("respect", 0.0))
        for c in recent_consequences:
            ctype = c.get("consequence_type", "")
            if ctype in ("npc_response_agreed", "npc_interaction_started"):
                base += 0.05
        return max(-1.0, min(1.0, base))
