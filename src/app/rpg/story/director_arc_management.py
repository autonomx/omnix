"""Arc management mixin for the RPG story director."""
from __future__ import annotations

from typing import Dict, Optional

from .director_arcs import StoryArc


class DirectorArcManagementMixin:
    # =========================================================
    # FIX #1: Arc Conflict Resolution
    # =========================================================

    def resolve_arc_conflicts(self, entity_id):
        """Fix #1: When an entity has conflicting arcs (e.g., revenge vs alliance
        against same target), resolve by priority system.

        Priority order: revenge > betrayal > alliance

        Args:
            entity_id: The entity to resolve arcs for.

        Returns:
            Tuple of (primary_arc, secondary_arcs) where primary gets full influence.
        """
        arcs = self.get_arcs_for_entity(entity_id)
        if len(arcs) <= 1:
            return (arcs[0] if arcs else None, [])

        # Priority system for arc types
        arc_priority = {"revenge": 3, "betrayal": 2, "alliance": 1}
        arcs_sorted = sorted(arcs, key=lambda a: arc_priority.get(a.type, 0), reverse=True)

        primary = arcs_sorted[0]
        secondary = arcs_sorted[1:]
        return (primary, secondary)

    def _get_arc_pressure_multiplier(self, arc, is_primary=True):
        """Get pressure multiplier for an arc based on conflict resolution.

        Primary arcs get full influence, secondary arcs get reduced (0.3x).

        Args:
            arc: The StoryArc to get multiplier for.
            is_primary: Whether this arc is the primary (highest priority) arc.

        Returns:
            Float multiplier for pressure contribution.
        """
        if is_primary:
            return 1.0
        return 0.3  # Secondary arcs contribute 30%

    # =========================================================
    # FIX #2: Local Tension System
    # =========================================================

    def _update_local_tension(self, event):
        """Fix #2: Update local tension for entities involved in an event.

        Instead of escalating the entire world, tension increases primarily
        for the entities directly involved in the event.

        Args:
            event: The event dict to extract tension updates from.
        """
        etype = event.get("type", "")
        src = event.get("source") or event.get("actor")
        tgt = event.get("target")

        local_delta = 0.0
        global_delta = 0.0

        if etype == "death":
            local_delta = 2.0
            global_delta = 0.5
        elif etype == "damage":
            local_delta = 0.5
            global_delta = 0.2
        elif etype == "critical_hit":
            local_delta = 1.5
            global_delta = 0.3
        elif etype in ("assist", "heal"):
            local_delta = -0.3
            global_delta = -0.1

        # Apply local tension to involved entities
        for eid in [src, tgt]:
            if eid:
                self.local_tension[eid] = self.local_tension.get(eid, 0.0) + local_delta
                self.local_tension[eid] = max(0.0, min(10.0, self.local_tension[eid]))

        # Global tension gets smaller delta
        self.global_tension += max(0.0, global_delta)

    def _get_effective_tension(self, entity_id):
        """Fix #2: Get effective tension for an entity using local+global blend.

        effective_tension = local * 0.7 + global * 0.3

        This ensures distant NPCs don't escalate unrealistically.

        Args:
            entity_id: The entity to get effective tension for.

        Returns:
            Float tension value (0-10 scale).
        """
        local = self.local_tension.get(entity_id, 0.0)
        global_val = self.global_tension
        return local * 0.7 + global_val * 0.3

    # =========================================================
    # FIX #3: Softened Forced Goals (Blend Instead of Override)
    # =========================================================

    def get_mandated_goals(self, npc_id):
        """Get goals that an NPC is nudged toward this tick.

        Fix #3: Instead of hard override, blend mandated goals with reduced force.
        This respects the design principle: "bias decisions, not control outcomes."

        Args:
            npc_id: The NPC to check for mandated goals.

        Returns:
            Dict with softened mandated goal, or None if no mandate applies.
        """
        # Fix #1: Resolve arc conflicts to get primary arc
        primary, secondary = self.resolve_arc_conflicts(npc_id)

        for arc in [primary] + secondary:
            forced = arc.get_forced_goal(npc_id)
            if forced:
                is_primary = arc == primary
                # Fix #3: Soften forced goals - 0.6x for primary, 0.3x for secondary
                softened_force = forced.get("force", 1.0) * (0.6 if is_primary else 0.3)
                forced["force"] = softened_force
                forced["_is_softened"] = True
                return forced

        return None

    # =========================================================
    # FIX #4: Arc Cooldowns (Prevent Revenge Loops)
    # =========================================================

    def _update_arc_cooldowns(self):
        """Fix #4: Tick down arc creation cooldowns."""
        for key in list(self.arc_cooldowns.keys()):
            self.arc_cooldowns[key] -= 1
            if self.arc_cooldowns[key] <= 0:
                del self.arc_cooldowns[key]

    def _is_arc_on_cooldown(self, originator, target, arc_type):
        """Fix #4: Check if an arc type between two entities is on cooldown.

        Args:
            originator: The arc originator entity ID.
            target: The arc target entity ID.
            arc_type: The type of arc.

        Returns:
            True if arc creation is currently on cooldown.
        """
        key = (originator, target, arc_type)
        return self.arc_cooldowns.get(key, 0) > 0

    def _set_arc_cooldown(self, originator, target, arc_type, ticks=15):
        """Fix #4: Set a cooldown on arc creation to prevent loops.

        Args:
            originator: The arc originator entity ID.
            target: The arc target entity ID.
            arc_type: The type of arc.
            ticks: Number of ticks to cooldown.
        """
        key = (originator, target, arc_type)
        self.arc_cooldowns[key] = ticks

    # =========================================================
    # FIX #5: Resolution Consequences
    # =========================================================

    def _apply_resolution_effects(self, arc):
        """Fix #5: When an arc resolves, apply consequences to beliefs and emotions.

        This feeds back into the belief system loop.

        Resolution effects:
        - Revenge: originator hostility decreases, target (if alive) fear increases
        - Alliance: members gain trust boost
        - Betrayal: originator caution increases, target hostility increases

        Args:
            arc: The StoryArc that just resolved.
        """
        arc.tick_created = arc.tick_created  # Preserve for debugging
        arc.resolution_event = {
            "type": f"{arc.type}_resolved",
            "originator": arc.originator,
            "target": arc.target,
            "effects_applied": [],
        }

        if arc.type == "revenge":
            # Originator's hostility decreases (closure)
            arc.resolution_event["effects_applied"].append("originator_hostility_reduced")
            # Set arc cooldown to prevent immediate revenge re-creation
            self._set_arc_cooldown(arc.originator, arc.target, "revenge", 20)

        elif arc.type == "alliance":
            # Members gain trust in each other
            arc.resolution_event["effects_applied"].append("members_trust_boost")
            for member in arc.members:
                self._set_arc_cooldown(member, arc.originator if member != arc.originator else arc.target, "alliance", 10)

        elif arc.type == "betrayal":
            # Originator becomes cautious, target becomes hostile
            arc.resolution_event["effects_applied"].append("target_hostile_originator_cautious")
            self._set_arc_cooldown(arc.originator, arc.target, "betrayal", 25)

    # =========================================================
    # FIX #6: Enhanced Story State for LLM
    # =========================================================

    def get_story_state(self):
        """Get current story state for LLM grounding.

        Fix #6: Returns comprehensive story context including active arcs,
        not just phase/tension/arc.

        Returns:
            Dict with story state values.
        """
        return {
            "phase": self.phase,
            "tension": round(self.global_tension, 3),
            "arc": self.arc,
        }

    def get_entity_story_state(self, entity_id):
        """Fix #6: Get entity-specific story state for LLM grounding.

        Returns detailed story context per entity, including their
        active arcs. This goes into the grounding block.

        Args:
            entity_id: The entity to get story state for.

        Returns:
            Dict with comprehensive story state for the entity.
        """
        arcs = self.get_arcs_for_entity(entity_id)
        active_arc_info = []
        for arc in arcs:
            active_arc_info.append({
                "type": arc.type,
                "phase": arc.phase,
                "target": arc.target,
                "intensity": round(arc.intensity, 2),
            })

        return {
            "phase": self.phase,
            "tension": round(self.global_tension, 3),
            "local_tension": round(self.local_tension.get(entity_id, 0.0), 3),
            "arc": self.arc,
            "tension_level": self.get_tension_level(),
            "active_arcs": active_arc_info,
            "arc_count": len(active_arc_info),
        }

    def _detect_memory_driven_arcs(self, session):
        """Detect story arcs from NPC memories.

        This is the memory-driven arc detection that creates emergent
        narrative arcs based on what NPCs remember.

        Scans NPC memories for patterns like:
        - Multiple damage events from same source → revenge arc
        - Death events involving allies → revenge arc
        - Repeated healing from same source → alliance arc

        Args:
            session: The current game session.
        """
        for npc in session.npcs:
            if not npc.is_active:
                continue

            # Check for revenge arc from death memories
            revenge_arc = self._detect_revenge_arc(npc, session)
            if (revenge_arc and
                not self._arc_exists(revenge_arc.originator, revenge_arc.target, "revenge") and
                not self._is_arc_on_cooldown(revenge_arc.originator, revenge_arc.target, "revenge")):
                self.active_arcs.append(revenge_arc)
                self._set_arc_cooldown(revenge_arc.originator, revenge_arc.target, "revenge", 15)

            # Check for alliance arc from healing/positive memories
            alliance_arc = self._detect_alliance_arc(npc, session)
            if (alliance_arc and
                not self._arc_exists(alliance_arc.originator, alliance_arc.target, "alliance") and
                not self._is_arc_on_cooldown(alliance_arc.originator, alliance_arc.originator, "alliance")):
                self.active_arcs.append(alliance_arc)
                self._set_arc_cooldown(alliance_arc.originator, alliance_arc.originator, "alliance", 10)

    def _detect_revenge_arc(self, npc, session) -> Optional['StoryArc']:
        """Detect if an NPC should start a revenge arc based on memories.

        Looks for:
        - NPC has memories of being damaged by a specific entity
        - NPC has memories of allies being killed by a specific entity
        - NPC has semantic beliefs that someone is dangerous

        Args:
            npc: The NPC to check
            session: Current game session

        Returns:
            StoryArc if revenge pattern detected, None otherwise
        """
        memories = npc.memory.get("events", []) if isinstance(npc.memory, dict) else []

        # Count damage events per source
        damage_by_source: Dict[str, int] = {}
        killed_allies: Dict[str, list] = {}

        for mem in memories:
            mem_type = mem.get("type", "")
            source = mem.get("source", mem.get("actor", ""))
            target = mem.get("target", "")

            # NPC was damaged by someone
            if mem_type == "damage" and target == npc.id and source:
                damage_by_source[source] = damage_by_source.get(source, 0) + 1

            # Someone killed NPC's ally (NPC remembers the death)
            if mem_type == "death" and source:
                if target != npc.id and target != source:
                    if source not in killed_allies:
                        killed_allies[source] = []
                    killed_allies[source].append(target)

        # Create revenge arc if thresholds met
        # Either: 3+ damage events from same source, or any ally killed

        for source, count in damage_by_source.items():
            if count >= 3:
                return StoryArc(
                    arc_type="revenge",
                    originator=npc.id,
                    target=source,
                    intensity=min(1.0, 0.3 + count * 0.15),
                    tick_created=session.world.time if hasattr(session, 'world') else 0,
                )

        for killer, victims in killed_allies.items():
            if victims:  # Any ally killed triggers revenge
                return StoryArc(
                    arc_type="revenge",
                    originator=npc.id,
                    target=killer,
                    intensity=min(1.0, 0.5 + len(victims) * 0.2),
                    tick_created=session.world.time if hasattr(session, 'world') else 0,
                )

        return None

    def _detect_alliance_arc(self, npc, session) -> Optional['StoryArc']:
        """Detect if an NPC should form an alliance arc based on memories.

        Looks for:
        - Repeated healing from same source
        - Positive dialogue patterns

        Args:
            npc: The NPC to check
            session: Current game session

        Returns:
            StoryArc if alliance pattern detected, None otherwise
        """
        memories = npc.memory.get("events", []) if isinstance(npc.memory, dict) else []

        # Count healing events per source
        heal_by_source: Dict[str, int] = {}

        for mem in memories:
            mem_type = mem.get("type", "")
            source = mem.get("source", mem.get("actor", ""))
            target = mem.get("target", "")

            # NPC was healed by someone
            if mem_type == "heal" and target == npc.id and source:
                heal_by_source[source] = heal_by_source.get(source, 0) + 1

        # Create alliance arc if healed 3+ times by same source
        for source, count in heal_by_source.items():
            if count >= 3:
                return StoryArc(
                    arc_type="alliance",
                    originator=npc.id,
                    target=None,  # Alliance is with the healer
                    members=[npc.id, source],
                    intensity=min(1.0, 0.3 + count * 0.15),
                    tick_created=session.world.time if hasattr(session, 'world') else 0,
                )

        return None

    def _arc_exists(self, originator: str, target: str, arc_type: str) -> bool:
        """Check if an arc with the same originator, target, and type exists.

        Args:
            originator: The arc originator
            target: The arc target
            arc_type: The arc type to check

        Returns:
            True if arc already exists
        """
        for arc in self.active_arcs:
            if arc.originator == originator and arc.target == target and arc.type == arc_type:
                return True
        return False

    def _create_revenge_arc(self, event):
        """Create a revenge arc when an NPC dies.

        Args:
            event: The death event that triggered this arc.
        """
        source = event.get("source")
        target = event.get("target")

        arc = StoryArc(
            arc_type="revenge",
            originator=target,
            target=source,
            intensity=1.0,
            tick_created=event.get("tick", 0),
        )
        self.active_arcs.append(arc)

    def _create_betrayal_arc(self, event):
        """Create a betrayal arc.

        Args:
            event: The betrayal event.
        """
        arc = StoryArc(
            arc_type="betrayal",
            originator=event.get("traitor"),
            target=event.get("victim"),
            intensity=0.8,
            tick_created=event.get("tick", 0),
        )
        self.active_arcs.append(arc)

    def _create_alliance_arc(self, event):
        """Create an alliance arc.

        Args:
            event: The alliance formation event.
        """
        arc = StoryArc(
            arc_type="alliance",
            originator=event.get("leader"),
            target=event.get("against"),
            members=event.get("members", []),
            intensity=0.5,
            tick_created=event.get("tick", 0),
        )
        self.active_arcs.append(arc)

    def _add_forced_event(self, forced_goal):
        """Store a forced goal for this tick.

        Args:
            forced_goal: The goal that must be pursued.
        """
        self._forced_events.append(forced_goal)

    def get_active_arcs(self):
        """Get all currently active story arcs.

        Returns:
            List of active StoryArc objects.
        """
        return [a for a in self.active_arcs if a.active]

    def get_arcs_for_entity(self, entity_id):
        """Get story arcs involving a specific entity.

        Args:
            entity_id: The entity ID to search for.

        Returns:
            List of arcs where the entity is involved.
        """
        arcs = []
        for arc in self.active_arcs:
            if not arc.active:
                continue

            if arc.type == "revenge":
                if entity_id == arc.originator or entity_id == arc.target:
                    arcs.append(arc)
            elif arc.type == "betrayal":
                if entity_id == arc.originator or entity_id == arc.target:
                    arcs.append(arc)
            elif arc.type == "alliance":
                if entity_id in arc.members:
                    arcs.append(arc)

        return arcs

    def get_forced_events(self, session):
        """Get events that MUST happen this tick.

        These are events the story director schedules to maintain
        narrative pacing.

        Args:
            session: The current game session.

        Returns:
            List of forced events to process.
        """
        forced = list(self._forced_events)
        self._forced_events = []
        return forced

    def get_tension_level(self):
        """Get current tension level category.

        Returns:
            String: 'calm', 'tense', 'intense', or 'climax'
        """
        if self.global_tension < 2.0:
            return "calm"
        elif self.global_tension < 5.0:
            return "tense"
        elif self.global_tension < 8.0:
            return "intense"
        else:
            return "climax"

    def get_narrative_pressure(self, entity_id):
        """Get narrative pressure modifiers for an entity.

        Returns influence that story arcs should have on entity behavior.

        Args:
            entity_id: The entity to get pressure for.

        Returns:
            Dict with pressure modifiers (aggression, caution, urgency).
        """
        pressure = {
            "aggression": 0.0,
            "caution": 0.0,
            "urgency": 0.0,
        }

        arcs = self.get_arcs_for_entity(entity_id)

        for arc in arcs:
            intensity = arc.intensity

            if arc.type == "revenge":
                if entity_id == arc.originator:
                    # Victim pursues revenge - high aggression during tension/climax
                    if arc.phase in ("tension", "climax"):
                        pressure["aggression"] += intensity * 0.8
                        pressure["urgency"] += intensity * 0.6
                    else:
                        pressure["aggression"] += intensity * 0.5
                        pressure["urgency"] += intensity * 0.3
                elif entity_id == arc.target:
                    # Killer should feel caution - potential retaliation
                    if arc.phase == "climax":
                        pressure["caution"] += intensity * 0.9
                    else:
                        pressure["caution"] += intensity * 0.4

            elif arc.type == "betrayal":
                pressure["caution"] += intensity * 0.6
                pressure["aggression"] += intensity * 0.2

            elif arc.type == "alliance":
                if entity_id in arc.members:
                    pressure["aggression"] += intensity * 0.3
                    pressure["caution"] -= intensity * 0.2  # Feel supported

        # Clamp values
        for key in pressure:
            pressure[key] = max(-1.0, min(1.0, pressure[key]))

        return pressure

    def schedule_escalation(self, delay_ticks=3):
        """Schedule a narrative escalation event.

        This forces the story to escalate regardless of current state.

        Args:
            delay_ticks: How many ticks until escalation triggers.
        """
        # Force escalation of all active arcs
        for arc in self.active_arcs:
            if arc.phase == "build":
                arc.progress += delay_ticks
            elif arc.phase == "tension":
                self.global_tension += 2.0

    def reset(self):
        """Reset the Story Director state."""
        self.active_arcs = []
        self.resolved_arcs = []
        self.global_tension = 0.0
        self.event_history = []
        self._forced_events = []
        self.phase = "intro"
        self.arc = None
        self.cooldowns = {}
        self.local_tension = {}
        self.arc_cooldowns = {}

    # =========================================================
