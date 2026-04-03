# Director System Enhancements — Code Review Document

**Date:** 2026-04-02 12:26  
**Type:** System Enhancement Proposal  
**Status:** Draft for Review  

---

## Overview

This document outlines four critical enhancements to the Director system, transforming it from a purely reactive threshold-based system into a strategic, causality-aware, pattern-learning narrative intelligence.

### Current State
```
Director Loop: OBSERVE -> ANALYZE -> DECIDE -> INJECT EVENT
- Reactive only (signal thresholds trigger events)
- No long-term goals or intent
- Events lack causal grounding
- NPCs unaware of world events
- No pattern recognition across time
```

### Target State
```
Director Loop: OBSERVE -> GALS -> ANALYZE -> DECIDE -> INJECT -> PROPAGATE
- Goal-driven with strategic intent
- Causality-aware event generation
- NPC memory propagation from events
- Pattern detection for adaptive behavior
```

---

## GAP 1 — Director is Reactive, Not Strategic

### Problem
The Director responds purely to signal thresholds with no long-term intent. This creates a system that feels like a slot machine of events rather than a purposeful narrative force.

### Solution
Introduce a goal system that gives the Director persistent objectives that evolve over time.

### File Changes

#### ➕ NEW FILE: `src/app/rpg/director/goals.py`

```python
# src/app/rpg/director/goals.py
"""Director Goals — Strategic objectives that evolve over time.

Gives the Director long-term intent rather than purely reactive behavior.
Goals accumulate progress based on signal patterns and influence decisions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class DirectorGoal:
    """A strategic objective that the Director pursues over time.

    Goals track progress toward narrative objectives like "increase tension"
    or "create betrayal arc". They update based on signals and influence
    the Director's intervention decisions.

    Attributes:
        goal_type: The type of goal (e.g., "increase_tension").
        progress: Current progress toward completion (0.0 to target_value).
        target_value: Value at which goal is considered complete.
        active: Whether this goal is currently being pursued.
    """

    def __init__(self, goal_type: str, target_value: float = 1.0):
        """Initialize a Director goal.

        Args:
            goal_type: String identifier for the goal type.
            target_value: Progress value at which goal completes.
        """
        self.goal_type = goal_type
        self.progress = 0.0
        self.target_value = target_value
        self.active = True

    def update(self, signals: Dict[str, float]) -> None:
        """Update goal progress based on current signals.

        Each goal type responds to different signals:
        - increase_tension: Responds to conflict signals
        - create_betrayal_arc: Responds to stagnation signals

        Args:
            signals: Dict of signal names to 0-1 values.
        """
        if self.goal_type == "increase_tension":
            # Tension builds from conflict
            self.progress += signals.get("conflict", 0) * 0.1

        elif self.goal_type == "create_betrayal_arc":
            # Betrayal arcs emerge from stagnation
            self.progress += signals.get("stagnation", 0) * 0.05

        # Clamp progress to valid range
        self.progress = max(0.0, min(self.progress, self.target_value))

    def is_complete(self) -> bool:
        """Check if the goal has been achieved.

        Returns:
            True if progress has reached target value.
        """
        return self.progress >= self.target_value

    def get_progress_ratio(self) -> float:
        """Get progress as a 0-1 ratio.

        Returns:
            Progress divided by target value.
        """
        if self.target_value == 0:
            return 0.0
        return self.progress / self.target_value

    def reset(self) -> None:
        """Reset goal progress to zero."""
        self.progress = 0.0
        self.active = True

    def __repr__(self) -> str:
        return (
            f"DirectorGoal(type='{self.goal_type}', "
            f"progress={self.progress:.2f}, "
            f"complete={self.is_complete()})"
        )
```

#### 🔧 MODIFY: `src/app/rpg/director/director.py`

**Change 1: Add imports and goal initialization**

```diff
------- SEARCH
from .emergence_adapter import EmergenceAdapter
from .event_engine import EventEngine
=======
from .emergence_adapter import EmergenceAdapter
from .event_engine import EventEngine
from .goals import DirectorGoal
+++++++ REPLACE
```

