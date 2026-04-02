"""Director — Emergence-driven narrative intervention system.

The Director observes system-level patterns and injects events to shape
narrative without scripting. It creates guided emergence rather than
random or scripted events.

NPC Loop:  DECIDE -> ACT -> OUTCOME -> RECORD
Director Loop:  OBSERVE -> ANALYZE -> DECIDE -> INJECT EVENT

The Director is called once per game tick AFTER all NPCs act.
It receives:
  - world_state: The current state of the game world
  - npcs: List of all active NPCs
  - recent_outcomes: List of action outcome objects

It then:
  1. Analyzes signals through the emergence tracker
  2. Decides whether to intervene based on thresholds
  3. Creates and applies an event if intervention is warranted
  4. Records the event in history

Design principles from rpg-design.txt:
  - "Not random events. Not scripted story. -> Guided emergence"
  - "The world is smart" (not just NPCs, the world itself adapts)
  - "Narrative without scripting" (events serve the system, not a story script)

Intervention types:
  - Stagnation (>0.7) -> twist: Inject unexpected events
  - Conflict spike (>0.8) -> escalation: Intensify the situation
  - Failure spike (>0.6) -> intervention: Assist or punish
  - High divergence (>0.75) -> chaos: Introduce unpredictability
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .emergence_adapter import EmergenceAdapter
from .event_engine import EventEngine


# ============================================================
# Director — main loop orchestrator
# ============================================================

class Director:
    """Main Director that observes and injects events into the world.

    The Director is the intelligence layer above individual NPCs.
    It watches the system as a whole and decides when to intervene
    to maintain narrative momentum and engagement.

    This implements the Director Loop from the design spec:
        OBSERVE -> ANALYZE -> DECIDE -> INJECT EVENT

    Attributes:
        emergence_tracker: Adapter that converts game state to signals.
        event_engine: Engine that creates and applies events.
        history: List of all events injected by the Director.
        cooldowns: Dict tracking cooldowns per intervention type.
        cooldown_ticks: Dict of max cooldown values per type.
        narrative_threads: Dict tracking ongoing narrative arcs from events.
        tick_count: Number of ticks the Director has processed.
        thresholds: Dict of signal thresholds for intervention.
    """

    # Default thresholds for intervention decisions
    DEFAULT_THRESHOLDS = {
        "stagnation": 0.7,
        "conflict": 0.8,
        "failure_spike": 0.6,
        "divergence": 0.75,
    }

    # Default cooldown ticks between same-type interventions
    DEFAULT_COOLDOWN_TICKS = {
        "twist": 3,
        "escalation": 2,
        "intervention": 4,
        "chaos": 3,
    }

    # Map signal type to intervention event type
    SIGNAL_TO_EVENT = {
        "stagnation": "twist",
        "conflict": "escalation",
        "failure_spike": "intervention",
        "divergence": "chaos",
    }

    def __init__(
        self,
        emergence_tracker: Optional[EmergenceAdapter] = None,
        event_engine: Optional[EventEngine] = None,
        thresholds: Optional[Dict[str, float]] = None,
        cooldowns: Optional[Dict[str, int]] = None,
        enable_cooldowns: bool = True,
    ):
        """Initialize Director.

        Args:
            emergence_tracker: Adapter for converting game state to signals.
                If None, a default EmergenceAdapter is created.
            event_engine: Engine for creating and applying events.
                If None, a default EventEngine is created.
            thresholds: Signal thresholds for intervention.
                If None, DEFAULT_THRESHOLDS is used.
            cooldowns: Max cooldown ticks per intervention type.
                If None, DEFAULT_COOLDOWN_TICKS is used.
            enable_cooldowns: If False, cooldowns are disabled.
        """
        self.emergence_tracker = emergence_tracker or EmergenceAdapter()
        self.event_engine = event_engine or EventEngine()
        self.history: List[Dict[str, Any]] = []
        # Cooldowns start at 0 (ready to fire), set to max after event fires
        self.cooldowns: Dict[str, int] = {
            "twist": 0, "escalation": 0,
            "intervention": 0, "chaos": 0,
        }
        self.cooldown_ticks: Dict[str, int] = dict(
            cooldowns or self.DEFAULT_COOLDOWN_TICKS
        )
        self.narrative_threads: Dict[str, Dict[str, Any]] = {}
        self.tick_count = 0
        self.thresholds = thresholds or dict(self.DEFAULT_THRESHOLDS)
        self.enable_cooldowns = enable_cooldowns

    def tick(
        self,
        world_state: Dict[str, Any],
        npcs: List[Any],
        recent_outcomes: List[Any],
    ) -> Optional[Dict[str, Any]]:
        """Process one game tick — the Director's main loop.

        This method should be called once per game tick AFTER all NPCs act.
        It performs the full Director Loop:
            OBSERVE (signals) -> ANALYZE (thresholds) ->
            DECIDE (intervention) -> INJECT EVENT

        Args:
            world_state: Current world state dictionary.
            npcs: List of NPC objects.
            recent_outcomes: List of recent action outcome objects.

        Returns:
            Event dict if an intervention occurred, None otherwise.
        """
        self.tick_count += 1

        # Step 1: OBSERVE — Analyze signals from the system
        signals = self.emergence_tracker.analyze(
            world_state, npcs, recent_outcomes
        )

        # Step 2: DECIDE — Determine if intervention is needed
        decision = self._decide_intervention(signals)

        # Step 3: INJECT — Create and apply event if decided
        event = None
        if decision:
            event = self.event_engine.create_event(decision, world_state, npcs)
            if event:
                self.event_engine.apply_event(event, world_state)
                self.history.append(event)

                # Track narrative threads
                self._update_narrative_threads(event)

                # Apply cooldown after event fires
                event_type = event.get("event_type", "chaos")
                self._apply_cooldown(event_type)

        # Step 4: Tick down cooldowns
        self._tick_cooldowns()

        return event

    def _decide_intervention(
        self, signals: Dict[str, float]
    ) -> Optional[Dict[str, Any]]:
        """Decide whether to intervene based on signal analysis.

        Checks each signal against its threshold in priority order:
            1. Stagnation -> twist (highest priority for narrative momentum)
            2. Conflict -> escalation
            3. Failure -> intervention (assistance/punishment)
            4. Divergence -> chaos

        Args:
            signals: Dict of signal names to 0-1 values.

        Returns:
            Decision dict with 'type' and 'intensity', or None.
        """
        checks = [
            ("stagnation", lambda v: v > self.thresholds.get("stagnation", 0.7)),
            ("conflict", lambda v: v > self.thresholds.get("conflict", 0.8)),
            ("failure_spike", lambda v: v > self.thresholds.get("failure_spike", 0.6)),
            ("divergence", lambda v: v > self.thresholds.get("divergence", 0.75)),
        ]

        for signal_name, check_func in checks:
            value = signals.get(signal_name, 0.0)
            if check_func(value):
                event_type = self.SIGNAL_TO_EVENT.get(signal_name)
                if not event_type:
                    continue

                # Check cooldown
                if self.enable_cooldowns and self.cooldowns.get(event_type, 0) > 0:
                    continue

                # Calculate intensity from signal value
                threshold = self.thresholds.get(signal_name, 0.5)
                intensity = min(1.0, value / max(threshold, 0.001))

                return {
                    "type": event_type,
                    "intensity": round(intensity, 3),
                    "signal": signal_name,
                    "signal_value": round(value, 3),
                }

        return None

    def _update_narrative_threads(self, event: Dict[str, Any]) -> None:
        """Update narrative threads based on injected event.

        Narrative threads allow events to accumulate into story arcs
        rather than being isolated incidents.

        Args:
            event: The event that was just applied.
        """
        event_name = event.get("name", "")
        event_type = event.get("event_type", "")
        tags = event.get("tags", [])

        # Determine thread from event tags
        thread_type = None
        for tag in tags:
            if tag in ("betrayal", "alliance", "combat", "environment"):
                thread_type = f"{tag}_arc"
                break

        if not thread_type:
            thread_type = f"{event_type}_arc"

        if thread_type in self.narrative_threads:
            thread = self.narrative_threads[thread_type]
            thread["stage"] += 1
            thread["last_event"] = event_name
            thread["events"].append(event_name)
        else:
            self.narrative_threads[thread_type] = {
                "stage": 1,
                "type": thread_type,
                "first_event": event_name,
                "last_event": event_name,
                "events": [event_name],
            }

    def _apply_cooldown(self, event_type: str) -> None:
        """Apply cooldown after an event fires.

        Args:
            event_type: The event type that just fired.
        """
        self.cooldowns[event_type] = self.cooldown_ticks.get(event_type, 0)

    def _tick_cooldowns(self) -> None:
        """Decrement all cooldown counters by 1."""
        for key in list(self.cooldowns.keys()):
            if self.cooldowns[key] > 0:
                self.cooldowns[key] -= 1

    def _set_cooldown(self, event_type: str, ticks: int) -> None:
        """Set a cooldown for a specific event type.

        Args:
            event_type: The event type to cooldown.
            ticks: Number of ticks for cooldown.
        """
        self.cooldowns[event_type] = ticks
        self.cooldown_ticks[event_type] = ticks

    def get_status(self) -> Dict[str, Any]:
        """Get Director status for debugging/monitoring.

        Returns:
            Dict with director state: ticks processed, event history summary,
            active narrative threads, and current cooldowns.
        """
        return {
            "tick_count": self.tick_count,
            "events_injected": len(self.history),
            "event_summary": self.event_engine.get_event_summary(),
            "active_threads": {
                k: v for k, v in self.narrative_threads.items()
                if v["stage"] > 0
            },
            "cooldowns": dict(self.cooldowns),
        }

    def reset(self) -> None:
        """Reset Director state for new game/session."""
        self.history.clear()
        self.narrative_threads.clear()
        self.tick_count = 0
        # Reset cooldowns to 0 (ready to fire)
        for key in self.cooldowns:
            self.cooldowns[key] = 0
        self.event_engine.reset()