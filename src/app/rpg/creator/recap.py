from __future__ import annotations

from typing import Any


class RecapBuilder:
    def build_canon_summary(self, coherence_core: Any, creator_canon_state: Any | None = None) -> dict:
        canon_facts = []
        if creator_canon_state is not None:
            canon_facts = [f.to_dict() for f in creator_canon_state.list_facts()]
        return {
            "canon_facts": canon_facts,
            "scene_summary": coherence_core.get_scene_summary(),
        }

    def build_session_recap(self, coherence_core: Any, gm_state: Any | None = None) -> dict:
        return {
            "scene_summary": coherence_core.get_scene_summary(),
            "recent_consequences": coherence_core.get_recent_consequences(limit=10),
            "active_tensions": coherence_core.get_active_tensions(),
            "unresolved_threads": coherence_core.get_unresolved_threads(),
            "gm_directives": gm_state.build_director_context() if gm_state else {},
        }

    def build_active_factions_summary(self, coherence_core: Any) -> dict:
        factions = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if fact.fact_id.startswith("faction:") and fact.predicate == "exists":
                factions.append({"faction_id": fact.subject, "metadata": fact.metadata})
        return {"factions": factions}

    def build_npc_roster(self, coherence_core: Any) -> dict:
        npcs = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if fact.fact_id.startswith("npc:") and fact.predicate == "name":
                npcs.append(
                    {
                        "npc_id": fact.subject,
                        "name": fact.value,
                        "metadata": fact.metadata,
                    }
                )
        return {"npcs": npcs}

    def build_unresolved_threads_summary(self, coherence_core: Any) -> dict:
        return {"threads": coherence_core.get_unresolved_threads()}

    def build_world_tensions_summary(self, coherence_core: Any) -> dict:
        return {"active_tensions": coherence_core.get_active_tensions()}

    def build_player_impact_summary(self, coherence_core: Any) -> dict:
        return {"recent_consequences": coherence_core.get_recent_consequences(limit=10)}