```diff
------- SEARCH
        self.emergence_tracker = emergence_tracker or EmergenceAdapter()
        self.event_engine = event_engine or EventEngine()
        self.history: List[Dict[str, Any]] = []
        # Cooldowns start at 0 (ready to fire), set to max after event fires
        self.cooldowns: Dict[str, int] = {
            "twist": 0, "escalation": 0,
            "intervention": 0, "chaos": 0,
        }
=======
        self.emergence_tracker = emergence_tracker or EmergenceAdapter()
        self.event_engine = event_engine or EventEngine()
        self.history: List[Dict[str, Any]] = []
        # Strategic goals that persist across ticks
        self.active_goals: List[DirectorGoal] = [
            DirectorGoal("increase_tension"),
            DirectorGoal("create_betrayal_arc"),
        ]
        # Cooldowns start at 0 (ready to fire), set to max after event fires
        self.cooldowns: Dict[str, int] = {
            "twist": 0, "escalation": 0,
            "intervention": 0, "chaos": 0,
        }
+++++++ REPLACE
```

**Change 2: Update tick method to update goals**

```diff
------- SEARCH
        # Step 2: DECIDE — Determine if intervention is needed
        decision = self._decide_intervention(signals)
=======
        # Step 1.5: Update strategic goals
        for goal in self.active_goals:
            goal.update(signals)

        # Step 2: DECIDE — Determine if intervention is needed
        decision = self._decide_intervention(signals, self.active_goals)
+++++++ REPLACE
```

**Change 3: Update method signature and add goal influence**

```diff
------- SEARCH
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
=======
    def _decide_intervention(
        self, signals: Dict[str, float], goals: Optional[List[DirectorGoal]] = None
    ) -> Optional[Dict[str, Any]]:
        """Decide whether to intervene based on signal analysis and goals.

        Checks each signal against its threshold in priority order:
            1. Stagnation -> twist (highest priority for narrative momentum)
            2. Conflict -> escalation
            3. Failure -> intervention (assistance/punishment)
            4. Divergence -> chaos

        Goal influence:
        - Active goals can override signal-driven decisions when progress is high

        Args:
            signals: Dict of signal names to 0-1 values.
            goals: Optional list of active DirectorGoal instances.

        Returns:
            Decision dict with 'type' and 'intensity', or None.
        """
        # Check goals first — they represent long-term intent
        if goals:
            for goal in goals:
                if not goal.active:
                    continue

                progress_ratio = goal.get_progress_ratio()

                if goal.goal_type == "increase_tension" and progress_ratio > 0.6:
                    return {
                        "type": "escalation",
                        "intensity": 0.5 + (progress_ratio * 0.5),
                        "signal": "goal_driven",
                        "goal": "increase_tension",
                        "goal_progress": round(progress_ratio, 3),
                    }

                if goal.goal_type == "create_betrayal_arc" and progress_ratio > 0.5:
                    return {
                        "type": "twist",
                        "subtype": "betrayal",
                        "intensity": 0.5 + (progress_ratio * 0.5),
                        "signal": "goal_driven",
                        "goal": "create_betrayal_arc",
                        "goal_progress": round(progress_ratio, 3),
                    }

        # Fall back to signal-driven decisions
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
+++++++ REPLACE
```

**Change 4: Add method to manage goals**

```diff
------- SEARCH
    def reset(self) -> None:
        """Reset Director state for new game/session."""
        self.history.clear()
        self.narrative_threads.clear()
        self.tick_count = 0
        # Reset cooldowns to 0 (ready to fire)
        for key in self.cooldowns:
            self.cooldowns[key] = 0
        self.event_engine.reset()
=======
    def reset(self) -> None:
        """Reset Director state for new game/session."""
        self.history.clear()
        self.narrative_threads.clear()
        self.tick_count = 0
        # Reset cooldowns to 0 (ready to fire)
        for key in self.cooldowns:
            self.cooldowns[key] = 0
        # Reset goals
        for goal in self.active_goals:
            goal.reset()
        self.event_engine.reset()

    def add_goal(self, goal: DirectorGoal) -> None:
        """Add a new strategic goal to the Director.

        Args:
            goal: DirectorGoal instance to track.
        """
        self.active_goals.append(goal)

    def remove_goal(self, goal_type: str) -> None:
        """Remove a goal by type.

        Args:
            goal_type: String identifier of the goal to remove.
        """
        self.active_goals = [
            g for g in self.active_goals if g.goal_type != goal_type
        ]
+++++++ REPLACE
```

---

## GAP 2 — Events Lack Causality

### Problem
Events appear out of nowhere. When the Director injects a "supply_drop", NPCs and players have no causal context for why it happened. Events feel "injected" rather than "earned".

### Solution
Add a causality engine that tracks the chain of events leading to Director decisions.

### File Changes

#### ➕ NEW FILE: `src/app/rpg/director/causality_engine.py`

