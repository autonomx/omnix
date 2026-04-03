from __future__ import annotations

from typing import Any

from .schema import AdventureSetup


class CreatorStatePresenter:
    """Convert creator/coherence/GM state into stable UI-friendly payloads.

    All ``present_*`` methods produce plain dicts with consistent field names
    suitable for direct JSON serialisation to a frontend panel.
    """

    def present_setup_summary(self, setup: AdventureSetup) -> dict:
        """Summarise an AdventureSetup for a UI overview panel."""
        return {
            "setup_id": setup.setup_id,
            "title": setup.title,
            "genre": setup.genre,
            "setting": setup.setting,
            "premise": setup.premise,
            "difficulty_style": setup.difficulty_style,
            "mood": setup.mood,
            "starting_location_id": setup.starting_location_id,
            "starting_npc_ids": list(setup.starting_npc_ids),
            "faction_count": len(setup.factions),
            "npc_count": len(setup.npc_seeds),
            "location_count": len(setup.locations),
            "has_pacing": setup.pacing is not None,
            "has_safety": setup.safety is not None,
            "has_content_balance": setup.content_balance is not None,
        }

    def present_canon_summary(
        self, creator_canon_state: Any, coherence_core: Any
    ) -> dict:
        """Produce a canon-state summary combining creator facts and coherence."""
        canon_facts = []
        if creator_canon_state is not None:
            canon_facts = [
                {
                    "fact_id": f.fact_id,
                    "subject": f.subject,
                    "predicate": f.predicate,
                    "value": f.value,
                }
                for f in creator_canon_state.list_facts()
            ]
        return {
            "canon_facts": canon_facts,
            "scene_summary": coherence_core.get_scene_summary(),
        }

    def present_gm_dashboard(self, gm_state: Any, coherence_core: Any) -> dict:
        """Present a combined GM dashboard with directives and world status."""
        ctx = gm_state.build_director_context()
        return {
            "active_directive_count": len(ctx.get("active_directives", [])),
            "pacing": ctx.get("pacing", []),
            "tone": ctx.get("tone", []),
            "danger": ctx.get("danger", []),
            "pinned_threads": ctx.get("pinned_threads", []),
            "scene_summary": coherence_core.get_scene_summary(),
            "unresolved_thread_count": len(coherence_core.get_unresolved_threads()),
        }

    def present_thread_panel(self, coherence_core: Any) -> dict:
        """Return threads grouped by status for a thread-panel UI."""
        all_threads = coherence_core.get_unresolved_threads()
        return {
            "unresolved_threads": all_threads,
            "total": len(all_threads),
        }

    def present_npc_panel(self, coherence_core: Any) -> dict:
        """List NPCs known to coherence for an NPC roster panel."""
        npcs = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if fact.fact_id.startswith("npc:") and fact.predicate == "name":
                npcs.append(
                    {
                        "npc_id": fact.subject,
                        "name": fact.value,
                        "metadata": dict(fact.metadata),
                    }
                )
        return {"npcs": npcs, "total": len(npcs)}

    def present_faction_panel(self, coherence_core: Any) -> dict:
        """List factions known to coherence for a faction panel."""
        factions = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if fact.fact_id.startswith("faction:") and fact.predicate == "exists":
                factions.append(
                    {
                        "faction_id": fact.subject,
                        "metadata": dict(fact.metadata),
                    }
                )
        return {"factions": factions, "total": len(factions)}

    def present_location_panel(self, coherence_core: Any) -> dict:
        """List locations known to coherence for a location panel."""
        locations = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if fact.fact_id.startswith("location:") and fact.predicate == "name":
                locations.append(
                    {
                        "location_id": fact.subject,
                        "name": fact.value,
                        "metadata": dict(fact.metadata),
                    }
                )
        return {"locations": locations, "total": len(locations)}

    def present_recap_panel(self, recap: dict) -> dict:
        """Normalise a recap dict into a stable UI payload shape."""
        return {
            "scene_summary": recap.get("scene_summary", ""),
            "recent_consequences": recap.get("recent_consequences", []),
            "active_tensions": recap.get("active_tensions", []),
            "unresolved_threads": recap.get("unresolved_threads", []),
            "gm_directives": recap.get("gm_directives", {}),
        }
