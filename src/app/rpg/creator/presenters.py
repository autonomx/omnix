from __future__ import annotations

from typing import Any

from .schema import AdventureSetup


class CreatorStatePresenter:
    """Convert creator/coherence/GM state into stable UI-friendly payloads.

    All ``present_*`` methods produce plain dicts with consistent field names
    suitable for direct JSON serialisation to a frontend panel.
    """

    def _present_thread(self, thread: dict) -> dict:
        return {
            "id": thread.get("thread_id"),
            "title": thread.get("title"),
            "status": thread.get("status"),
            "priority": thread.get("priority"),
            "notes": list(thread.get("notes", [])),
        }

    def _present_fact(self, fact: dict) -> dict:
        return {
            "id": fact.get("fact_id"),
            "subject": fact.get("subject"),
            "predicate": fact.get("predicate"),
            "value": fact.get("value"),
            "authority": fact.get("authority"),
            "label": fact.get("label") or fact.get("metadata", {}).get("label"),
        }

    def _present_directive(self, directive: dict) -> dict:
        return {
            "id": directive.get("directive_id"),
            "type": directive.get("directive_type"),
            "scope": directive.get("scope"),
            "enabled": directive.get("enabled", True),
            "summary": directive.get("instruction")
                or directive.get("tone")
                or directive.get("level")
                or directive.get("thread_id")
                or directive.get("target_id")
                or directive.get("npc_id")
                or directive.get("faction_id")
                or directive.get("location_id"),
        }

    def present_setup_summary(self, setup: AdventureSetup) -> dict:
        return {
            "title": setup.title,
            "genre": setup.genre,
            "setting": setup.setting,
            "premise": setup.premise,
            "difficulty_style": setup.difficulty_style,
            "mood": setup.mood,
            "starting_location_id": setup.starting_location_id,
            "starting_npc_ids": list(setup.starting_npc_ids),
            "counts": {
                "factions": len(setup.factions),
                "locations": len(setup.locations),
                "npcs": len(setup.npc_seeds),
            },
        }

    def present_canon_summary(
        self, creator_canon_state: Any, coherence_core: Any
    ) -> dict:
        facts = []
        if creator_canon_state is not None:
            facts = [self._present_fact(f.to_dict()) for f in creator_canon_state.list_facts()]
        scene_summary = coherence_core.get_scene_summary()
        if isinstance(scene_summary, dict):
            scene_summary = scene_summary
        else:
            scene_summary = {"summary": str(scene_summary)}
        return {
            "title": "Canon",
            "facts": facts,
            "scene_summary": scene_summary,
            "count": len(facts),
        }

    def present_gm_dashboard(self, gm_state: Any, coherence_core: Any) -> dict:
        summary = gm_state.build_ui_summary()
        directives = summary.get("directives", [])
        scene_summary = coherence_core.get_scene_summary()
        if isinstance(scene_summary, dict):
            scene_summary = scene_summary
        else:
            scene_summary = {"summary": str(scene_summary)}
        return {
            "title": "GM Dashboard",
            "directives": [self._present_directive(d) for d in directives],
            "counts": summary.get("counts", {}),
            "scene_summary": scene_summary,
        }

    def present_thread_panel(self, coherence_core: Any) -> dict:
        threads = coherence_core.get_unresolved_threads()
        return {
            "title": "Threads",
            "items": [self._present_thread(t) for t in threads],
            "count": len(threads),
        }

    def present_npc_panel(self, coherence_core: Any) -> dict:
        npcs = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if str(fact.fact_id).startswith("npc:") and fact.predicate == "name":
                npcs.append(
                    {
                        "id": fact.subject,
                        "name": fact.value,
                        "role": fact.metadata.get("role"),
                        "must_survive": fact.metadata.get("must_survive", False),
                    }
                )
        return {
            "title": "NPCs",
            "items": npcs,
            "count": len(npcs),
        }

    def present_faction_panel(self, coherence_core: Any) -> dict:
        factions = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if str(fact.fact_id).startswith("faction:") and fact.predicate == "exists":
                factions.append(
                    {
                        "id": fact.subject,
                        "name": fact.metadata.get("name"),
                        "exists": fact.value,
                    }
                )
        return {
            "title": "Factions",
            "items": factions,
            "count": len(factions),
        }

    def present_location_panel(self, coherence_core: Any) -> dict:
        locations = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if str(fact.fact_id).startswith("location:") and fact.predicate == "name":
                locations.append(
                    {
                        "id": fact.subject,
                        "name": fact.value,
                        "description": fact.metadata.get("description"),
                    }
                )
        return {
            "title": "Locations",
            "items": locations,
            "count": len(locations),
        }

    def present_recap_panel(self, recap: dict) -> dict:
        scene_summary = recap.get("scene_summary", {})
        if isinstance(scene_summary, dict):
            scene_summary = scene_summary
        else:
            scene_summary = {"summary": str(scene_summary)}
        return {
            "title": recap.get("title", "Recap"),
            "scene_summary": scene_summary,
            "active_tensions": list(recap.get("active_tensions", [])),
            "recent_consequences": list(recap.get("recent_consequences", [])),
            "unresolved_threads": [self._present_thread(t) for t in recap.get("unresolved_threads", [])],
        }

    # ------------------------------------------------------------------
    # Phase 7.3 — Action resolution presenters
    # ------------------------------------------------------------------

    def present_action_resolution(self, resolution: dict) -> dict:
        """Present an action resolution result in a UI-safe format."""
        resolved_action = resolution.get("resolved_action", {})
        events = resolution.get("events", [])
        transition = resolved_action.get("transition")
        return {
            "title": "Action Result",
            "action": {
                "action_id": resolved_action.get("action_id"),
                "option_id": resolved_action.get("option_id"),
                "intent_type": resolved_action.get("intent_type"),
                "target_id": resolved_action.get("target_id"),
                "summary": resolved_action.get("summary"),
                "consequence_count": len(resolved_action.get("consequences", [])),
            },
            "events": [
                {"type": e.get("type"), "payload": dict(e.get("payload", {}))}
                for e in events
            ],
            "transition": self.present_scene_transition(transition),
        }

    def present_scene_transition(self, transition: dict | None) -> dict | None:
        """Present a scene transition in a UI-safe format."""
        if transition is None:
            return None
        return {
            "transition_id": transition.get("transition_id"),
            "transition_type": transition.get("transition_type"),
            "from_location": transition.get("from_location"),
            "to_location": transition.get("to_location"),
            "summary": transition.get("summary"),
        }