```python
# src/app/rpg/director/causality_engine.py
"""Causality Engine — Tracks cause-effect relationships in narrative events.

Makes events feel earned rather than injected by maintaining a chain
of causality between outcomes and Director interventions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class CausalityEngine:
    """Extracts causal relationships from game events.

    Analyzes NPC actions and their outcomes to determine what
    caused the need for Director intervention.

    Attributes:
        history: List of extracted causal chains.
        max_history: Maximum number of causal chains to retain.
    """

    def __init__(self, max_history: int = 20):
        """Initialize causality engine.

        Args:
            max_history: Maximum causal chains to retain.
        """
        self.history: List[Dict[str, Any]] = []
        self.max_history = max_history

    def extract_cause(
        self,
        npcs: List[Any],
        outcomes: List[Any],
    ) -> Optional[Dict[str, Any]]:
        """Extract causal chain from recent outcomes.

        Looks for patterns like:
        - failure_chain: Multiple consecutive failures
        - escalation_pattern: Increasing severity of conflicts
        - stagnation_pattern: Repeated same-type actions

        Args:
            npcs: List of NPC entities.
            outcomes: List of recent action outcome objects.

        Returns:
            Causal chain dict with 'type', 'count', and optional 'source_npc',
            or None if no significant pattern found.
        """
        if not outcomes:
            return None

        # Check for failure chain
        failures = [o for o in outcomes if not getattr(o, "success", True)]

        if len(failures) >= 2:
            cause = {
                "type": "failure_chain",
                "count": len(failures),
                "recent_failures": [
                    {
                        "action": getattr(o, "action", "unknown"),
                        "actor": getattr(o, "actor", "unknown"),
                    }
                    for o in failures[-3:]
                ],
            }
            self._record_cause(cause)
            return cause

        # Check for escalation pattern
        if len(outcomes) >= 3:
            severities = [getattr(o, "severity", 0) for o in outcomes]
            if all(severities[i] >= severities[i - 1] for i in range(1, len(severities))):
                cause = {
                    "type": "escalation_pattern",
                    "count": len(outcomes),
                    "max_severity": max(severities),
                }
                self._record_cause(cause)
                return cause

        return None

    def _record_cause(self, cause: Dict[str, Any]) -> None:
        """Record a causal chain in history.

        Args:
            cause: Causal chain dict to record.
        """
        self.history.append(cause)
        # Trim history
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_causal_summary(self) -> Dict[str, Any]:
        """Get summary of recent causal chains.

        Returns:
            Dict with counts by cause type and recent chains.
        """
        type_counts: Dict[str, int] = {}
        for chain in self.history:
            ctype = chain.get("type", "unknown")
            type_counts[ctype] = type_counts.get(ctype, 0) + 1

        return {
            "total_chains": len(self.history),
            "by_type": type_counts,
            "recent": self.history[-5:],
        }

    def reset(self) -> None:
        """Clear causal history."""
        self.history.clear()
```

#### 🔧 MODIFY: `src/app/rpg/director/director.py`

**Change 1: Add causality engine import**

```diff
------- SEARCH
from .emergence_adapter import EmergenceAdapter
from .event_engine import EventEngine
from .goals import DirectorGoal
=======
from .emergence_adapter import EmergenceAdapter
from .event_engine import EventEngine
from .goals import DirectorGoal
from .causality_engine import CausalityEngine
+++++++ REPLACE
```

**Change 2: Initialize causality engine**

```diff
------- SEARCH
        self.event_engine = event_engine or EventEngine()
        self.history: List[Dict[str, Any]] = []
        # Strategic goals that persist across ticks
        self.active_goals: List[DirectorGoal] = [
=======
        self.event_engine = event_engine or EventEngine()
        self.causality_engine = CausalityEngine()
        self.history: List[Dict[str, Any]] = []
        # Strategic goals that persist across ticks
        self.active_goals: List[DirectorGoal] = [
+++++++ REPLACE
```

**Change 3: Inject causality into decisions**

```diff
------- SEARCH
        # Step 1: OBSERVE — Analyze signals from the system
        signals = self.emergence_tracker.analyze(
            world_state, npcs, recent_outcomes
        )
=======
        # Step 1: OBSERVE — Analyze signals from the system
        signals = self.emergence_tracker.analyze(
            world_state, npcs, recent_outcomes
        )

        # Step 1.25: Extract causal chain from outcomes
        cause = self.causality_engine.extract_cause(npcs, recent_outcomes)
+++++++ REPLACE
```

**Change 4: Pass causality through decision**

