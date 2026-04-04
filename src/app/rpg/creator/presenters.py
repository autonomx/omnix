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
        metadata = resolved_action.get("metadata", {})

        result = {
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

        # Phase 7.4 — Include NPC decision summary if present
        npc_decision = metadata.get("npc_decision")
        if npc_decision:
            result["npc_decision"] = self.present_npc_decision(npc_decision)

        # Phase 7.5 — Include group dynamics if present
        group_dynamics = metadata.get("group_dynamics")
        if group_dynamics:
            result["group_dynamics"] = self.present_group_dynamics(group_dynamics)

        return result

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

    # ------------------------------------------------------------------
    # Phase 7.4 — NPC decision presenters
    # ------------------------------------------------------------------

    def present_npc_decision(self, decision: dict) -> dict:
        """Present an NPC decision result in a UI-safe format."""
        return {
            "npc_id": decision.get("npc_id") or "unknown",
            "outcome": decision.get("outcome") or "unknown",
            "response_type": decision.get("response_type") or "unknown",
            "summary": decision.get("summary") or "",
            "modifiers": list(decision.get("modifiers") or []),
        }

    # ------------------------------------------------------------------
    # Phase 7.5 — Group dynamics presenters
    # ------------------------------------------------------------------

    def present_secondary_reaction(self, reaction: dict) -> dict:
        """Present a secondary reaction in a UI-safe format."""
        return {
            "npc_id": reaction.get("npc_id") or "unknown",
            "reaction_type": reaction.get("reaction_type") or "unknown",
            "summary": reaction.get("summary") or "",
            "modifiers": list(reaction.get("modifiers") or []),
        }

    def present_group_dynamics(self, group: dict) -> dict:
        """Present group dynamics in a UI-safe format."""
        participants = group.get("participants") or []
        # FIX #7: Ensure deterministic ordering for UI stability
        participants = sorted(participants, key=lambda p: p.get("npc_id", ""))
        crowd_state = group.get("crowd_state") or {}
        secondary_reactions = group.get("secondary_reactions") or []
        # FIX #7: Ensure deterministic ordering for UI stability
        secondary_reactions = sorted(secondary_reactions, key=lambda r: r.get("npc_id", ""))
        rumor_seeds = group.get("rumor_seeds") or []

        return {
            "participants": [
                {
                    "npc_id": p.get("npc_id") or "unknown",
                    "role": p.get("role") or "unknown",
                    "faction_id": p.get("faction_id"),
                }
                for p in participants
            ],
            "crowd_state": {
                "mood": crowd_state.get("mood") or "neutral",
                "tension": crowd_state.get("tension") or "low",
                "support_level": crowd_state.get("support_level") or "mixed",
            },
            "secondary_reactions": [
                self.present_secondary_reaction(r) for r in secondary_reactions
            ],
            "rumor_seeds": [
                {
                    "rumor_id": s.get("rumor_id") or "unknown",
                    "rumor_type": s.get("rumor_type") or "unknown",
                    "summary": s.get("summary") or "",
                }
                for s in rumor_seeds
            ],
        }

    # ------------------------------------------------------------------
    # Phase 7.6 — Social state presenters
    # ------------------------------------------------------------------

    def present_social_dashboard(self, social_state_core: Any) -> dict:
        """Present the social state dashboard in a UI-safe format."""
        if social_state_core is None:
            return {
                "title": "Social State",
                "relationships": [],
                "rumors": [],
                "alliances": [],
            }
        state = social_state_core.get_state()
        return {
            "title": "Social State",
            "relationships": [r.to_dict() for r in state.relationships.values()],
            "rumors": [self.present_rumor(r.to_dict()) for r in state.rumors.values()],
            "alliances": [a.to_dict() for a in state.alliances.values()],
        }

    def present_npc_social_view(self, social_view: dict) -> dict:
        """Present an NPC social view in a UI-safe format."""
        return {
            "npc_id": social_view.get("npc_id") or "unknown",
            "target_id": social_view.get("target_id"),
            "relationship": social_view.get("relationship"),
            "reputation": social_view.get("reputation"),
            "active_rumors": [
                self.present_rumor(r) for r in (social_view.get("active_rumors") or [])
            ],
        }

    def present_rumor(self, rumor: dict) -> dict:
        """Present a rumor in a UI-safe format."""
        return {
            "rumor_id": rumor.get("rumor_id") or "unknown",
            "rumor_type": rumor.get("rumor_type") or "unknown",
            "summary": rumor.get("summary") or "",
            "spread_level": rumor.get("spread_level", 0),
            "active": rumor.get("active", True),
        }
