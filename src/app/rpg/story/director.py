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

from typing import Any, Dict, List, Optional

from .director_types import DirectorOutput

from .director_arc_management import DirectorArcManagementMixin
from .director_arcs import ARC_PHASES as ARC_PHASES
from .director_arcs import StoryArc as StoryArc
from .director_goal_shaping import DirectorGoalShapingMixin
class StoryDirector(DirectorArcManagementMixin, DirectorGoalShapingMixin):
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

        # Fix #2: Local tension per entity (avoids world-wide escalation)
        self.local_tension: Dict[str, float] = {}

        # Fix #4: Arc creation cooldowns to prevent revenge loops
        self.arc_cooldowns: Dict[tuple, int] = {}  # {(originator, target, type): remaining_ticks}

    # =========================================================
    # PATCH 1: AUTHORITATIVE DIRECTOR OUTPUT (from rpg-design.txt)
    # =========================================================

    def decide(self, session, player_intent: Dict[str, Any]) -> 'DirectorOutput':
        """MAIN ENTRY POINT — Decide story direction for this turn.

        This is the authoritative Director Output Contract from the design spec.
        It returns structured output that other systems consume:
        - NPC goal updates
        - Story events to inject
        - World state updates
        - Tension delta
        - Future beats (forward planning 3-5 turns ahead)

        Args:
            session: The current game session.
            player_intent: Structured intent from the player's input.

        Returns:
            DirectorOutput with structured decisions.
        """
        # Get current story state
        self._update_phase()

        # GAP 4: Build memory context (Director uses memory for continuity)
        memory_context = self._build_memory_context(session)

        # Calculate tension delta based on current state and intent
        tension_delta = self._calculate_tension_delta(player_intent)

        # Get NPC goal updates based on current arcs
        npc_goal_updates = self._get_npc_goal_updates(session, player_intent, memory_context)

        # Get story events to inject based on narrative needs
        story_events = self._get_story_events(session, player_intent, memory_context)

        # GAP 6: Maybe inject surprise/twist events for perceived intelligence
        surprise = self._maybe_inject_surprise(session)
        if surprise:
            story_events.append(surprise)

        # Get world state updates
        world_state_updates = self._get_world_state_updates(session, player_intent)

        # GAP 1: Forward planning — plan beats for next 3-5 turns
        future_beats = self._plan_story_beats(session, memory_context)

        return DirectorOutput(
            npc_goal_updates=npc_goal_updates,
            story_events=story_events,
            world_state_updates=world_state_updates,
            tension_delta=tension_delta,
            future_beats=future_beats,
        )

    # =========================================================
    # NEW METHODS — GAP 1, GAP 4, GAP 6
    # =========================================================

    def _build_memory_context(self, session) -> Dict[str, Any]:
        """GAP 4: Build memory context that Director uses for continuity.

        The Director needs to know about:
        - Recent conflicts and who was involved
        - Player reputation (aggressive vs diplomatic history)
        - Past arcs and their resolutions
        - Long-term consequences

        Args:
            session: The current game session.

        Returns:
            Memory context dict.
        """
        # Player reputation from global tension history
        aggressive_count = sum(
            1 for e in self.event_history
            if e.get("type") in ("damage", "death", "critical_hit")
        )
        peaceful_count = sum(
            1 for e in self.event_history
            if e.get("type") in ("heal", "assist")
        )

        player_reputation = "neutral"
        if aggressive_count > peaceful_count + 2:
            player_reputation = "aggressive"
        elif peaceful_count > aggressive_count + 2:
            player_reputation = "diplomatic"

        # Extract recent conflicts
        recent_conflicts = [
            e for e in self.event_history
            if e.get("type") in ("damage", "death", "betrayal")
        ][-10:]

        # Resolve arc history
        resolved_summary = []
        for arc in self.resolved_arcs[-5:]:
            resolved_summary.append({
                "type": arc.type,
                "originator": arc.originator,
                "target": arc.target,
                "phase_reached": arc.phase,
            })

        return {
            "player_reputation": player_reputation,
            "recent_conflicts": recent_conflicts,
            "resolved_arcs": resolved_summary,
            "active_arc_count": len(self.active_arcs),
            "total_events_seen": len(self.event_history),
        }

    def _plan_story_beats(self, session, memory_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """GAP 1: Forward planning — plan story beats for next 3-5 turns.

        Instead of just reacting to the current turn, the Director plans
        ahead to create:
        - Suspense (building toward future events)
        - Continuity (events connect to past events)
        - Intentional storytelling (arcs have deliberate pacing)

        Args:
            session: The current game session.
            memory_context: Memory context from _build_memory_context().

        Returns:
            List of future beat dicts with {"turn": +N, "event": {...}}.
        """
        beats = []

        # Plan based on current arcs and phase
        for arc in self.active_arcs:
            if not arc.active:
                continue

            if arc.phase == "build":
                # Next turns: escalate hints about this arc
                beats.append({
                    "turn": 1,
                    "event": {
                        "type": "story_event",
                        "summary": f"Subtle signs of a {arc.type} begin to appear",
                        "tension": 0.1,
                        "tags": ["foreshadowing", arc.type],
                    }
                })
                beats.append({
                    "turn": 3,
                    "event": {
                        "type": "story_event",
                        "summary": f"The {arc.type} becomes harder to ignore",
                        "tension": 0.3,
                        "tags": ["escalation", arc.type],
                    }
                })

            elif arc.phase == "tension":
                # Next turns: climax approaching
                beats.append({
                    "turn": 1,
                    "event": {
                        "type": "story_event",
                        "summary": f"Tension around the {arc.type} mounts",
                        "tension": 0.4,
                        "tags": ["building", arc.type],
                    }
                })
                beats.append({
                    "turn": 2,
                    "event": {
                        "type": "story_event",
                        "summary": f"The {arc.type} is about to reach its breaking point",
                        "tension": 0.6,
                        "tags": ["pre-climax", arc.type],
                    }
                })

            elif arc.phase == "climax":
                # Resolution approaching
                beats.append({
                    "turn": 1,
                    "event": {
                        "type": "story_event",
                        "summary": f"The {arc.type} reaches its peak",
                        "tension": 0.8,
                        "tags": ["climax", arc.type],
                    }
                })
                beats.append({
                    "turn": 2,
                    "event": {
                        "type": "story_event",
                        "summary": f"Aftermath of the {arc.type} settles in",
                        "tension": -0.2,
                        "tags": ["resolution", arc.type],
                    }
                })

        # Plan based on player reputation
        if memory_context.get("player_reputation") == "aggressive":
            beats.append({
                "turn": 2,
                "event": {
                    "type": "story_event",
                    "summary": "Word of your violence spreads — NPCs grow cautious",
                    "tension": 0.3,
                    "tags": ["reputation", "consequence"],
                }
            })

        return beats[:5]  # Cap at 5 beats

    def _maybe_inject_surprise(self, session) -> Optional[Dict[str, Any]]:
        """GAP 6: Inject unexpected events for perceived intelligence.

        Stories need chaos. At random intervals, the Director injects
        surprises that:
        - Break predictability
        - Create emergent story moments
        - Make the world feel alive and unscripted

        Args:
            session: The current game session.

        Returns:
            Surprise event dict, or None.
        """
        import random

        # 10% chance of surprise each turn (adjustable)
        surprise_chance = 0.1

        # Don't inject surprises during calm phase (too disruptive)
        if self.phase == "intro":
            surprise_chance *= 0.5

        # Don't inject too many surprises if we've had recent ones
        recent_surprises = sum(
            1 for e in self.event_history[-20:]
            if e.get("tags") and "twist" in e.get("tags", [])
        )
        if recent_surprises >= 2:
            return None  # Too many surprises recently

        if random.random() >= surprise_chance:
            return None

        # Surprise event pool
        import random
        surprises = [
            {
                "type": "story_event",
                "summary": "An unexpected figure steps from the shadows",
                "tension": 0.5,
                "tags": ["twist", "mystery"],
            },
            {
                "type": "story_event",
                "summary": "A distant sound echoes — something approaches",
                "tension": 0.3,
                "tags": ["twist", "threat"],
            },
            {
                "type": "story_event",
                "summary": "The ground trembles slightly — was that movement beneath?",
                "tension": 0.4,
                "tags": ["twist", "environment"],
            },
            {
                "type": "story_event",
                "summary": "A forgotten memory surfaces — with painful clarity",
                "tension": 0.2,
                "tags": ["twist", "memory"],
            },
            {
                "type": "story_event",
                "summary": "A messenger arrives with urgent news",
                "tension": 0.4,
                "tags": ["twist", "news"],
            },
        ]

        return random.choice(surprises)

    def _get_npc_goal_updates(
        self, session, player_intent: Dict[str, Any], memory_context: Dict[str, Any] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get goal updates for NPCs based on story direction.

        Args:
            session: The current game session.
            player_intent: Structured player intent.
            memory_context: Memory context for continuity (GAP 4).

        Returns:
            Dict mapping NPC IDs to lists of goal dicts.
        """
        del memory_context  # Available for future use
        updates: Dict[str, List[Dict[str, Any]]] = {}

        # NPCs with active arcs get goal updates
        for arc in self.active_arcs:
            if arc.phase in ("tension", "climax") and arc.active:
                # Update originator goals
                if arc.originator not in updates:
                    updates[arc.originator] = []

                goal = arc.get_forced_goal(arc.originator)
                if goal:
                    updates[arc.originator].append(goal)

        # Players who damaged NPCs make them hostile
        player_target = player_intent.get("target")
        if player_target and player_intent.get("type") == "attack":
            npc = next(
                (n for n in session.npcs if n.id == player_target and n.is_active),
                None
            )
            if npc:
                if player_target not in updates:
                    updates[player_target] = []
                updates[player_target].append({
                    "type": "defend",
                    "target": "player",
                    "reason": "player_attack",
                    "priority": 2.0,
                })

        return updates

    def _get_story_events(
        self, session, player_intent: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get story events to inject into the event stream.

        These are narrative-level events the Director creates to
        maintain story pacing and tension.

        Args:
            session: The current game session.
            player_intent: Structured player intent.

        Returns:
            List of story event dicts.
        """
        events = []

        # Tension-based story beats
        tension_level = self.get_tension_level()

        if tension_level == "climax" and self.arc:
            events.append({
                "type": "story_event",
                "summary": f"The tension reaches its peak as the {self.arc} arc climaxes",
                "tension": 1.0,
                "tags": ["climax", self.arc],
            })
        elif tension_level == "tense" and self.arc:
            events.append({
                "type": "story_event",
                "summary": f"Shadows of the {self.arc} draw closer",
                "tension": 0.6,
                "tags": ["building_tension", self.arc],
            })

        # Arc-specific story beats
        for arc in self.active_arcs:
            if arc.phase == "build" and arc.progress >= 2:
                events.append({
                    "type": "story_event",
                    "summary": f"Whispers of a {arc.type} begin to spread",
                    "tension": 0.2,
                    "tags": ["arc_building", arc.type],
                })

        return events

    def _get_world_state_updates(
        self, session, player_intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get world state updates from the Director.

        Args:
            session: The current game session.
            player_intent: Structured player intent.

        Returns:
            Dict of world state key-value updates.
        """
        updates = {}

        # Update alert level based on tension
        if hasattr(session, 'world'):
            current_alert = getattr(session.world, 'alert_level', 0)
            tension_alert = min(5, int(self.global_tension / 2))
            if tension_alert != current_alert:
                updates["alert_level"] = tension_alert

        return updates

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

        # Fix #4: Tick down arc cooldowns
        self._update_arc_cooldowns()

        for event in events:
            self.event_history.append(event)

            # Fix #2: Update local tension for involved entities
            self._update_local_tension(event)

            # Phase-based arc progression
            for arc in self.active_arcs:
                arc.advance(self._get_effective_tension(arc.originator), events)

                # Collect forced goals for current tick
                forced = arc.get_forced_goal(arc.originator)
                if forced:
                    self._add_forced_event(forced)

        # Move resolved arcs to archive
        newly_resolved = [a for a in self.active_arcs if a.resolved]
        for arc in newly_resolved:
            # Fix #5: Apply resolution effects before archiving
            self._apply_resolution_effects(arc)
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

        # Fix #2: Decay local tension too
        for entity_id in list(self.local_tension.keys()):
            self.local_tension[entity_id] *= 0.93
            if self.local_tension[entity_id] < 0.1:
                del self.local_tension[entity_id]

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