```diff
------- SEARCH
        # Check goals first — they represent long-term intent
        if goals:
            for goal in goals:
                if not goal.active:
                    continue

                progress_ratio = goal.get_progress_ratio()

                if goal.goal_type == "increase_tension" and progress_ratio > 0.6:
                    return {
                        "type": "escalation",
                        "intensity": 0.5 + (progress_ratio * 0.5),
                        "signal": "goal_driven",
                        "goal": "increase_tension",
                        "goal_progress": round(progress_ratio, 3),
                    }

                if goal.goal_type == "create_betrayal_arc" and progress_ratio > 0.5:
                    return {
                        "type": "twist",
                        "subtype": "betrayal",
                        "intensity": 0.5 + (progress_ratio * 0.5),
                        "signal": "goal_driven",
                        "goal": "create_betrayal_arc",
                        "goal_progress": round(progress_ratio, 3),
                    }
=======
        # Check goals first — they represent long-term intent
        if goals:
            for goal in goals:
                if not goal.active:
                    continue

                progress_ratio = goal.get_progress_ratio()

                if goal.goal_type == "increase_tension" and progress_ratio > 0.6:
                    result = {
                        "type": "escalation",
                        "intensity": 0.5 + (progress_ratio * 0.5),
                        "signal": "goal_driven",
                        "goal": "increase_tension",
                        "goal_progress": round(progress_ratio, 3),
                    }
                    return result

                if goal.goal_type == "create_betrayal_arc" and progress_ratio > 0.5:
                    result = {
                        "type": "twist",
                        "subtype": "betrayal",
                        "intensity": 0.5 + (progress_ratio * 0.5),
                        "signal": "goal_driven",
                        "goal": "create_betrayal_arc",
                        "goal_progress": round(progress_ratio, 3),
                    }
                    if cause:
                        result["cause"] = cause
                    return result
+++++++ REPLACE
```

```diff
------- SEARCH
                # Calculate intensity from signal value
                threshold = self.thresholds.get(signal_name, 0.5)
                intensity = min(1.0, value / max(threshold, 0.001))

                return {
                    "type": event_type,
                    "intensity": round(intensity, 3),
                    "signal": signal_name,
                    "signal_value": round(value, 3),
                }
=======
                # Calculate intensity from signal value
                threshold = self.thresholds.get(signal_name, 0.5)
                intensity = min(1.0, value / max(threshold, 0.001))

                result = {
                    "type": event_type,
                    "intensity": round(intensity, 3),
                    "signal": signal_name,
                    "signal_value": round(value, 3),
                }

                # Inject causality for failure interventions
                if signal_name == "failure_spike" and cause:
                    result["cause"] = cause

                return result
+++++++ REPLACE
```

#### 🔧 MODIFY: `src/app/rpg/director/event_engine.py`

**Change: Include causality information in events**

```diff
------- SEARCH
        event_type = decision.get("type", "chaos")
        intensity = decision.get("intensity", 0.5)
        target_npc = decision.get("target_npc")
=======
        event_type = decision.get("type", "chaos")
        intensity = decision.get("intensity", 0.5)
        target_npc = decision.get("target_npc")
        cause = decision.get("cause")
+++++++ REPLACE
```

```diff
------- SEARCH
        event = random.choice(available).copy()
        event["event_type"] = event_type
        event["intensity"] = intensity
        event["tick_applied"] = len(self.history)
=======
        event = random.choice(available).copy()
        event["event_type"] = event_type
        event["intensity"] = intensity
        event["tick_applied"] = len(self.history)

        # Attach causal context if present
        if cause:
            event["causality"] = cause
+++++++ REPLACE
```

---

## GAP 3 — NPCs Are Not Aware of Events

### Problem
When the Director injects an event (e.g., supply_drop), NPCs have no memory of it. Their behavior doesn't change, and they can't reference the event in future decisions.

### Solution
Add an event propagator that records events into NPC memory, making the world feel reactive.

### File Changes

#### ➕ NEW FILE: `src/app/rpg/director/event_propagator.py`

