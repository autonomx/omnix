"""Story Director — Dynamic narrative control system.

The Story Director tracks story arcs, manages global tension,
and injects narrative pressure into NPC decision-making.

This is NOT an LLM. It is a system that decides what matters.

Architecture:
    events + memory → narrative shaping → directed outcomes → story arcs

Key capabilities:
    - Arc phase system: build → tension → climax → resolution
    - Memory-driven arc detection: Uses NPC memories to detect emergent arcs
    - Forced events: The director can MANDATE events happen
    - Goal overrides: NPCs following arcs bypass normal GOAP
    - Event bus integration: Reacts to events directly
"""

from typing import Dict, Optional


# Arc phase enumeration
ARC_PHASES = ["build", "tension", "climax", "resolution"]


class StoryArc:
    """A single story arc with phase-based progression.
    
    Each arc progresses through phases based on events and tension.
    """
    
    def __init__(self, arc_type, originator, target, **kwargs):
        """Initialize a story arc.
        
        Args:
            arc_type: Type of arc (revenge, betrayal, alliance).
            originator: The entity that initiated the arc.
            target: The target entity of the arc.
            **kwargs: Additional arc properties.
        """
        self.type = arc_type
        self.originator = originator
        self.target = target
        self.phase = "build"  # build → tension → climax → resolution
        self.progress = 0.0
        self.intensity = kwargs.get("intensity", 1.0)
        self.tick_created = kwargs.get("tick_created", 0)
        self.active = True
        self.members = kwargs.get("members", [])
        self.resolved = False
        self.resolution_event = None
        
    def advance(self, global_tension, events):
        """Advance arc phase based on progress and tension.
        
        Args:
            global_tension: Current global tension level.
            events: Recent events that may affect this arc.
        """
        if not self.active:
            return
            
        # Count relevant events for this arc
        relevant_events = 0
        for event in events:
            if self._is_relevant_event(event):
                relevant_events += 1
                self.progress += 0.3
            else:
                self.progress += 0.05
                
        # Phase transitions
        if self.phase == "build" and self.progress >= 3.0:
            self.phase = "tension"
            self.intensity = min(1.0, self.intensity + 0.2)
        elif self.phase == "tension" and global_tension >= 7.0:
            self.phase = "climax"
            self.intensity = min(1.0, self.intensity + 0.3)
        elif self.phase == "climax":
            # Climax resolves after enough progress
            if self.progress >= 6.0:
                self.phase = "resolution"
                self.active = False
                self.resolved = True
        elif self.phase == "resolution":
            self.active = False
            self.resolved = True
            
    def _is_relevant_event(self, event):
        """Check if an event is relevant to this arc.
        
        Args:
            event: The event to check.
            
        Returns:
            True if the event relates to this arc.
        """
        source = event.get("source")
        target = event.get("target")
        involved = {self.originator, self.target} | set(self.members)
        
        return source in involved or target in involved
        
    def get_forced_goal(self, entity_id):
        """Get a forced goal for an entity in this arc.
        
        During tension and climax phases, the arc mandates behavior.
        
        Args:
            entity_id: The entity to get a forced goal for.
            
        Returns:
            Dict with forced goal, or None if no force applies.
        """
        if self.phase not in ("tension", "climax"):
            return None
            
        if not self.active:
            return None
            
        force_strength = self.intensity if self.phase == "climax" else self.intensity * 0.5
        
        if self.type == "revenge":
            if entity_id == self.originator:
                return {
                    "type": "attack_target",
                    "target": self.target,
                    "reason": "forced_revenge",
                    "force": force_strength,
                }
        elif self.type == "betrayal":
            if entity_id == self.originator:
                return {
                    "type": "attack_target",
                    "target": self.target,
                    "reason": "forced_betrayal",
                    "force": force_strength,
                }
        elif self.type == "alliance":
            if entity_id in self.members and self.target:
                return {
                    "type": "attack_target",
                    "target": self.target,
                    "reason": "forced_alliance",
                    "force": force_strength,
                }
                
        return None
        
    def to_dict(self):
        """Convert arc to dictionary representation."""
        return {
            "type": self.type,
            "originator": self.originator,
            "target": self.target,
            "phase": self.phase,
            "progress": self.progress,
            "intensity": self.intensity,
            "active": self.active,
            "resolved": self.resolved,
            "members": self.members,
        }


