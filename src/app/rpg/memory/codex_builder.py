"""Phase 7.7 — Codex Builder.

Derive codex entries from canonical/coherence/social state.
This is a read-model builder — codex entries are stable, deduplicated,
safe for UI, and canon-aware where applicable.
"""

from __future__ import annotations

from typing import Any

from .models import CodexEntry


class CodexBuilder:
    """Derive codex entries from authoritative state."""

    def build_npc_entries(
        self,
        coherence_core: Any,
        social_state_core: Any | None = None,
    ) -> list[CodexEntry]:
        """Build codex entries for NPCs from coherence and social state."""
        entries: list[CodexEntry] = []
        seen_ids: set[str] = set()
        state = coherence_core.get_state()

        for fact_id, fact in state.stable_world_facts.items():
            if fact.category == "npc" or (fact.predicate == "is_npc" and fact.value):
                npc_id = fact.subject
                if npc_id in seen_ids:
                    continue
                seen_ids.add(npc_id)
                entries.append(
                    CodexEntry(
                        entry_id=f"codex:npc:{npc_id}",
                        entry_type="npc",
                        title=npc_id,
                        summary=f"NPC: {npc_id}",
                        tags=["npc"],
                        related_ids=[npc_id],
                    )
                )

        for cid, commitment in state.npc_commitments.items():
            npc_id = commitment.actor_id
            if npc_id in seen_ids:
                continue
            seen_ids.add(npc_id)
            entries.append(
                CodexEntry(
                    entry_id=f"codex:npc:{npc_id}",
                    entry_type="npc",
                    title=npc_id,
                    summary=f"NPC: {npc_id} (has active commitments)",
                    tags=["npc"],
                    related_ids=[npc_id],
                )
            )

        if social_state_core is not None:
            social = social_state_core.get_state()
            for rel in social.relationships.values():
                for entity_id in (rel.source_id, rel.target_id):
                    if entity_id != "player" and entity_id not in seen_ids:
                        seen_ids.add(entity_id)
                        entries.append(
                            CodexEntry(
                                entry_id=f"codex:npc:{entity_id}",
                                entry_type="npc",
                                title=entity_id,
                                summary=f"NPC: {entity_id} (known through relationships)",
                                tags=["npc"],
                                related_ids=[entity_id],
                            )
                        )

        # Fix 3: enforce deterministic dedup by entry_id
        unique = {}
        for e in entries:
            unique[e.entry_id] = e
        return list(sorted(unique.values(), key=lambda x: x.entry_id))

    def build_faction_entries(
        self,
        coherence_core: Any,
        social_state_core: Any | None = None,
    ) -> list[CodexEntry]:
        """Build codex entries for factions."""
        entries: list[CodexEntry] = []
        seen_ids: set[str] = set()
        state = coherence_core.get_state()

        for fact_id, fact in state.stable_world_facts.items():
            if fact.category == "faction" or fact.predicate == "is_faction":
                faction_id = fact.subject
                if faction_id in seen_ids:
                    continue
                seen_ids.add(faction_id)
                entries.append(
                    CodexEntry(
                        entry_id=f"codex:faction:{faction_id}",
                        entry_type="faction",
                        title=faction_id,
                        summary=f"Faction: {faction_id}",
                        tags=["faction"],
                        related_ids=[faction_id],
                    )
                )

        if social_state_core is not None:
            social = social_state_core.get_state()
            for alliance in social.alliances.values():
                for eid in (alliance.entity_a, alliance.entity_b):
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        entries.append(
                            CodexEntry(
                                entry_id=f"codex:faction:{eid}",
                                entry_type="faction",
                                title=eid,
                                summary=f"Faction: {eid} (known through alliances)",
                                tags=["faction"],
                                related_ids=[eid],
                            )
                        )

        # Fix 3: enforce deterministic dedup by entry_id
        unique = {}
        for e in entries:
            unique[e.entry_id] = e
        return list(sorted(unique.values(), key=lambda x: x.entry_id))

    def build_location_entries(
        self,
        coherence_core: Any,
    ) -> list[CodexEntry]:
        """Build codex entries for locations."""
        entries: list[CodexEntry] = []
        seen_ids: set[str] = set()
        state = coherence_core.get_state()

        for fact_id, fact in state.stable_world_facts.items():
            if fact.category == "location" or fact.predicate == "is_location":
                loc_id = fact.subject
                if loc_id in seen_ids:
                    continue
                seen_ids.add(loc_id)
                entries.append(
                    CodexEntry(
                        entry_id=f"codex:location:{loc_id}",
                        entry_type="location",
                        title=loc_id,
                        summary=f"Location: {loc_id}",
                        tags=["location"],
                        related_ids=[loc_id],
                    )
                )

        for bucket in (state.stable_world_facts, state.scene_facts):
            loc_fact = bucket.get("scene:location")
            if loc_fact and loc_fact.value and loc_fact.value not in seen_ids:
                seen_ids.add(loc_fact.value)
                entries.append(
                    CodexEntry(
                        entry_id=f"codex:location:{loc_fact.value}",
                        entry_type="location",
                        title=loc_fact.value,
                        summary=f"Location: {loc_fact.value} (current scene)",
                        canonical=True,
                        tags=["location", "current"],
                        related_ids=[loc_fact.value],
                    )
                )

        # Fix 3: enforce deterministic dedup by entry_id
        unique = {}
        for e in entries:
            unique[e.entry_id] = e
        return list(sorted(unique.values(), key=lambda x: x.entry_id))

    def build_lore_entries(
        self,
        creator_canon_state: Any | None,
    ) -> list[CodexEntry]:
        """Build codex entries for lore/canon facts."""
        entries: list[CodexEntry] = []
        if creator_canon_state is None:
            return entries

        for fact in creator_canon_state.list_facts():
            entries.append(
                CodexEntry(
                    entry_id=f"codex:lore:{fact.fact_id}",
                    entry_type="lore",
                    title=f"{fact.subject}: {fact.predicate}",
                    summary=str(fact.value),
                    canonical=True,
                    tags=["lore", "canon"],
                    related_ids=[fact.subject] if fact.subject else [],
                    metadata={"authority": fact.authority},
                )
            )

        # Fix 3: enforce deterministic dedup by entry_id
        unique = {}
        for e in entries:
            unique[e.entry_id] = e
        return list(sorted(unique.values(), key=lambda x: x.entry_id))

    def build_rumor_entries(
        self,
        social_state_core: Any | None,
    ) -> list[CodexEntry]:
        """Build codex entries for active rumors."""
        entries: list[CodexEntry] = []
        if social_state_core is None:
            return entries

        state = social_state_core.get_state()
        for rumor_id, rumor in state.rumors.items():
            if rumor.active:
                related = [eid for eid in [rumor.source_npc_id, rumor.subject_id] if eid]
                entries.append(
                    CodexEntry(
                        entry_id=f"codex:rumor:{rumor_id}",
                        entry_type="rumor",
                        title=f"Rumor: {rumor.summary[:50]}",
                        summary=rumor.summary,
                        canonical=False,
                        tags=["rumor"],
                        related_ids=related,
                    )
                )

        # Fix 3: enforce deterministic dedup by entry_id
        unique = {}
        for e in entries:
            unique[e.entry_id] = e
        return list(sorted(unique.values(), key=lambda x: x.entry_id))

    def build_thread_entries(
        self,
        coherence_core: Any,
    ) -> list[CodexEntry]:
        """Build codex entries for narrative threads."""
        entries: list[CodexEntry] = []
        state = coherence_core.get_state()

        for thread_id, thread in state.unresolved_threads.items():
            status_tag = "resolved" if thread.status == "resolved" else "active"
            entries.append(
                CodexEntry(
                    entry_id=f"codex:thread:{thread_id}",
                    entry_type="thread",
                    title=thread.title,
                    summary=f"Thread: {thread.title} (status: {thread.status})",
                    tags=["thread", status_tag],
                    related_ids=list(thread.anchor_entity_ids),
                    metadata={"priority": thread.priority, "status": thread.status},
                )
            )

        # Fix 3: enforce deterministic dedup by entry_id
        unique = {}
        for e in entries:
            unique[e.entry_id] = e
        return list(sorted(unique.values(), key=lambda x: x.entry_id))