```python
# src/app/rpg/director/event_propagator.py
"""Event Propagator — Distributes Director events to NPC memory.

Ensures NPCs are aware of world events and can react to them,
creating a living world where events ripple through NPC behavior.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class EventPropagator:
    """Propagates Director events to NPC memory systems.

    After the Director injects an event, the propagator ensures
    all relevant NPCs record the event in their memory with
    appropriate salience and context.

    Attributes:
        propagation_radius: Number of NPCs to affect (None = all).
        salience_boost: Additional salience for Director events.
    """

    def __init__(
        self,
        propagation_radius: Optional[int] = None,
        salience_boost: float = 0.3,
    ):
        """Initialize event propagator.

        Args:
            propagation_radius: Max NPCs to affect (None = all).
            salience_boost: Extra salience for Director events.
        """
        self.propagation_radius = propagation_radius
        self.salience_boost = salience_boost

    def propagate(
        self,
        event: Dict[str, Any],
        npcs: List[Any],
        target_only: bool = False,
    ) -> int:
        """Propagate an event to NPC memories.

        Args:
            event: Event dict from Director.
            npcs: List of NPC entities.
            target_only: Only propagate to targeted NPC.

        Returns:
            Number of NPCs that received the event.
        """
        if not event:
            return 0

        # Determine which NPCs to affect
        affected_npcs = self._get_affected_npcs(event, npcs, target_only)

        memory_event = {
            "type": "world_event",
            "name": event.get("name", "unknown"),
            "event_type": event.get("event_type", "unknown"),
            "description": event.get("description", ""),
            "intensity": event.get("intensity", 0.5),
            "causality": event.get("causality"),
            "salience": 0.8 + self.salience_boost,  # High salience for Director events
        }

        count = 0
        for npc in affected_npcs:
            if hasattr(npc, "memory") and npc.memory:
                npc.memory.remember(memory_event)
                count += 1
            elif hasattr(npc, "remember_event"):
                npc.remember_event(memory_event)
                count += 1

        return count

    def _get_affected_npcs(
        self,
        event: Dict[str, Any],
        npcs: List[Any],
        target_only: bool,
    ) -> List[Any]:
        """Determine which NPCs should receive the event.

        Args:
            event: Event dict.
            npcs: All NPCs.
            target_only: Target only specific NPC.

        Returns:
            List of NPCs to propagate to.
        """
        if target_only or event.get("targeted"):
            target_id = event.get("target")
            if target_id:
                return [npc for npc in npcs if getattr(npc, "id", None) == target_id]
            return []

        # Propagate to all (or limited by radius)
        if self.propagation_radius is not None:
            return npcs[: self.propagation_radius]
        return npcs

    def reset(self) -> None:
        """Reset propagator state."""
        pass  # Stateless component
```

#### 🔧 MODIFY: `src/app/rpg/director/director.py`

**Change 1: Add propagator import**

```diff
------- SEARCH
from .emergence_adapter import EmergenceAdapter
from .event_engine import EventEngine
from .goals import DirectorGoal
from .causality_engine import CausalityEngine
=======
from .emergence_adapter import EmergenceAdapter
from .event_engine import EventEngine
from .goals import DirectorGoal
from .causality_engine import CausalityEngine
from .event_propagator import EventPropagator
+++++++ REPLACE
```

**Change 2: Initialize propagator**

```diff
------- SEARCH
        self.causality_engine = CausalityEngine()
        self.history: List[Dict[str, Any]] = []
=======
        self.causality_engine = CausalityEngine()
        self.propagator = EventPropagator()
        self.history: List[Dict[str, Any]] = []
+++++++ REPLACE
```

**Change 3: Propagate events after applying**

```diff
------- SEARCH
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
=======
        # Step 3: INJECT — Create and apply event if decided
        event = None
        if decision:
            event = self.event_engine.create_event(decision, world_state, npcs)
            if event:
                self.event_engine.apply_event(event, world_state)
                self.history.append(event)

                # Track narrative threads
                self._update_narrative_threads(event)

                # Propagate event to NPC memory
                self.propagator.propagate(event, npcs)

                # Apply cooldown after event fires
                event_type = event.get("event_type", "chaos")
                self._apply_cooldown(event_type)
+++++++ REPLACE
```

#### 🔧 MODIFY: `src/app/rpg/ai/llm_mind/npc_mind.py`

**Change: Include recent events in LLM evaluation context**

```diff
------- SEARCH
        context = build_context(
            npc={"name": self.npc_name, "role": self.npc_role},
            personality=self.personality,
            memory=self.memory.summarize(),
            goals=[g.to_dict() for g in self.goals.active_goals],
            world={
                "visible_entities": visible_entities,
                "location": world.get("location", "unknown"),
            },
            recent_events=self.memory.get_raw_events(limit=5),
            intent_priority=intent_priority,
        )
=======
        # Include Director events in context
        recent_world_events = self.memory.get_recent_events(limit=5)

        context = build_context(
            npc={"name": self.npc_name, "role": self.npc_role},
            personality=self.personality,
            memory=self.memory.summarize(),
            goals=[g.to_dict() for g in self.goals.active_goals],
            world={
                "visible_entities": visible_entities,
                "location": world.get("location", "unknown"),
            },
            recent_events=self.memory.get_raw_events(limit=5),
            world_events=recent_world_events,
            intent_priority=intent_priority,
        )
+++++++ REPLACE
```