class StoryDirector:
    """Controls story arcs and narrative tension.
    
    Tracks active story arcs, manages global tension levels,
    and provides narrative pressure that influences NPC behavior.
    
    Capabilities:
    - Arc creation and phase progression
    - Memory-driven arc detection from NPC experiences
    - Forced narrative events
    - Goal overrides that bypass GOAP
    - Direct event bus subscriptions
    - Bias-based goal shaping (conflict, alliance, mystery)
    - Pacing control based on story phase
    - Anti-repetition cooldown system
    """
    
    def __init__(self):
        """Initialize the Story Director."""
        self.active_arcs = []
        self.resolved_arcs = []
        self.global_tension = 0.0
        self.event_history = []
        self._forced_events = []
        self._event_handlers = {}
        
        # Story phase progression (intro -> build -> tension -> climax -> resolution)
        self.phase = "intro"
        
        # Active story arc type (conflict, alliance, mystery)
        self.arc = None
        
        # Anti-repetition cooldowns: {(npc_id, goal_name): remaining_ticks}
        self.cooldowns: Dict[tuple, int] = {}
        
    def register_handlers(self, event_bus):
        """Register this director as a handler on the event bus.
        
        Args:
            event_bus: The event bus to subscribe to.
        """
        event_bus.subscribe("death", self._on_death)
        event_bus.subscribe("damage", self._on_damage)
        event_bus.subscribe("critical_hit", self._on_critical_hit)
        
    def _on_death(self, session, event):
        """Handle death events - create revenge arcs with high priority."""
        self.global_tension += 3.0
        self._create_revenge_arc(dict(event))
        
    def _on_damage(self, session, event):
        """Handle damage events - increase tension based on severity."""
        amount = event.get("amount", 0)
        if amount >= 10:
            self.global_tension += 1.0
        else:
            self.global_tension += 0.3
            
    def _on_critical_hit(self, session, event):
        """Handle critical hit events - spike tension."""
        self.global_tension += 2.0
        
    def update(self, session, events):
        """Update story state based on events.
        
        Processes events, checks for memory-driven arcs, adjusts tension,
        and advances arc phases.
        
        Args:
            session: The current game session.
            events: List of events that occurred this tick.
        """
        # Check for memory-driven arcs (NPCs with persistent grudge memories)
        self._detect_memory_driven_arcs(session)
        
        for event in events:
            self.event_history.append(event)
            
            # Phase-based arc progression
            for arc in self.active_arcs:
                arc.advance(self.global_tension, events)
                
                # Collect forced goals for current tick
                forced = arc.get_forced_goal(arc.originator)
                if forced:
                    self._add_forced_event(forced)
                    
        # Move resolved arcs to archive
        newly_resolved = [a for a in self.active_arcs if a.resolved]
        for arc in newly_resolved:
            self.active_arcs.remove(arc)
            self.resolved_arcs.append(arc)
        
        # Keep only recent history
        self.event_history = self.event_history[-50:]
        self._decay_tension()
        
    def _decay_tension(self):
        """Decay global tension over time."""
        self.global_tension *= 0.95
        if self.global_tension < 0.1:
            self.global_tension = 0.0
            
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
            if revenge_arc and not self._arc_exists(revenge_arc.originator, revenge_arc.target, "revenge"):
                self.active_arcs.append(revenge_arc)
            
            # Check for alliance arc from healing/positive memories
            alliance_arc = self._detect_alliance_arc(npc, session)
            if alliance_arc and not self._arc_exists(alliance_arc.originator, alliance_arc.target, "alliance"):
                self.active_arcs.append(alliance_arc)
    
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
        
    def get_mandated_goals(self, npc_id):
        """Get goals that an NPC MUST pursue this tick.
        
        During tension and climax phases, arcs force specific goals.
        This bypasses normal GOAP planning.
        
        Args:
            npc_id: The NPC to check for mandated goals.
            
        Returns:
            Dict with mandated goal, or None if no mandate applies.
        """
        arcs = self.get_arcs_for_entity(npc_id)
        
        for arc in arcs:
            forced = arc.get_forced_goal(npc_id)
            if forced:
                return forced
                
        return None
        
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

    # =========================================================
    # DESIGN SPEC METHODS (from rpg-design.txt)
    # =========================================================

    def adjust_goal(self, npc, proposed_goal, context):
        """MAIN ENTRY POINT — Apply arc shaping and pacing to proposed goal.
        
        This is the core method from the design spec that biases NPC goals
        based on story state without overriding simulation logic.
        
        Args:
            npc: The NPC whose goal is being adjusted.
            proposed_goal: The goal proposed by GOAP.
            context: Context dict with recent_events and other state.
            
        Returns:
            Modified goal dict with adjusted priority.
        """
        self._update_tension(context)
        self._update_phase()
        self._update_cooldowns()

        goal = dict(proposed_goal)  # Copy to avoid mutation
        goal.setdefault("priority", 1.0)
        goal.setdefault("name", goal.get("type", "unknown"))

        # Apply arc shaping
        if self.arc == "conflict":
            goal = self._bias_conflict(npc, goal)
        elif self.arc == "alliance":
            goal = self._bias_alliance(npc, goal)
        elif self.arc == "mystery":
            goal = self._bias_mystery(npc, goal)

        # Apply pacing rules
        goal = self._apply_pacing(npc, goal)

        # Apply anti-repetition
        goal = self.prevent_repetition(npc, goal)

        return goal

    def _update_tension(self, context):
        """Update tension based on recent events.
        
        Tension rises and falls based on what happens in the world.
        
        Event weights:
        - damage: +0.05
        - death: +0.2
        - assist: -0.03 (reduces tension)
        
        Args:
            context: Context dict with recent_events list.
        """
        events = context.get("recent_events", [])
        delta = 0.0

        for e in events:
            etype = e.get("type", "")
            if etype == "damage":
                delta += 0.05
            elif etype == "death":
                delta += 0.2
            elif etype == "assist":
                delta -= 0.03

        self.global_tension = max(0.0, min(1.0, self.global_tension + delta))

    def _update_phase(self):
        """Update story phase based on current tension.
        
        Phase progression:
        - intro: tension < 0.2 (calm, exploratory)
        - build: tension < 0.5 (suspicion rising)
        - tension: tension < 0.8 (cautious, reactive)
        - climax: tension >= 0.8 (decisive, emotional)
        
        Also triggers auto-arc selection.
        """
        if self.global_tension < 0.2:
            self.phase = "intro"
        elif self.global_tension < 0.5:
            self.phase = "build"
        elif self.global_tension < 0.8:
            self.phase = "tension"
        elif self.global_tension >= 0.8:
            self.phase = "climax"

        # Auto-select arc based on tension
        self.auto_select_arc()

    def auto_select_arc(self):
        """Design item 9: Dynamically select story arc based on tension.
        
        Arc selection:
        - Low tension (< 0.2): mystery arc (exploration)
        - Medium tension (0.2-0.6): alliance arc (cooperation)
        - High tension (> 0.6): conflict arc (combat)
        """
        if self.global_tension < 0.2:
            self.arc = "mystery"
        elif self.global_tension < 0.6:
            self.arc = "alliance"
        else:
            self.arc = "conflict"

    # =========================================================
    # GOAL SHAPING METHODS (design items 5-6)
    # =========================================================

    def _bias_conflict(self, npc, goal):
        """Bias goal toward conflict behavior.
        
        During conflict arcs:
        - Attack goals get +30% priority boost
        - Talk/social goals get -30% penalty
        
        Args:
            npc: The NPC whose goal is being biased.
            goal: The goal dict to modify.
            
        Returns:
            Modified goal dict.
        """
        goal_name = goal.get("name", goal.get("type", ""))

        if "attack" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 1.3

        if "talk" in goal_name.lower() or "assist" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 0.7

        return goal

    def _bias_alliance(self, npc, goal):
        """Bias goal toward alliance/cooperation behavior.
        
        During alliance arcs:
        - Assist/help goals get +50% priority boost
        - Attack goals get -40% penalty
        
        Args:
            npc: The NPC whose goal is being biased.
            goal: The goal dict to modify.
            
        Returns:
            Modified goal dict.
        """
        goal_name = goal.get("name", goal.get("type", ""))

        if "assist" in goal_name.lower() or "help" in goal_name.lower() or "ally" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 1.5

        if "attack" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 0.6

        return goal

    def _bias_mystery(self, npc, goal):
        """Bias goal toward exploration/mystery behavior.
        
        During mystery arcs:
        - Explore/observe goals get +40% priority boost
        - Attack goals get -20% penalty
        
        Args:
            npc: The NPC whose goal is being biased.
            goal: The goal dict to modify.
            
        Returns:
            Modified goal dict.
        """
        goal_name = goal.get("name", goal.get("type", ""))

        if "explore" in goal_name.lower() or "observe" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 1.4

        if "attack" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 0.8

        return goal

    def _apply_pacing(self, npc, goal):
        """Apply pacing rules based on current story phase.
        
        Pacing ensures natural story progression:
        - Intro: Suppress attacks (30% priority) for calm beginning
        - Tension: Boost all goals by 20% for building drama
        - Climax: Attacks get 50% boost for decisive resolution
        
        Args:
            npc: The NPC whose goal is being paced.
            goal: The goal dict to modify.
            
        Returns:
            Modified goal dict.
        """
        goal_name = goal.get("name", goal.get("type", ""))

        if self.phase == "intro":
            # Calm beginning - suppress aggression
            if "attack" in goal_name.lower():
                goal["priority"] = goal.get("priority", 1.0) * 0.3

        elif self.phase == "tension":
            # Building drama - boost everything
            goal["priority"] = goal.get("priority", 1.0) * 1.2

        elif self.phase == "climax":
            # Decisive resolution - boost attacks
            if "attack" in goal_name.lower():
                goal["priority"] = goal.get("priority", 1.0) * 1.5

        return goal

    def prevent_repetition(self, npc, goal):
        """Design item 11: Anti-repetition guard.
        
        Prevents NPCs from repeating the same goal too frequently.
        Sets a 3-tick cooldown on goals after they're used.
        
        Args:
            npc: The NPC whose goal is being checked.
            goal: The goal dict to check.
            
        Returns:
            Modified goal dict with priority reduced if on cooldown.
        """
        key = (npc.id, goal.get("name", goal.get("type", "")))

        if self.cooldowns.get(key, 0) > 0:
            goal["priority"] = goal.get("priority", 1.0) * 0.2

        self.cooldowns[key] = 3
        return goal

    def _update_cooldowns(self):
        """Tick down all cooldown counters each frame."""
        for key in list(self.cooldowns.keys()):
            self.cooldowns[key] -= 1
            if self.cooldowns[key] <= 0:
                del self.cooldowns[key]

    def get_story_state(self):
        """Get current story state for LLM grounding.
        
        Design item 10: Returns phase, tension, and arc
        for injection into scene grounding.
        
        Returns:
            Dict with story state values.
        """
        return {
            "phase": self.phase,
            "tension": round(self.global_tension, 3),
            "arc": self.arc,
        }


def select_events_for_scene(events, director):
    """Only show narratively important events.
    
    Filters events based on their narrative significance and
    current tension level.
    
    Args:
        events: List of events to filter.
        director: The StoryDirector instance for tension context.
        
    Returns:
        Filtered list of important events (max 5).
    """
    if not events:
        return []
        
    important = []
    
    # Priority weights for event types
    priority_weights = {
        "death": 10,
        "critical_hit": 8,
        "damage": 3,
        "betrayal": 9,
        "alliance_formed": 6,
        "move": 1,
        "observe": 1,
    }
    
    scored_events = []
    for event in events:
        event_type = event.get("type", "unknown")
        weight = priority_weights.get(event_type, 2)
        
        # Boost weight during high tension
        if director.global_tension > 5:
            weight *= 1.5
            
        scored_events.append((weight, event))
        
    # Sort by score (descending) and take top events
    scored_events.sort(key=lambda x: -x[0])
    
    important = [e for _, e in scored_events[:5]]
    
    return important