---

## GAP 4 — No Pattern Learning in Director

### Problem
The Director doesn't learn from repeated patterns. NPCs could fail the action 20 times in a row and the Director would respond identically each time, rather than adapting its approach.

### Solution
Add a pattern detector that identifies recurring behavior patterns and reports them to the Director for adaptive responses.

### File Changes

#### ➕ NEW FILE: `src/app/rpg/director/pattern_detector.py`

```python
# src/app/rpg/director/pattern_detector.py
"""Pattern Detector — Identifies recurring behavior patterns across time.

Enables the Director to adapt its interventions based on historical patterns
rather than treating each event in isolation.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional


class PatternDetector:
    """Detects recurring patterns in NPC outcomes and world events.

    Analyzes historical data to identify patterns that should trigger
    different Director responses than the default threshold-based logic.

    Attributes:
        outcome_history: Recent outcomes tracked for pattern analysis.
        max_window: Maximum window size for pattern detection.
    """

    def __init__(self, max_window: int = 10):
        """Initialize pattern detector.

        Args:
            max_window: Maximum outcomes to track for patterns.
        """
        self.outcome_history: deque = deque(maxlen=max_window)
        self.max_window = max_window
        self.detected_patterns: List[Dict[str, Any]] = []

    def record_outcome(self, outcome: Any) -> None:
        """Record an outcome for pattern analysis.

        Args:
            outcome: Action outcome object.
        """
        self.outcome_history.append({
            "success": getattr(outcome, "success", True),
            "action": getattr(outcome, "action", "unknown"),
            "actor": getattr(outcome, "actor", "unknown"),
            "severity": getattr(outcome, "severity", 0),
        })

    def detect_failure_pattern(
        self, outcomes: Optional[List[Any]] = None, window: int = 5
    ) -> bool:
        """Detect if there's a pattern of repeated failures.

        Args:
            outcomes: Recent outcomes to analyze. If None, uses history.
            window: Size of window to check.

        Returns:
            True if failure rate exceeds 70% in window.
        """
        recent = outcomes if outcomes is not None else list(self.outcome_history)
        recent = recent[-window:]

        if len(recent) < window:
            return False

        failures = sum(
            1 for o in recent if not getattr(o, "success", True)
            if isinstance(o, object) else not o.get("success", True)
        )

        failure_rate = failures / window
        return failure_rate > 0.7

    def detect_stagnation_pattern(
        self, outcomes: Optional[List[Any]] = None, window: int = 5
    ) -> Optional[Dict[str, Any]]:
        """Detect if NPCs are repeating the same action type.

        Args:
            outcomes: Recent outcomes. If None, uses history.
            window: Size of window to check.

        Returns:
            Pattern dict if stagnation detected, None otherwise.
        """
        recent = outcomes if outcomes is not None else list(self.outcome_history)
        recent = recent[-window:]

        if len(recent) < window:
            return None

        action_counts: Dict[str, int] = {}
        for o in recent:
            action = (
                getattr(o, "action", "unknown")
                if isinstance(o, object)
                else o.get("action", "unknown")
            )
            action_counts[action] = action_counts.get(action, 0) + 1

        # Check if single action dominates
        for action, count in action_counts.items():
            if count / window > 0.8:
                pattern = {
                    "type": "stagnation",
                    "dominant_action": action,
                    "frequency": count / window,
                }
                self.detected_patterns.append(pattern)
                return pattern

        return None

    def detect_escalation_pattern(
        self, outcomes: Optional[List[Any]] = None, window: int = 5
    ) -> Optional[Dict[str, Any]]:
        """Detect if outcome severity is consistently increasing.

        Args:
            outcomes: Recent outcomes. If None, uses history.
            window: Size of window to check.

        Returns:
            Pattern dict if escalation detected, None otherwise.
        """
        recent = outcomes if outcomes is not None else list(self.outcome_history)
        recent = recent[-window:]

        if len(recent) < 3:
            return None

        severities = [
            getattr(o, "severity", 0) if isinstance(o, object) else o.get("severity", 0)
            for o in recent
        ]

        # Check if trend is increasing
        increases = sum(
            1 for i in range(1, len(severities)) if severities[i] > severities[i - 1]
        )

        if increases >= len(severities) - 1:
            pattern = {
                "type": "escalation",
                "severity_range": [min(severities), max(severities)],
                "trend": "increasing",
            }
            self.detected_patterns.append(pattern)
            return pattern

        return None

    def analyze(
        self, outcomes: Optional[List[Any]] = None
    ) -> List[Dict[str, Any]]:
        """Run all pattern detectors and return findings.

        Args:
            outcomes: Recent outcomes. If None, uses history.

        Returns:
            List of detected pattern dicts.
        """
        patterns = []

        if self.detect_failure_pattern(outcomes):
            patterns.append({
                "type": "failure_cluster",
                "response": "adaptive_intervention",
            })

        stagnation = self.detect_stagnation_pattern(outcomes)
        if stagnation:
            patterns.append({
                "type": "action_stagnation",
                "response": "diversify_events",
                "detail": stagnation,
            })

        escalation = self.detect_escalation_pattern(outcomes)
        if escalation:
            patterns.append({
                "type": "conflict_escalation",
                "response": "de_escalation",
                "detail": escalation,
            })

        return patterns

    def reset(self) -> None:
        """Clear pattern history."""
        self.outcome_history.clear()
        self.detected_patterns.clear()
```

#### 🔧 MODIFY: `src/app/rpg/director/director.py`

**Change 1: Add pattern detector import**

```diff
------- SEARCH
from .emergence_adapter import EmergenceAdapter
from .event_engine import EventEngine
from .goals import DirectorGoal
from .causality_engine import CausalityEngine
from .event_propagator import EventPropagator
=======
from .emergence_adapter import EmergenceAdapter
from .event_engine import EventEngine
from .goals import DirectorGoal
from .causality_engine import CausalityEngine
from .event_propagator import EventPropagator
from .pattern_detector import PatternDetector
+++++++ REPLACE
```

**Change 2: Initialize pattern detector**

```diff
------- SEARCH
        self.causality_engine = CausalityEngine()
        self.propagator = EventPropagator()
        self.history: List[Dict[str, Any]] = []
=======
        self.causality_engine = CausalityEngine()
        self.propagator = EventPropagator()
        self.pattern_detector = PatternDetector()
        self.history: List[Dict[str, Any]] = []
+++++++ REPLACE
```

**Change 3: Record outcomes for pattern analysis**

```diff
------- SEARCH
        # Step 1.25: Extract causal chain from outcomes
        cause = self.causality_engine.extract_cause(npcs, recent_outcomes)
=======
        # Step 1.25: Extract causal chain from outcomes
        cause = self.causality_engine.extract_cause(npcs, recent_outcomes)

        # Step 1.5: Record outcomes for pattern analysis
        for outcome in recent_outcomes:
            self.pattern_detector.record_outcome(outcome)
+++++++ REPLACE
```

**Change 4: Use pattern detection in decisions**

```diff
------- SEARCH
        # Fall back to signal-driven decisions
        checks = [
=======
        # Check for adaptive patterns
        patterns = self.pattern_detector.analyze()
        for pattern in patterns:
            if pattern["type"] == "failure_cluster":
                return {
                    "type": "intervention",
                    "mode": "adaptive",
                    "reason": "repeated_failures",
                    "intensity": 0.8,
                    "signal": "pattern_driven",
                }

            if pattern["type"] == "action_stagnation":
                return {
                    "type": "twist",
                    "mode": "diversify",
                    "reason": pattern.get("detail", {}).get("dominant_action", "unknown"),
                    "intensity": 0.7,
                    "signal": "pattern_driven",
                }

        # Fall back to signal-driven decisions
        checks = [
+++++++ REPLACE
```

---

## OPTIONAL ENHANCEMENT — Director State Tracking

### Purpose
Provides a persistent state object for the Director that tracks long-term metrics like tension and stability across the entire game session.

### File Changes

#### ➕ NEW FILE: `src/app/rpg/director/director_state.py` (Optional)

```python
# src/app/rpg/director/director_state.py
"""Director State — Persistent state tracking for long-term metrics.

Maintains running aggregates of world state that influence Director decisions
beyond what instant signals can provide.
"""

from __future__ import annotations

from typing import Any, Dict


class DirectorState:
    """Persistent state tracking for the Director.

    Tracks long-term metrics that should influence Director decisions
    beyond what instant signals can provide.

    Attributes:
        tension: Accumulated narrative tension (0.0 to 1.0).
        stability: World stability level (0.0 to 1.0).
        chaos_factor: Unpredictability multiplier (0.0 to 1.0).
        narrative_momentum: How much story momentum exists (0.0 to 1.0).
    """

    def __init__(self):
        """Initialize director state with defaults."""
        self.tension = 0.0
        self.stability = 1.0
        self.chaos_factor = 0.0
        self.narrative_momentum = 0.0

    def update(self, signals: Dict[str, float]) -> None:
        """Update state based on current signals.

        Args:
            signals: Dict of signal names to 0-1 values.
        """
        # Tension builds from conflict, decays slowly
        self.tension += signals.get("conflict", 0) * 0.1
        self.tension -= 0.02  # Natural decay
        self.tension = max(0.0, min(1.0, self.tension))

        # Stability decreases from divergence, increases from coherence
        self.stability -= signals.get("divergence", 0) * 0.05
        self.stability += 0.01  # Natural recovery
        self.stability = max(0.0, min(1.0, self.stability))

        # Chaos factor from unpredictable signals
        self.chaos_factor += signals.get("divergence", 0) * 0.08
        self.chaos_factor -= 0.01
        self.chaos_factor = max(0.0, min(1.0, self.chaos_factor))

        # Narrative momentum from stagnation (need for change)
        self.narrative_momentum += signals.get("stagnation", 0) * 0.1
        self.narrative_momentum -= 0.015
        self.narrative_momentum = max(0.0, min(1.0, self.narrative_momentum))

    def get_summary(self) -> Dict[str, float]:
        """Get state summary.

        Returns:
            Dict of all state values.
        """
        return {
            "tension": round(self.tension, 3),
            "stability": round(self.stability, 3),
            "chaos_factor": round(self.chaos_factor, 3),
            "narrative_momentum": round(self.narrative_momentum, 3),
        }

    def is_critical(self) -> bool:
        """Check if state is at critical levels.

        Returns:
            True if any metric is at extreme.
        """
        return (
            self.tension > 0.85
            or self.stability < 0.15
            or self.chaos_factor > 0.85
            or self.narrative_momentum > 0.9
        )

    def reset(self) -> None:
        """Reset state to defaults."""
        self.tension = 0.0
        self.stability = 1.0
        self.chaos_factor = 0.0
        self.narrative_momentum = 0.0
```

---

## Final Directory Structure

After implementing these changes, the `director/` directory will contain:

```
src/app/rpg/director/
├── __init__.py
├── director.py              # Modified: Goals, causality, patterns, propagation
├── event_engine.py          # Modified: Causality in events
├── emergence_adapter.py     # Unchanged
├── goals.py                 # ✅ NEW: Strategic goal system
├── causality_engine.py      # ✅ NEW: Cause-effect tracking
├── event_propagator.py      # ✅ NEW: Event distribution to NPCs
├── pattern_detector.py      # ✅ NEW: Pattern recognition
└── director_state.py        # 🟡 OPTIONAL: Persistent state
```

---

## What This Unlocks

### Before vs After

| Dimension | Before | After |
|-----------|--------|-------|
| Decision Making | Reactive (signal thresholds only) | Goal-driven with strategic intent |
| Events | Feel injected/random | Causally grounded in gameplay |
| NPC Awareness | Events happen in vacuum | NPCs remember and react to events |
| Pattern Recognition | None | Detects failure chains, stagnation, escalation |
| Adaptivity | Same response every time | Adaptive interventions based on history |

### Integration with Existing Systems

These enhancements integrate cleanly with:

1. **NPC Mind** (`src/app/rpg/ai/llm_mind/npc_mind.py`): NPCs now receive world events in memory context
2. **Event Engine** (`src/app/rpg/director/event_engine.py`): Events carry causal context
3. **Emergence Adapter** (`src/app/rpg/director/emergence_adapter.py`): Signals now influence goal progress
4. **Narrative Systems**: Narrative threads now connect to actual causal chains

### Testing Strategy

Recommended tests to add:

1. **Goals**: Test that goals progress over multiple ticks and influence decisions
2. **Causality**: Test that failure chains are correctly extracted and propagated
3. **Propagation**: Test that NPCs receive events in memory after Director injects them
4. **Patterns**: Test pattern detection with synthetic outcome sequences
5. **Integration**: Test full Director loop with all components active

---

## Migration Notes

### Breaking Changes

- `Director._decide_intervention()` signature changed from `(self, signals)` to `(self, signals, goals=None)`
- Existing calls to `_decide_intervention` without goals parameter will still work due to default parameter
- Event dicts now include optional `"causality"` and `"causality"` keys

### Backward Compatibility

- All existing Director functionality preserved when new components are not initialized
- New imports are at bottom of existing import block
- Goal system is additive — Director works with or without active goals