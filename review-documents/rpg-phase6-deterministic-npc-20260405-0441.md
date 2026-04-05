# Phase 6 — Deterministic NPC Architecture Patch

**Date:** 2026-04-05 04:41 UTC  
**Branch:** `copilot/implement-omnix-rpg-design`  
**Status:** Implementation complete with all tests passing

---

## Summary

Phase 6 replaces the LLM-dependent `ai/llm_mind` module with a fully deterministic NPC architecture. Every NPC decision is now derived from structured state (memory, beliefs, goals) through pure functions — no LLM calls required for NPC behavior in the simulation loop.

### Architecture

```
Event → NPCMemory.remember() → BeliefModel.update_from_event()
     → GoalEngine.generate_goals() → GoalEngine.merge_goals()
     → NPCMind.decide() → NPCDecision (validated, serializable)
```

### Key Design Decisions

1. **Deterministic by construction** — All components use sorted outputs, stable IDs, and clamped values
2. **Serialization-first** — Every component has `to_dict()`/`from_dict()` for state persistence
3. **Backwards compatible** — Old module names (`memory.py`, `decision.py`, etc.) become thin wrappers
4. **Event-driven beliefs** — Trust/fear/respect/hostility evolve from observed events
5. **Priority-based goals** — Goals are generated from beliefs + simulation state, deduplicated by ID

---

## Files Changed (18 files, +1102/-1120 lines)

### New Files (5)
| File | Lines | Purpose |
|------|-------|---------|
| `npc_memory.py` | 124 | Salience-based NPC memory with trim/sort |
| `npc_decision.py` | 58 | Structured decision dataclass |
| `npc_prompt_builder.py` | 22 | LLM prompt builder placeholder |
| `npc_response_parser.py` | 10 | Response parser placeholder |
| `npc_decision_validator.py` | 54 | Intent/action validation |

### Replaced Files (4)
| File | Before | After | Purpose |
|------|--------|-------|---------|
| `belief_model.py` | 1 (stub) | 148 | Trust/fear/respect/hostility model |
| `goal_engine.py` | 270 (lifecycle) | 205 | Priority-based goal generation |
| `npc_mind.py` | 363 (LLM-driven) | 175 | Deterministic orchestrator |
| `__init__.py` | 1 (stub) | 19 | Phase 6 exports |

### Compatibility Wrappers (5)
| File | Purpose |
|------|---------|
| `memory.py` | Re-exports `NPCMemory` |
| `decision.py` | Re-exports `NPCDecision` |
| `prompt_builder.py` | Re-exports `NPCPromptBuilder` |
| `response_parser.py` | Re-exports `NPCResponseParser` |
| `validator.py` | Re-exports `NPCDecisionValidator` |

### Integration Patches (4)
| File | Changes |
|------|---------|
| `world_simulation.py` | +NPC mind helpers, NPC processing in simulation tick |
| `world_player_actions.py` | +`_infer_affected_npc_ids()`, enriched event metadata |
| `world_scene_generator.py` | +`_collect_scene_actors()`, scene NPC enrichment |
| `world_scene_narrator.py` | +`_attach_npc_mind_context()`, Phase 6 prompt guidance |

---

## Test Coverage

| Suite | Tests | File |
|-------|-------|------|
| **Unit** | 109 | `tests/unit/rpg/test_phase6_deterministic_npc.py` |
| **Functional** | 20 | `tests/functional/test_phase6_deterministic_npc_functional.py` |
| **Regression** | 17 | `tests/regression/test_phase6_deterministic_npc_regression.py` |
| **Total** | **146** | |

### Unit Test Classes
- `TestNPCMemory` (14 tests) — remember, trim, salience, round-trip
- `TestBeliefModel` (18 tests) — update, clamp, event-driven, round-trip
- `TestGoalEngine` (14 tests) — generate, merge, advance, dedup
- `TestNPCDecision` (6 tests) — create, fallback, round-trip
- `TestNPCDecisionValidator` (7 tests) — validation, normalization
- `TestNPCPromptBuilder` (2 tests) — prompt construction
- `TestNPCResponseParser` (3 tests) — parse handling
- `TestNPCMind` (22 tests) — lifecycle, relevance, round-trip
- `TestWorldSimulationHelpers` (7 tests) — npc_index, minds, events
- `TestPlayerActionHelpers` (4 tests) — affected NPC inference
- `TestSceneGeneratorHelpers` (5 tests) — actor collection
- `TestNarratorHelpers` (3 tests) — mind context attachment
- `TestCompatibilityWrappers` (6 tests) — wrapper imports

### Functional Test Classes
- `TestNPCLifecycle` (3 tests) — full observe→refresh→decide cycle
- `TestMultiNPCSimulation` (3 tests) — multi-NPC batch processing
- `TestStatePersistence` (3 tests) — serialization survival
- `TestPlayerActionPipeline` (2 tests) — enriched action events
- `TestSceneEnrichment` (2 tests) — NPC actor injection
- `TestNarratorEnrichment` (1 test) — Phase 6 prompt context

### Regression Test Classes
- `TestDeterminism` (5 tests) — identical I/O guarantee
- `TestSerializationRoundTrip` (6 tests) — field preservation
- `TestBoundaryInvariants` (11 tests) — clamping, limits, crash safety

### Run Command
```bash
cd src && PYTHONPATH="." python3 -m pytest \
  tests/unit/rpg/test_phase6_deterministic_npc.py \
  tests/functional/test_phase6_deterministic_npc_functional.py \
  tests/regression/test_phase6_deterministic_npc_regression.py \
  -v --noconftest
```

---

## Component Details

### NPCMemory (`npc_memory.py`)
- Salience-sorted entries with configurable max (default 32)
- Player events boosted to ≥0.7 salience
- Self-targeted events boosted to ≥0.9 salience
- Stable memory IDs: `mem:{npc_id}:{tick}:{index}:{type}:{target}`

### BeliefModel (`belief_model.py`)
- Four axes: trust, fear, respect, hostility (all clamped to [-1.0, 1.0])
- Event-driven updates based on actor, type, faction alignment, location
- Player help → +trust, +respect
- Player attack → +hostility, -trust, +fear
- Faction alignment → amplified trust/hostility shifts

### GoalEngine (`goal_engine.py`)
- Priority-based generation from beliefs + simulation state
- Location pressure ≥2.0 → stabilize_location goal
- Hostility ≥0.35 → retaliate goal
- Fear ≥0.35 → avoid_player goal
- Trust ≥0.35 → approach_player goal
- Default → observe goal
- Deduplication by goal_id, merge favors higher priority

### NPCMind (`npc_mind.py`)
- Orchestrator: observe_events → refresh_goals → decide
- Event relevance filtering (player always relevant, self-target, faction, location)
- Goal→intent mapping (stabilize→stabilize, retaliate→retaliate, etc.)
- Decision validated through NPCDecisionValidator
- Full narrator context export

### Integration: world_simulation.py
- NPC index built from setup payload NPC definitions
- NPC minds loaded from simulation state (or created fresh)
- All NPCs observe events, refresh goals, decide each tick
- Decisions converted to events and appended to simulation
- NPC minds serialized back into simulation state

### Integration: world_player_actions.py
- `_infer_affected_npc_ids()` maps actions to affected NPCs via npc_index
- Events enriched with actor, target_kind, faction_id, location_id, affected_npc_ids, salience

### Integration: world_scene_generator.py
- `_collect_scene_actors()` gathers NPCs related to scene source
- Scenes enriched with NPC actors and `primary_npc_ids` list

### Integration: world_scene_narrator.py
- `_attach_npc_mind_context()` injects memory, beliefs, goals, last_decision
- `build_npc_reaction_prompt()` updated with Phase 6 guidance:
  - Use active goals to shape NPC wants
  - Use belief_summary for tone
  - Use memory_summary for continuity
  - Use last_decision for intent alignment

---

## Code Diff

```diff
diff --git a/src/app/rpg/ai/llm_mind/__init__.py b/src/app/rpg/ai/llm_mind/__init__.py
index b6b73f0..1033fd3 100644
--- a/src/app/rpg/ai/llm_mind/__init__.py
+++ b/src/app/rpg/ai/llm_mind/__init__.py
@@ -1 +1,19 @@
-"""LLM Mind module."""
+from .belief_model import BeliefModel
+from .npc_memory import NPCMemory
+from .goal_engine import GoalEngine
+from .npc_decision import NPCDecision
+from .npc_prompt_builder import NPCPromptBuilder
+from .npc_response_parser import NPCResponseParser
+from .npc_decision_validator import NPCDecisionValidator
+from .npc_mind import NPCMind
+
+__all__ = [
+    "BeliefModel",
+    "NPCMemory",
+    "GoalEngine",
+    "NPCDecision",
+    "NPCPromptBuilder",
+    "NPCResponseParser",
+    "NPCDecisionValidator",
+    "NPCMind",
+]
diff --git a/src/app/rpg/ai/llm_mind/belief_model.py b/src/app/rpg/ai/llm_mind/belief_model.py
index 37ec0f7..2d9e9e4 100644
--- a/src/app/rpg/ai/llm_mind/belief_model.py
+++ b/src/app/rpg/ai/llm_mind/belief_model.py
@@ -1 +1,147 @@
-"""Belief model."""
+from __future__ import annotations
+
+from dataclasses import dataclass, field
+from typing import Any, Dict
+
+
+_BELIEF_KEYS = ("trust", "fear", "respect", "hostility")
+
+
+def _safe_str(value: Any) -> str:
+    if value is None:
+        return ""
+    return str(value)
+
+
+def _safe_float(value: Any, default: float = 0.0) -> float:
+    try:
+        return float(value)
+    except Exception:
+        return default
+
+
+def _clamp_signed(value: float) -> float:
+    return max(-1.0, min(1.0, value))
+
+
+def _empty_belief_record() -> Dict[str, float]:
+    return {
+        "trust": 0.0,
+        "fear": 0.0,
+        "respect": 0.0,
+        "hostility": 0.0,
+    }
+
+
+@dataclass
+class BeliefModel:
+    beliefs: Dict[str, Dict[str, float]] = field(default_factory=dict)
+
+    def to_dict(self) -> Dict[str, Any]:
+        normalized: Dict[str, Dict[str, float]] = {}
+        for target_id, record in sorted(self.beliefs.items()):
+            normalized[target_id] = {
+                key: _clamp_signed(_safe_float(record.get(key), 0.0))
+                for key in _BELIEF_KEYS
+            }
+        return {"beliefs": normalized}
+
+    @classmethod
+    def from_dict(cls, data: Dict[str, Any] | None) -> "BeliefModel":
+        data = data or {}
+        raw = data.get("beliefs") or {}
+        beliefs: Dict[str, Dict[str, float]] = {}
+        for target_id, record in raw.items():
+            if not isinstance(record, dict):
+                continue
+            beliefs[_safe_str(target_id)] = {
+                key: _clamp_signed(_safe_float(record.get(key), 0.0))
+                for key in _BELIEF_KEYS
+            }
+        return cls(beliefs=beliefs)
+
+    def _ensure_target(self, target_id: str) -> Dict[str, float]:
+        target_id = _safe_str(target_id)
+        if target_id not in self.beliefs:
+            self.beliefs[target_id] = _empty_belief_record()
+        return self.beliefs[target_id]
+
+    def update_belief(self, target_id: str, key: str, delta: float) -> float:
+        if key not in _BELIEF_KEYS:
+            return 0.0
+        record = self._ensure_target(target_id)
+        record[key] = _clamp_signed(_safe_float(record.get(key), 0.0) + float(delta))
+        return record[key]
+
+    def get_beliefs(self, target_id: str) -> Dict[str, float]:
+        record = self._ensure_target(target_id)
+        return dict(record)
+
+    def summarize(self, limit: int = 8) -> Dict[str, Dict[str, float]]:
+        items = sorted(self.beliefs.items(), key=lambda pair: pair[0])
+        out: Dict[str, Dict[str, float]] = {}
+        for target_id, record in items[: max(0, limit)]:
+            out[target_id] = dict(record)
+        return out
+
+    def update_from_event(self, event: Dict[str, Any], npc_context: Dict[str, Any]) -> None:
+        event = event or {}
+        npc_context = npc_context or {}
+
+        actor = _safe_str(event.get("actor"))
+        event_type = _safe_str(event.get("type"))
+        target_id = _safe_str(event.get("target_id"))
+        faction_id = _safe_str(event.get("faction_id"))
+        location_id = _safe_str(event.get("location_id"))
+
+        npc_id = _safe_str(npc_context.get("npc_id"))
+        npc_faction_id = _safe_str(npc_context.get("faction_id"))
+        npc_location_id = _safe_str(npc_context.get("location_id"))
+
+        # Direct player/NPC relationship updates
+        if actor == "player":
+            if event_type in {"help", "support", "assist"}:
+                self.update_belief("player", "trust", 0.20)
+                self.update_belief("player", "respect", 0.10)
+
+            if event_type in {"threaten", "coerce"}:
+                self.update_belief("player", "fear", 0.25)
+                self.update_belief("player", "hostility", 0.15)
+                self.update_belief("player", "trust", -0.15)
+
+            if event_type in {"attack", "betray", "sabotage"}:
+                self.update_belief("player", "hostility", 0.40)
+                self.update_belief("player", "trust", -0.40)
+                self.update_belief("player", "fear", 0.20)
+
+            if event_type in {"negotiate", "parley"}:
+                self.update_belief("player", "respect", 0.10)
+
+        # If event affects this NPC directly
+        if target_id and target_id == npc_id:
+            if actor == "player":
+                self.update_belief("player", "respect", 0.10)
+                if event_type in {"help", "support"}:
+                    self.update_belief("player", "trust", 0.20)
+                elif event_type in {"attack", "threaten", "coerce"}:
+                    self.update_belief("player", "hostility", 0.30)
+                    self.update_belief("player", "fear", 0.20)
+
+        # Faction alignment effects
+        if npc_faction_id and faction_id and faction_id == npc_faction_id:
+            if actor == "player":
+                if event_type in {"help", "support", "stabilize"}:
+                    self.update_belief("player", "trust", 0.15)
+                    self.update_belief("player", "respect", 0.10)
+                elif event_type in {"attack", "sabotage", "destabilize"}:
+                    self.update_belief("player", "hostility", 0.20)
+                    self.update_belief("player", "trust", -0.20)
+
+        # Locality effects
+        if npc_location_id and location_id and location_id == npc_location_id:
+            if actor == "player":
+                if event_type in {"stabilize", "protect"}:
+                    self.update_belief("player", "respect", 0.10)
+                elif event_type in {"cause_chaos", "destabilize", "attack"}:
+                    self.update_belief("player", "fear", 0.10)
+                    self.update_belief("player", "hostility", 0.10)
diff --git a/src/app/rpg/ai/llm_mind/decision.py b/src/app/rpg/ai/llm_mind/decision.py
index b84e2d7..f25fa34 100644
--- a/src/app/rpg/ai/llm_mind/decision.py
+++ b/src/app/rpg/ai/llm_mind/decision.py
@@ -1 +1,3 @@
-"""Decision."""
+from .npc_decision import NPCDecision
+
+__all__ = ["NPCDecision"]
diff --git a/src/app/rpg/ai/llm_mind/goal_engine.py b/src/app/rpg/ai/llm_mind/goal_engine.py
index f561b65..35106e0 100644
--- a/src/app/rpg/ai/llm_mind/goal_engine.py
+++ b/src/app/rpg/ai/llm_mind/goal_engine.py
@@ -1,270 +1,217 @@
-"""Goal Engine with Lifecycle Management.
-
-Patch 2: Goal Lifecycle
-- Goals track completion state (active -> completed/failed)
-- Progress increments based on matching events
-- Completed goals are pruned from active list
-- Summary includes completed/failed counts
-"""
-
 from __future__ import annotations
 
-from typing import Any, Dict, List, Optional
-
+from dataclasses import dataclass, field
+from typing import Any, Dict, List
 
-class ActiveGoal:
-    """Represents an active goal with progress tracking and lifecycle.
 
-    Attributes:
-        goal: The goal definition dict.
-        progress: Float from 0.0 to 1.0 indicating completion.
-        completed: Whether this goal has been completed.
-        failed: Whether this goal has been abandoned/failed.
-    """
+_MAX_GOALS = 5
 
-    def __init__(self, goal: Dict[str, Any]):
-        """Initialize an active goal.
 
-        Args:
-            goal: Goal dict with 'type', 'target', 'priority' keys.
-        """
-        self.goal = goal
-        self.progress = 0.0
-        self.completed = False
-        self.failed = False
+def _safe_str(value: Any) -> str:
+    if value is None:
+        return ""
+    return str(value)
 
-    @property
-    def goal_type(self) -> str:
-        """Return the goal type."""
-        return self.goal.get("type", "unknown")
 
-    @property
-    def target(self) -> Optional[str]:
-        """Return the goal target."""
-        return self.goal.get("target")
+def _safe_float(value: Any, default: float = 0.0) -> float:
+    try:
+        return float(value)
+    except Exception:
+        return default
 
-    @property
-    def priority(self) -> float:
-        """Return the goal priority."""
-        return self.goal.get("priority", 0.5)
 
-    def advance(self, amount: float) -> None:
-        """Advance goal progress.
+def _goal_sort_key(goal: Dict[str, Any]):
+    priority = _safe_float(goal.get("priority"), 0.0)
+    goal_id = _safe_str(goal.get("goal_id"))
+    return (-priority, goal_id)
 
-        Args:
-            amount: Amount to add to progress.
-        """
-        self.progress = min(1.0, max(0.0, self.progress + amount))
-        if self.progress >= 1.0:
-            self.completed = True
 
-    def mark_failed(self) -> None:
-        """Mark this goal as failed."""
-        self.failed = True
+@dataclass
+class GoalEngine:
+    goals: List[Dict[str, Any]] = field(default_factory=list)
+    max_goals: int = _MAX_GOALS
 
     def to_dict(self) -> Dict[str, Any]:
-        """Return dict representation.
-
-        Returns:
-            Dict with goal state fields.
-        """
         return {
-            "type": self.goal_type,
-            "target": self.target,
-            "priority": self.priority,
-            "progress": self.progress,
-            "completed": self.completed,
-            "failed": self.failed,
-            "raw_goal": self.goal,
+            "goals": [dict(goal) for goal in self.goals],
+            "max_goals": int(self.max_goals),
         }
 
-    def __repr__(self) -> str:
-        return (
-            f"ActiveGoal(type='{self.goal_type}', "
-            f"progress={self.progress:.2f}, "
-            f"completed={self.completed}, failed={self.failed})"
-        )
-
-
-class GoalEngine:
-    """Manages NPC goals with lifecycle tracking and progress.
-
-    Patch 2 additions:
-    - Goals have completed/failed state
-    - Events advance progress for matching goals
-    - Completed goals are automatically pruned
-    - Summary shows full lifecycle state
-    """
-
-    def __init__(self, npc_id: str = ""):
-        """Initialize goal engine.
-
-        Args:
-            npc_id: NPC identifier.
-        """
-        self.npc_id = npc_id
-        self.active_goals: List[ActiveGoal] = []
-        self.completed_goals: List[ActiveGoal] = []
-        self.failed_goals: List[ActiveGoal] = []
-
-    def add_goal(self, goal: Dict[str, Any]) -> ActiveGoal:
-        """Add a goal to the active pool.
-
-        Args:
-            goal: Goal dict with 'type', 'priority', etc.
-
-        Returns:
-            The created ActiveGoal wrapper.
-        """
-        ag = ActiveGoal(goal)
-        self.active_goals.append(ag)
-        return ag
-
-    def add_goals(self, goals: List[Dict[str, Any]]) -> List[ActiveGoal]:
-        """Add multiple goals at once.
-
-        Args:
-            goals: List of goal dicts.
-
-        Returns:
-            List of created ActiveGoal wrappers.
-        """
-        added = []
-        for g in goals:
-            added.append(self.add_goal(g))
-        return added
-
-    def update_progress(self, event: Dict[str, Any]) -> List[ActiveGoal]:
-        """Update goal progress based on an event.
-
-        Patch 2: Match events to goals and advance progress.
-       复仇 events match revenge goals, attack events match attack goals, etc.
-
-        Args:
-            event: Event dict with 'type', 'target', 'actor' keys.
-
-        Returns:
-            List of goals that were completed by this event.
-        """
-        event_type = event.get("type", "")
-        event_target = event.get("target", "")
-        completed: List[ActiveGoal] = []
-
-        for g in self.active_goals:
-            if g.completed or g.failed:
+    @classmethod
+    def from_dict(cls, data: Dict[str, Any] | None) -> "GoalEngine":
+        data = data or {}
+        raw_goals = data.get("goals") or []
+        max_goals = int(data.get("max_goals", _MAX_GOALS) or _MAX_GOALS)
+        goals: List[Dict[str, Any]] = []
+        for item in raw_goals:
+            if not isinstance(item, dict):
                 continue
-
-            g_type = g.goal_type
-
-            # Revenge goals advance on attack/damage to the target
-            if g_type == "revenge" and event_type in ("attack", "damage", "kill"):
-                if event_target == g.target:
-                    g.advance(0.5)
-
-            # Protect goals advance when threat is neutralized
-            if g_type == "protect" and event_type in ("attack", "kill"):
-                if event_target == g.target:
-                    g.advance(0.3)
-
-            # Generic: any goal with matching target type advances
-            if g.target and event_target == g.target:
-                g.advance(0.2)
-
-            # Check for completion
-            if g.progress >= 1.0 and not g.completed:
-                g.completed = True
-                completed.append(g)
-
-        # Move completed goals
-        for g in completed:
-            self.active_goals.remove(g)
-            self.completed_goals.append(g)
-
-        return completed
-
-    def prune(self) -> Dict[str, int]:
-        """Remove completed/failed goals from active list.
-
-        Returns:
-            Dict with counts of pruned goals.
-        """
-        stats: Dict[str, int] = {"completed": 0, "failed": 0, "pruned": 0}
-
-        still_active: List[ActiveGoal] = []
-        for g in self.active_goals:
-            if g.completed:
-                self.completed_goals.append(g)
-                stats["completed"] += 1
-                stats["pruned"] += 1
-            elif g.failed:
-                self.failed_goals.append(g)
-                stats["failed"] += 1
-                stats["pruned"] += 1
-            else:
-                still_active.append(g)
-
-        self.active_goals = still_active
-        return stats
-
-    def clear_resolved(self) -> None:
-        """Remove completed/failed goals from active list.
-
-        Patch 2: Lifecycle cleanup - only keep non-resolved goals.
-        """
-        self.active_goals = [g for g in self.active_goals if not g.completed and not g.failed]
-        for g in self.active_goals[:]:
-            if g.completed:
-                self.completed_goals.append(g)
-            elif g.failed:
-                self.failed_goals.append(g)
-        self.active_goals = [g for g in self.active_goals if not g.completed and not g.failed]
-
-    def summarize(self) -> Dict[str, Any]:
-        """Return a summary of goal state.
-
-        Returns:
-            Dict with active, completed, failed counts and details.
-        """
+            goals.append({
+                "goal_id": _safe_str(item.get("goal_id")),
+                "type": _safe_str(item.get("type")),
+                "target_id": _safe_str(item.get("target_id")),
+                "priority": _safe_float(item.get("priority"), 0.0),
+                "reason": _safe_str(item.get("reason")),
+                "status": _safe_str(item.get("status")) or "active",
+                "progress": _safe_float(item.get("progress"), 0.0),
+            })
+        engine = cls(goals=goals, max_goals=max_goals)
+        engine.goals = sorted(engine.goals, key=_goal_sort_key)[: engine.max_goals]
+        return engine
+
+    def _make_goal(
+        self,
+        npc_id: str,
+        goal_type: str,
+        target_id: str,
+        priority: float,
+        reason: str,
+    ) -> Dict[str, Any]:
+        goal_id = f"goal:{npc_id}:{goal_type}:{target_id or 'none'}"
         return {
-            "active_count": len(self.active_goals),
-            "completed_count": len(self.completed_goals),
-            "failed_count": len(self.failed_goals),
-            "active": [g.to_dict() for g in self.active_goals],
-            "completed": [g.to_dict() for g in self.completed_goals[:5]],
-            "failed": [g.to_dict() for g in self.failed_goals[:5]],
+            "goal_id": goal_id,
+            "type": goal_type,
+            "target_id": target_id,
+            "priority": float(priority),
+            "reason": reason,
+            "status": "active",
+            "progress": 0.0,
         }
 
-    def get_highest_priority(self) -> Optional[ActiveGoal]:
-        """Return the highest priority active goal.
-
-        Returns:
-            ActiveGoal with highest priority, or None.
-        """
-        if not self.active_goals:
-            return None
-        return max(self.active_goals, key=lambda g: g.priority)
-
-    def has_goal_type(self, goal_type: str) -> bool:
-        """Check if a goal type is active.
-
-        Args:
-            goal_type: Goal type to search for.
+    def generate_goals(
+        self,
+        npc_context: Dict[str, Any],
+        simulation_state: Dict[str, Any],
+        belief_summary: Dict[str, Dict[str, float]],
+        memory_summary: List[Dict[str, Any]],
+    ) -> List[Dict[str, Any]]:
+        npc_context = npc_context or {}
+        simulation_state = simulation_state or {}
+        belief_summary = belief_summary or {}
+
+        npc_id = _safe_str(npc_context.get("npc_id"))
+        npc_location_id = _safe_str(npc_context.get("location_id"))
+        npc_faction_id = _safe_str(npc_context.get("faction_id"))
+
+        player_beliefs = belief_summary.get("player", {})
+        trust = _safe_float(player_beliefs.get("trust"), 0.0)
+        fear = _safe_float(player_beliefs.get("fear"), 0.0)
+        hostility = _safe_float(player_beliefs.get("hostility"), 0.0)
+
+        locations = simulation_state.get("locations") or {}
+        location_state = locations.get(npc_location_id) or {}
+        location_pressure = _safe_float(location_state.get("pressure"), 0.0)
+
+        goals: List[Dict[str, Any]] = []
+
+        if location_pressure >= 2.0 and npc_location_id:
+            goals.append(self._make_goal(
+                npc_id=npc_id,
+                goal_type="stabilize_location",
+                target_id=npc_location_id,
+                priority=0.80 + min(location_pressure * 0.05, 0.15),
+                reason="Local pressure is elevated",
+            ))
+
+        if npc_faction_id:
+            goals.append(self._make_goal(
+                npc_id=npc_id,
+                goal_type="support_faction",
+                target_id=npc_faction_id,
+                priority=0.45,
+                reason="Faction loyalty baseline",
+            ))
+
+        if hostility >= 0.35:
+            goals.append(self._make_goal(
+                npc_id=npc_id,
+                goal_type="retaliate",
+                target_id="player",
+                priority=0.70 + min(hostility * 0.20, 0.20),
+                reason="Player is viewed as hostile",
+            ))
+        elif fear >= 0.35:
+            goals.append(self._make_goal(
+                npc_id=npc_id,
+                goal_type="avoid_player",
+                target_id="player",
+                priority=0.65 + min(fear * 0.20, 0.20),
+                reason="Player is viewed as threatening",
+            ))
+        elif trust >= 0.35:
+            goals.append(self._make_goal(
+                npc_id=npc_id,
+                goal_type="approach_player",
+                target_id="player",
+                priority=0.60 + min(trust * 0.20, 0.20),
+                reason="Player is viewed as trustworthy",
+            ))
+        else:
+            goals.append(self._make_goal(
+                npc_id=npc_id,
+                goal_type="observe",
+                target_id="player",
+                priority=0.35,
+                reason="Maintain awareness of player",
+            ))
+
+        if memory_summary:
+            top_memory = memory_summary[0]
+            top_target = _safe_str(top_memory.get("target_id"))
+            top_type = _safe_str(top_memory.get("type"))
+            if top_target and top_target != "player" and top_type in {"incident", "attack", "destabilize", "threaten"}:
+                goals.append(self._make_goal(
+                    npc_id=npc_id,
+                    goal_type="investigate",
+                    target_id=top_target,
+                    priority=0.55,
+                    reason=f"Recent salient memory: {top_type}",
+                ))
+
+        goals = sorted(goals, key=_goal_sort_key)
+
+        deduped: List[Dict[str, Any]] = []
+        seen = set()
+        for goal in goals:
+            goal_id = goal["goal_id"]
+            if goal_id in seen:
+                continue
+            seen.add(goal_id)
+            deduped.append(goal)
 
-        Returns:
-            True if an active goal of that type exists.
-        """
-        return any(g.goal_type == goal_type and not g.completed and not g.failed for g in self.active_goals)
+        return deduped[: self.max_goals]
 
-    def reset(self) -> None:
-        """Clear all goals."""
-        self.active_goals.clear()
-        self.completed_goals.clear()
-        self.failed_goals.clear()
+    def merge_goals(self, generated: List[Dict[str, Any]]) -> None:
+        generated = generated or []
+        merged = {}
+        for goal in self.goals + generated:
+            goal_id = _safe_str(goal.get("goal_id"))
+            if not goal_id:
+                continue
+            existing = merged.get(goal_id)
+            if existing is None or _safe_float(goal.get("priority"), 0.0) > _safe_float(existing.get("priority"), 0.0):
+                merged[goal_id] = dict(goal)
+        self.goals = sorted(merged.values(), key=_goal_sort_key)[: self.max_goals]
 
-    def __repr__(self) -> str:
-        return (
-            f"GoalEngine(npc='{self.npc_id}', "
-            f"active={len(self.active_goals)}, "
-            f"completed={len(self.completed_goals)}, "
-            f"failed={len(self.failed_goals)})"
-        )
\ No newline at end of file
+    def top_goal(self) -> Dict[str, Any] | None:
+        if not self.goals:
+            return None
+        return dict(sorted(self.goals, key=_goal_sort_key)[0])
+
+    def advance_from_event(self, event: Dict[str, Any]) -> None:
+        event = event or {}
+        target_id = _safe_str(event.get("target_id"))
+        event_type = _safe_str(event.get("type"))
+
+        updated: List[Dict[str, Any]] = []
+        for goal in self.goals:
+            new_goal = dict(goal)
+            if target_id and target_id == _safe_str(goal.get("target_id")):
+                progress = _safe_float(goal.get("progress"), 0.0)
+                if event_type in {"help", "support", "stabilize", "investigate", "negotiate"}:
+                    progress += 0.25
+                elif event_type in {"attack", "sabotage", "retaliate"}:
+                    progress += 0.15
+                new_goal["progress"] = min(progress, 1.0)
+            updated.append(new_goal)
+        self.goals = sorted(updated, key=_goal_sort_key)[: self.max_goals]
diff --git a/src/app/rpg/ai/llm_mind/memory.py b/src/app/rpg/ai/llm_mind/memory.py
index 88cb55e..b673c95 100644
--- a/src/app/rpg/ai/llm_mind/memory.py
+++ b/src/app/rpg/ai/llm_mind/memory.py
@@ -1,113 +1,3 @@
-"""NPC Memory with Salience-Based Importance and Decay.
+from .npc_memory import NPCMemory
 
-Patch 1: Memory Salience + Decay
-- Events are scored by importance type (betrayal > gift > idle)
-- Old memories decay over time (0.97 multiplier per tick)
-- Memory is pruned to max_size, keeping highest-salience events
-- Summarize returns structured top-10 memories
-"""
-
-from __future__ import annotations
-
-from typing import Any, Dict, List
-
-
-class NPCMemory:
-    """Manages an NPC's event memory with salience-based scoring and decay."""
-
-    # Max events to keep after pruning
-    max_size: int = 50
-
-    def __init__(self, max_size: int = 50):
-        """Initialize memory.
-
-        Args:
-            max_size: Maximum number of events to retain.
-        """
-        self.events: List[Dict[str, Any]] = []  # [{event, importance, age}]
-        self.max_size = max_size
-
-    def remember(self, event: Dict[str, Any]) -> None:
-        """Add an event to memory with importance scoring and decay.
-
-        Args:
-            event: Event dict with at least a 'type' key.
-        """
-        importance = self._score(event)
-        self.events.append({
-            "event": event,
-            "importance": importance,
-            "age": 0,
-        })
-
-        # Apply age increment and decay to all events
-        for e in self.events:
-            e["age"] += 1
-            e["importance"] *= 0.97
-
-        # Sort by importance (descending) and prune
-        self.events = sorted(
-            self.events,
-            key=lambda e: e["importance"],
-            reverse=True,
-        )[: self.max_size]
-
-    def _score(self, event: Dict[str, Any]) -> float:
-        """Compute the salience/importance of an event.
-
-        High-impact events (betrayal, attack) score 1.0
-        Medium events (help, gift) score 0.7
-        Low events (idle, observe) score 0.3
-
-        Args:
-            event: Event dict.
-
-        Returns:
-            Importance score between 0.0 and 1.0.
-        """
-        t = event.get("type", "")
-        if t in ("betrayal", "attack", "death", "combat", "damage"):
-            return 1.0
-        if t in ("help", "gift", "trade", "alliance", "heal"):
-            return 0.7
-        return 0.3
-
-    def summarize(self, limit: int = 10) -> List[Dict[str, Any]]:
-        """Return top memories as a structured summary.
-
-        Args:
-            limit: Maximum number of memories to return.
-
-        Returns:
-            List of dicts with type, actor, target keys.
-        """
-        return [
-            {
-                "type": e["event"].get("type"),
-                "actor": e["event"].get("actor"),
-                "target": e["event"].get("target"),
-            }
-            for e in self.events[:limit]
-        ]
-
-    def get_raw_events(self, limit: int = 10) -> List[Dict[str, Any]]:
-        """Return raw event dicts for the top memories.
-
-        Args:
-            limit: Maximum events to return.
-
-        Returns:
-            List of raw event dicts.
-        """
-        return [e["event"] for e in self.events[:limit]]
-
-    def clear(self) -> None:
-        """Clear all memories."""
-        self.events.clear()
-
-    def __len__(self) -> int:
-        """Return number of stored events."""
-        return len(self.events)
-
-    def __repr__(self) -> str:
-        return f"NPCMemory(events={len(self.events)}, max={self.max_size})"
\ No newline at end of file
+__all__ = ["NPCMemory"]
diff --git a/src/app/rpg/ai/llm_mind/npc_decision.py b/src/app/rpg/ai/llm_mind/npc_decision.py
new file mode 100644
index 0000000..e1a09d8
--- /dev/null
+++ b/src/app/rpg/ai/llm_mind/npc_decision.py
@@ -0,0 +1,58 @@
+from __future__ import annotations
+
+from dataclasses import dataclass, asdict
+from typing import Any, Dict
+
+
+@dataclass
+class NPCDecision:
+    npc_id: str
+    tick: int
+    intent: str
+    action_type: str
+    target_id: str
+    target_kind: str
+    location_id: str
+    reason: str
+    dialogue_hint: str
+    urgency: float
+
+    def to_dict(self) -> Dict[str, Any]:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: Dict[str, Any] | None) -> "NPCDecision":
+        data = data or {}
+        return cls(
+            npc_id=str(data.get("npc_id") or ""),
+            tick=int(data.get("tick", 0) or 0),
+            intent=str(data.get("intent") or "wait"),
+            action_type=str(data.get("action_type") or "wait"),
+            target_id=str(data.get("target_id") or ""),
+            target_kind=str(data.get("target_kind") or ""),
+            location_id=str(data.get("location_id") or ""),
+            reason=str(data.get("reason") or ""),
+            dialogue_hint=str(data.get("dialogue_hint") or ""),
+            urgency=float(data.get("urgency", 0.0) or 0.0),
+        )
+
+    @classmethod
+    def fallback(
+        cls,
+        npc_id: str,
+        tick: int,
+        location_id: str,
+        reason: str = "No strong action selected",
+    ) -> "NPCDecision":
+        return cls(
+            npc_id=npc_id,
+            tick=tick,
+            intent="wait",
+            action_type="wait",
+            target_id="",
+            target_kind="",
+            location_id=location_id,
+            reason=reason,
+            dialogue_hint="The NPC hesitates and watches events unfold.",
+            urgency=0.10,
+        )
diff --git a/src/app/rpg/ai/llm_mind/npc_decision_validator.py b/src/app/rpg/ai/llm_mind/npc_decision_validator.py
new file mode 100644
index 0000000..44432a6
--- /dev/null
+++ b/src/app/rpg/ai/llm_mind/npc_decision_validator.py
@@ -0,0 +1,54 @@
+from __future__ import annotations
+
+from typing import Any, Dict
+
+
+_ALLOWED_INTENTS = {
+    "observe",
+    "support",
+    "confront",
+    "avoid",
+    "investigate",
+    "negotiate",
+    "stabilize",
+    "retaliate",
+    "wait",
+}
+
+_ALLOWED_ACTION_TYPES = {
+    "observe",
+    "support",
+    "confront",
+    "avoid",
+    "investigate",
+    "negotiate",
+    "stabilize",
+    "retaliate",
+    "wait",
+}
+
+
+class NPCDecisionValidator:
+    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
+        data = dict(data or {})
+
+        intent = str(data.get("intent") or "wait")
+        action_type = str(data.get("action_type") or "wait")
+
+        if intent not in _ALLOWED_INTENTS:
+            intent = "wait"
+        if action_type not in _ALLOWED_ACTION_TYPES:
+            action_type = "wait"
+
+        data["intent"] = intent
+        data["action_type"] = action_type
+
+        data["npc_id"] = str(data.get("npc_id") or "")
+        data["tick"] = int(data.get("tick", 0) or 0)
+        data["target_id"] = str(data.get("target_id") or "")
+        data["target_kind"] = str(data.get("target_kind") or "")
+        data["location_id"] = str(data.get("location_id") or "")
+        data["reason"] = str(data.get("reason") or "")
+        data["dialogue_hint"] = str(data.get("dialogue_hint") or "")
+        data["urgency"] = float(data.get("urgency", 0.0) or 0.0)
+        return data
diff --git a/src/app/rpg/ai/llm_mind/npc_memory.py b/src/app/rpg/ai/llm_mind/npc_memory.py
new file mode 100644
index 0000000..9fec29a
--- /dev/null
+++ b/src/app/rpg/ai/llm_mind/npc_memory.py
@@ -0,0 +1,124 @@
+from __future__ import annotations
+
+from dataclasses import dataclass, field
+from typing import Any, Dict, List
+
+
+_MAX_MEMORIES = 32
+
+
+def _safe_str(value: Any) -> str:
+    if value is None:
+        return ""
+    return str(value)
+
+
+def _safe_float(value: Any, default: float = 0.0) -> float:
+    try:
+        return float(value)
+    except Exception:
+        return default
+
+
+def _clamp01(value: float) -> float:
+    return max(0.0, min(1.0, value))
+
+
+def _memory_sort_key(item: Dict[str, Any]):
+    salience = _safe_float(item.get("salience"), 0.0)
+    tick = int(item.get("tick", 0) or 0)
+    memory_id = _safe_str(item.get("memory_id"))
+    return (-salience, -tick, memory_id)
+
+
+@dataclass
+class NPCMemory:
+    npc_id: str
+    entries: List[Dict[str, Any]] = field(default_factory=list)
+    max_entries: int = _MAX_MEMORIES
+
+    def to_dict(self) -> Dict[str, Any]:
+        return {
+            "npc_id": self.npc_id,
+            "entries": [dict(entry) for entry in self.entries],
+            "max_entries": int(self.max_entries),
+        }
+
+    @classmethod
+    def from_dict(cls, data: Dict[str, Any] | None) -> "NPCMemory":
+        data = data or {}
+        npc_id = _safe_str(data.get("npc_id"))
+        max_entries = int(data.get("max_entries", _MAX_MEMORIES) or _MAX_MEMORIES)
+        raw_entries = data.get("entries") or []
+        entries: List[Dict[str, Any]] = []
+        for item in raw_entries:
+            if not isinstance(item, dict):
+                continue
+            entries.append({
+                "memory_id": _safe_str(item.get("memory_id")),
+                "tick": int(item.get("tick", 0) or 0),
+                "type": _safe_str(item.get("type")),
+                "actor": _safe_str(item.get("actor")),
+                "target_id": _safe_str(item.get("target_id")),
+                "target_kind": _safe_str(item.get("target_kind")),
+                "location_id": _safe_str(item.get("location_id")),
+                "faction_id": _safe_str(item.get("faction_id")),
+                "summary": _safe_str(item.get("summary")),
+                "salience": _clamp01(_safe_float(item.get("salience"), 0.0)),
+            })
+        memory = cls(npc_id=npc_id, entries=entries, max_entries=max_entries)
+        memory._trim()
+        return memory
+
+    def _trim(self) -> None:
+        self.entries = sorted(self.entries, key=_memory_sort_key)[: self.max_entries]
+        self.entries = sorted(
+            self.entries,
+            key=lambda item: (
+                int(item.get("tick", 0) or 0),
+                _safe_str(item.get("memory_id")),
+            ),
+        )
+
+    def remember(self, event: Dict[str, Any], tick: int, index: int = 0) -> None:
+        event = event or {}
+        event_type = _safe_str(event.get("type")) or "unknown"
+        actor = _safe_str(event.get("actor"))
+        target_id = _safe_str(event.get("target_id"))
+        target_kind = _safe_str(event.get("target_kind"))
+        location_id = _safe_str(event.get("location_id"))
+        faction_id = _safe_str(event.get("faction_id"))
+        summary = _safe_str(event.get("summary")) or event_type
+
+        salience = _clamp01(_safe_float(event.get("salience"), 0.4))
+        if actor == "player":
+            salience = max(salience, 0.7)
+        if target_id == self.npc_id:
+            salience = max(salience, 0.9)
+
+        memory_id = f"mem:{self.npc_id}:{tick}:{index}:{event_type}:{target_id or 'none'}"
+
+        self.entries.append({
+            "memory_id": memory_id,
+            "tick": int(tick),
+            "type": event_type,
+            "actor": actor,
+            "target_id": target_id,
+            "target_kind": target_kind,
+            "location_id": location_id,
+            "faction_id": faction_id,
+            "summary": summary,
+            "salience": salience,
+        })
+        self._trim()
+
+    def remember_many(self, events: List[Dict[str, Any]], tick: int) -> None:
+        for index, event in enumerate(events):
+            self.remember(event, tick=tick, index=index)
+
+    def top_memories(self, limit: int = 5) -> List[Dict[str, Any]]:
+        ranked = sorted(self.entries, key=_memory_sort_key)
+        return [dict(item) for item in ranked[: max(0, limit)]]
+
+    def summary(self, limit: int = 5) -> List[Dict[str, Any]]:
+        return self.top_memories(limit=limit)
diff --git a/src/app/rpg/ai/llm_mind/npc_mind.py b/src/app/rpg/ai/llm_mind/npc_mind.py
index 6c55923..8b866b7 100644
--- a/src/app/rpg/ai/llm_mind/npc_mind.py
+++ b/src/app/rpg/ai/llm_mind/npc_mind.py
@@ -1,363 +1,169 @@
-"""NPC Mind -- Unified decision engine for LLM-driven NPCs.
-
-Patches implemented:
-- Patch 5: Spatial Awareness (visible entities, location filtering)
-- Patch 6: LLM Load Control (urgency-based thinking skip)
-- Patch 7: Multi-NPC Interaction Logic (interaction intent priority)
-"""
-
 from __future__ import annotations
 
-from typing import Any, Dict, List, Optional
+from typing import Any, Dict, List
 
-from .memory import NPCMemory
+from .belief_model import BeliefModel
 from .goal_engine import GoalEngine
-from .prompt_builder import build_context, build_npc_prompt
-from .response_parser import NPCDecision, NPCResponseParser
+from .npc_decision import NPCDecision
+from .npc_decision_validator import NPCDecisionValidator
+from .npc_memory import NPCMemory
 
 
-class NPCMind:
-    """Complete LLM-driven NPC mind with all patches.
+def _safe_str(value: Any) -> str:
+    if value is None:
+        return ""
+    return str(value)
 
-    Usage:
-        mind = NPCMind(llm_client, npc_id="1", ...)
-        decision = mind.decide(world_state)
-    """
 
+class NPCMind:
     def __init__(
         self,
-        llm_client=None,
-        npc_id: str = "",
-        npc_name: str = "NPC",
-        npc_role: str = "villager",
-        personality: Optional[Dict[str, float]] = None,
+        npc_id: str,
+        memory: NPCMemory | None = None,
+        beliefs: BeliefModel | None = None,
+        goal_engine: GoalEngine | None = None,
+        last_decision: Dict[str, Any] | None = None,
+        last_seen_tick: int = 0,
     ):
-        """Initialize the NPC mind.
-
-        Args:
-            llm_client: LLM client for generation (can be None for testing).
-            npc_id: Unique identifier.
-            npc_name: Display name.
-            npc_role: Role/occupation.
-            personality: Trait dict (aggression, honor, greed).
-        """
-        self.llm_client = llm_client
         self.npc_id = npc_id
-        self.npc_name = npc_name
-        self.npc_role = npc_role
-
-        # Patch 3: Personality traits
-        self.personality = personality or {
-            "aggression": 0.5,
-            "honor": 0.5,
-            "greed": 0.5,
+        self.memory = memory or NPCMemory(npc_id=npc_id)
+        self.beliefs = beliefs or BeliefModel()
+        self.goal_engine = goal_engine or GoalEngine()
+        self.last_decision = dict(last_decision or {})
+        self.last_seen_tick = int(last_seen_tick or 0)
+        self.validator = NPCDecisionValidator()
+
+    def to_dict(self) -> Dict[str, Any]:
+        return {
+            "npc_id": self.npc_id,
+            "memory": self.memory.to_dict(),
+            "beliefs": self.beliefs.to_dict(),
+            "goals": self.goal_engine.to_dict(),
+            "last_decision": dict(self.last_decision),
+            "last_seen_tick": self.last_seen_tick,
         }
 
-        # Patch 1: Memory with salience+decay
-        self.memory = NPCMemory()
-
-        # Patch 2: Goal lifecycle engine
-        self.goals = GoalEngine(npc_id=npc_id)
-
-        # Patch 4: Robust parser
-        self.parser = NPCResponseParser()
-
-        # Patch 6: Load control state
-        self.last_decision: Optional[NPCDecision] = None
-        self.last_tick: int = 0
-
-    def decide(self, world: Dict[str, Any], tick: int = 0) -> NPCDecision:
-        """Make a decision based on world state.
-
-        Implements:
-        - Patch 5: Spatial filtering of visible entities
-        - Patch 6: Urgency-based LLM skip
-        - Patch 7: Interaction intent priority
-
-        Args:
-            world: World state dict.
-            tick: Current game tick.
-
-        Returns:
-            NPCDecision from LLM or fallback.
-        """
-        # Patch 5: Filter visible entities
-        visible_entities = self._get_visible_entities(world)
-
-        # Patch 6: Compute urgency for load control
-        urgency = self._compute_urgency()
-
-        # Skip LLM if nothing urgent and we have a recent decision
-        if urgency < 0.3 and self.last_decision and (tick - self.last_tick) < 5:
-            return self.last_decision
-
-        # Patch 7: Build context with interaction priority
-        intent_priority = len(visible_entities) > 0
-
-        context = build_context(
-            npc={"name": self.npc_name, "role": self.npc_role},
-            personality=self.personality,
-            memory=self.memory.summarize(),
-            goals=[g.to_dict() for g in self.goals.active_goals],
-            world={
-                "visible_entities": visible_entities,
-                "location": world.get("location", "unknown"),
-            },
-            recent_events=self.memory.get_raw_events(limit=5),
-            intent_priority=intent_priority,
+    @classmethod
+    def from_dict(cls, data: Dict[str, Any] | None) -> "NPCMind":
+        data = data or {}
+        npc_id = _safe_str(data.get("npc_id"))
+        return cls(
+            npc_id=npc_id,
+            memory=NPCMemory.from_dict(data.get("memory")),
+            beliefs=BeliefModel.from_dict(data.get("beliefs")),
+            goal_engine=GoalEngine.from_dict(data.get("goals")),
+            last_decision=data.get("last_decision") or {},
+            last_seen_tick=int(data.get("last_seen_tick", 0) or 0),
         )
 
-        prompt = build_npc_prompt(context)
-
-        # Call LLM if available
-        if self.llm_client:
-            try:
-                raw = self.llm_client.generate(prompt)
-                decision = self.parser.parse(raw)
-            except Exception:
-                decision = NPCDecision.fallback()
-        else:
-            decision = NPCDecision.fallback()
-
-        # Remember the decision as an event
-        event = {
-            "type": "decision",
-            "actor": self.npc_id,
-            "intent": decision.intent,
-            "target": decision.target,
-            "tick": tick,
-        }
-        self.memory.remember(event)
-
-        # Patch 2: Update goal progress from decision
-        if decision.target:
-            goal_event = {
-                "type": decision.intent,
-                "target": decision.target,
-                "actor": self.npc_id,
-            }
-            self.goals.update_progress(goal_event)
-
-        # Patch 6: Cache decision
-        self.last_decision = decision
-        self.last_tick = tick
-
-        return decision
-
-    def remember_event(self, event: Dict[str, Any]) -> None:
-        """Record an external event into memory.
-
-        Args:
-            event: Event dict.
-        """
-        self.memory.remember(event)
-
-        # Patch 2: Update goal progress
-        self.goals.update_progress(event)
-
-    def add_goal(self, goal: Dict[str, Any]) -> None:
-        """Add a goal.
-
-        Args:
-            goal: Goal dict.
-        """
-        self.goals.add_goal(goal)
-
-    def _get_visible_entities(self, world: Dict[str, Any]) -> List[Any]:
-        """Patch 5: Filter entities by spatial awareness.
-
-        Uses distance and location to determine visibility.
-
-        Args:
-            world: World state.
-
-        Returns:
-            List of visible entity dicts.
-        """
-        my_location = world.get("location", "")
-        my_pos = world.get("position", (0, 0))
-        entities = world.get("entities", [])
-        vision_range = world.get("vision_range", 10.0)
-
-        visible: List[Any] = []
-        for e in entities:
-            if isinstance(e, dict):
-                # Skip self
-                if e.get("id") == self.npc_id:
-                    continue
-                e_loc = e.get("location", "")
-                e_pos = e.get("position")
-
-                # Same location check
-                if my_location and e_loc and my_location == e_loc:
-                    visible.append(e)
-                    continue
-
-                # Distance check
-                if e_pos and my_pos:
-                    dist = self._distance(my_pos, e_pos)
-                    if dist <= vision_range:
-                        e_copy = dict(e)
-                        e_copy["distance"] = dist
-                        visible.append(e_copy)
-            else:
-                visible.append(e)
-
-        return visible
-
-    @staticmethod
-    def _distance(p1: tuple, p2: tuple) -> float:
-        """Euclidean distance between two points.
-
-        Args:
-            p1: First point (x, y).
-            p2: Second point (x, y).
-
-        Returns:
-            Distance value.
-        """
-        import math
-        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
-
-    def _compute_urgency(self) -> float:
-        """Patch 6: Compute urgency for LLM load control.
-
-        High urgency means the NPC needs to think right now.
-        Low urgency means we can reuse the last decision.
-
-        Returns:
-            Urgency value between 0.0 and 1.0.
-        """
-        summary = self.memory.summarize()
-        for mem in summary:
-            t = mem.get("type", "") if isinstance(mem, dict) else ""
-            if t in ("attack", "betrayal", "combat", "death", "damage"):
-                return 1.0
-
-        # Check goals for urgency
-        for g in self.goals.active_goals:
-            if g.priority > 0.8:
-                return 0.9
-            if g.goal_type in ("survive", "flee", "defend"):
-                return 1.0
-
-        return 0.2
-
-    def evaluate_plan(
-        self,
-        npc: Any,
-        plan: Dict[str, Any],
-        world_state: Dict[str, Any],
-    ) -> Dict[str, Any]:
-        """Evaluate and optionally adjust a GOAP plan.
-
-        Instead of deciding the action directly, the LLM reviews the
-        structured plan and returns adjustments:
-            - ``override``: Whether the LLM wants to veto the plan.
-            - ``override_action``: The forced action name when overriding.
-            - ``new_goal``: Alternative goal the LLM suggests.
-            - ``emotional_bias``: Emotion string to inject behavior.
-            - ``risk_tolerance``: Float 0.0–1.0 for risk adjustment.
-
-        This method is designed to be called by the DecisionEngine,
-        replacing the old ``decide_action`` pattern.
-
-        Args:
-            npc: The NPC entity.
-            plan: Structured GOAP plan dict (goal, steps, priority).
-            world_state: The current world state.
-
-        Returns:
-            Adjustment dict with keys: override, new_goal,
-            emotional_bias, risk_tolerance.
-        """
-        urgency = self._compute_urgency()
-        personality_str = ", ".join(
-            f"{k}={v}" for k, v in self.personality.items()
+    def _event_is_relevant(self, event: Dict[str, Any], npc_context: Dict[str, Any]) -> bool:
+        event = event or {}
+        npc_context = npc_context or {}
+
+        npc_id = _safe_str(npc_context.get("npc_id"))
+        npc_faction_id = _safe_str(npc_context.get("faction_id"))
+        npc_location_id = _safe_str(npc_context.get("location_id"))
+
+        actor = _safe_str(event.get("actor"))
+        target_id = _safe_str(event.get("target_id"))
+        faction_id = _safe_str(event.get("faction_id"))
+        location_id = _safe_str(event.get("location_id"))
+        affected_npc_ids = event.get("affected_npc_ids") or []
+
+        if actor == "player":
+            return True
+        if target_id and target_id == npc_id:
+            return True
+        if npc_faction_id and faction_id and faction_id == npc_faction_id:
+            return True
+        if npc_location_id and location_id and location_id == npc_location_id:
+            return True
+        if npc_id and npc_id in affected_npc_ids:
+            return True
+        return False
+
+    def observe_events(self, events: List[Dict[str, Any]], tick: int, npc_context: Dict[str, Any]) -> None:
+        relevant: List[Dict[str, Any]] = []
+        for event in events or []:
+            if self._event_is_relevant(event, npc_context):
+                relevant.append(event)
+
+        self.memory.remember_many(relevant, tick=tick)
+        for event in relevant:
+            self.beliefs.update_from_event(event, npc_context=npc_context)
+            self.goal_engine.advance_from_event(event)
+
+        self.last_seen_tick = int(tick)
+
+    def refresh_goals(self, simulation_state: Dict[str, Any], npc_context: Dict[str, Any]) -> None:
+        generated = self.goal_engine.generate_goals(
+            npc_context=npc_context,
+            simulation_state=simulation_state,
+            belief_summary=self.beliefs.summarize(limit=8),
+            memory_summary=self.memory.summary(limit=5),
         )
-
-        # Build a prompt that asks the LLM to evaluate the plan
-        prompt = (
-            f"You are {self.npc_name} ({self.npc_role}).\n"
-            f"Personality: {personality_str}\n\n"
-            f"Current GOAP plan:\n"
-            f"  Goal: {plan.get('goal', 'unknown')}\n"
-            f"  Steps: {plan.get('steps', [])}\n"
-            f"  Priority: {plan.get('priority', 0.5)}\n\n"
-            f"World state summary: {world_state}\n\n"
-            f"Urgency level: {urgency:.2f}\n\n"
-            f"Respond with a JSON object containing:\n"
-            f"  - override (bool): Should this plan be overridden?\n"
-            f"  - override_action (str|null): Action to force instead.\n"
-            f"  - new_goal (str|null): Better goal to pursue.\n"
-            f"  - emotion (str|null): Current emotion (anger,fear,joy,sadness,surprise,trust,disgust,anticipation).\n"
-            f"  - risk (float 0-1): Risk tolerance.\n"
+        self.goal_engine.merge_goals(generated)
+
+    def decide(self, simulation_state: Dict[str, Any], npc_context: Dict[str, Any], tick: int) -> NPCDecision:
+        npc_context = npc_context or {}
+        top_goal = self.goal_engine.top_goal()
+        location_id = _safe_str(npc_context.get("location_id"))
+
+        if not top_goal:
+            decision = NPCDecision.fallback(
+                npc_id=self.npc_id,
+                tick=tick,
+                location_id=location_id,
+                reason="No active goals",
+            )
+            self.last_decision = decision.to_dict()
+            return decision
+
+        goal_type = _safe_str(top_goal.get("type"))
+        target_id = _safe_str(top_goal.get("target_id"))
+        reason = _safe_str(top_goal.get("reason"))
+        priority = float(top_goal.get("priority", 0.0) or 0.0)
+
+        mapping = {
+            "stabilize_location": ("stabilize", "stabilize", "location", "The NPC acts to restore order."),
+            "support_faction": ("support", "support", "faction", "The NPC rallies support for their faction."),
+            "retaliate": ("retaliate", "retaliate", "actor", "The NPC moves against a perceived enemy."),
+            "avoid_player": ("avoid", "avoid", "actor", "The NPC keeps their distance."),
+            "approach_player": ("negotiate", "negotiate", "actor", "The NPC cautiously opens contact."),
+            "observe": ("observe", "observe", "actor", "The NPC watches closely."),
+            "investigate": ("investigate", "investigate", "entity", "The NPC looks into suspicious developments."),
+        }
+        intent, action_type, target_kind, dialogue_hint = mapping.get(
+            goal_type,
+            ("wait", "wait", "", "The NPC waits and reassesses."),
         )
 
-        if self.llm_client:
-            try:
-                raw = self.llm_client.generate(prompt)
-                return self._parse_plan_evaluation(raw)
-            except Exception:
-                pass
-
-        # Fallback: no adjustment needed
-        return {
-            "override": False,
-            "override_action": None,
-            "new_goal": None,
-            "emotion": None,
-            "risk_tolerance": urgency * 0.5,
+        raw = {
+            "npc_id": self.npc_id,
+            "tick": int(tick),
+            "intent": intent,
+            "action_type": action_type,
+            "target_id": target_id,
+            "target_kind": target_kind,
+            "location_id": location_id,
+            "reason": reason,
+            "dialogue_hint": dialogue_hint,
+            "urgency": priority,
         }
+        validated = self.validator.validate(raw)
+        decision = NPCDecision.from_dict(validated)
+        self.last_decision = decision.to_dict()
+        return decision
 
-    def _parse_plan_evaluation(
-        self, raw_response: str
-    ) -> Dict[str, Any]:
-        """Parse an LLM plan evaluation response.
-
-        Args:
-            raw_response: Raw text from the LLM.
+    def apply_player_action_feedback(self, action_event: Dict[str, Any], npc_context: Dict[str, Any], tick: int) -> None:
+        if self._event_is_relevant(action_event, npc_context):
+            self.memory.remember(action_event, tick=tick, index=0)
+            self.beliefs.update_from_event(action_event, npc_context=npc_context)
 
-        Returns:
-            Parsed adjustment dict.
-        """
-        result: Dict[str, Any] = {
-            "override": False,
-            "override_action": None,
-            "new_goal": None,
-            "emotion": None,
-            "risk_tolerance": 0.5,
+    def build_narrator_context(self) -> Dict[str, Any]:
+        return {
+            "memory_summary": self.memory.summary(limit=5),
+            "belief_summary": self.beliefs.summarize(limit=8),
+            "active_goals": [dict(goal) for goal in self.goal_engine.goals],
+            "last_decision": dict(self.last_decision),
         }
-
-        # Very simple JSON-ish parsing (production should use proper JSON extraction)
-        text = raw_response.strip().strip("`").strip()
-        if text.startswith("json"):
-            text = text[4:].strip()
-
-        try:
-            import json
-            parsed = json.loads(text)
-            result["override"] = bool(parsed.get("override", False))
-            result["override_action"] = parsed.get("override_action")
-            result["new_goal"] = parsed.get("new_goal")
-            result["emotion"] = parsed.get("emotion")
-            result["risk_tolerance"] = float(parsed.get("risk", 0.5))
-        except (json.JSONDecodeError, ValueError, TypeError):
-            pass
-
-        return result
-
-    def reset(self) -> None:
-        """Reset all state."""
-        self.memory.clear()
-        self.goals.reset()
-        self.last_decision = None
-        self.last_tick = 0
-
-    def __repr__(self) -> str:
-        return (
-            f"NPCMind(id='{self.npc_id}', name='{self.npc_name}', "
-            f"role='{self.npc_role}', "
-            f"mem_events={len(self.memory)}, "
-            f"active_goals={len(self.goals.active_goals)})"
-        )
\ No newline at end of file
diff --git a/src/app/rpg/ai/llm_mind/npc_prompt_builder.py b/src/app/rpg/ai/llm_mind/npc_prompt_builder.py
new file mode 100644
index 0000000..535f69b
--- /dev/null
+++ b/src/app/rpg/ai/llm_mind/npc_prompt_builder.py
@@ -0,0 +1,22 @@
+from __future__ import annotations
+
+from typing import Any, Dict, List
+
+
+class NPCPromptBuilder:
+    def build_decision_prompt(
+        self,
+        npc_context: Dict[str, Any],
+        belief_summary: Dict[str, Dict[str, float]],
+        memory_summary: List[Dict[str, Any]],
+        goals: List[Dict[str, Any]],
+        simulation_state: Dict[str, Any],
+    ) -> str:
+        npc_name = str(npc_context.get("name") or npc_context.get("npc_id") or "Unknown NPC")
+        return (
+            f"NPC: {npc_name}\n"
+            f"Beliefs: {belief_summary}\n"
+            f"Memory: {memory_summary}\n"
+            f"Goals: {goals}\n"
+            f"Context keys: {sorted((simulation_state or {}).keys())}\n"
+        )
diff --git a/src/app/rpg/ai/llm_mind/npc_response_parser.py b/src/app/rpg/ai/llm_mind/npc_response_parser.py
new file mode 100644
index 0000000..f6c2a1b
--- /dev/null
+++ b/src/app/rpg/ai/llm_mind/npc_response_parser.py
@@ -0,0 +1,10 @@
+from __future__ import annotations
+
+from typing import Any, Dict
+
+
+class NPCResponseParser:
+    def parse_decision(self, payload: Any) -> Dict[str, Any]:
+        if isinstance(payload, dict):
+            return dict(payload)
+        return {}
diff --git a/src/app/rpg/ai/llm_mind/prompt_builder.py b/src/app/rpg/ai/llm_mind/prompt_builder.py
index f744c45..e617be4 100644
--- a/src/app/rpg/ai/llm_mind/prompt_builder.py
+++ b/src/app/rpg/ai/llm_mind/prompt_builder.py
@@ -1,187 +1,3 @@
-"""Prompt Builder with Hard Persona Lock.
+from .npc_prompt_builder import NPCPromptBuilder
 
-Patch 3: Hard Persona Lock
-- NPC identity (name, role) is hardcoded into prompt
-- Personality traits (aggression, honor, greed) are explicit
-- Behavior rules bind traits to expected actions
-- Prevents "villager talks like philosopher king" drift
-"""
-
-from __future__ import annotations
-
-from typing import Any, Dict, List, Optional
-
-VALID_INTENTS = [
-    "interact_with_npc",
-    "pursue_goal",
-    "react_to_event",
-    "idle",
-]
-
-
-def build_npc_prompt(context: Dict[str, Any]) -> str:
-    """Build a prompt with hard persona lock.
-
-    Patch 3: Identity and personality are explicitly stated
-    and bound to behavior rules to prevent drift.
-
-    Args:
-        context: Dict with npc, personality, memory, goals, world keys.
-
-    Returns:
-        Formatted prompt string for the LLM.
-    """
-    npc = context.get("npc", {})
-    personality = context.get("personality", {})
-    memory_summary = context.get("memory_summary", [])
-    goals = context.get("goals", [])
-    world = context.get("world", {})
-    recent_events = context.get("recent_events", [])
-    intent_priority = context.get("intent_priority", False)
-
-    lines: List[str] = []
-
-    # ---- IDENTITY (Patch 3: Hard lock) ----
-    lines.append("You are this NPC. You MUST stay consistent.")
-    lines.append("")
-    lines.append("IDENTITY:")
-    lines.append(f"Name: {npc.get('name', 'unknown')}")
-    lines.append(f"Role: {npc.get('role', 'unknown')}")
-    lines.append("")
-
-    # ---- PERSONALITY TRAITS (Patch 3) ----
-    lines.append("PERSONALITY TRAITS:")
-    lines.append(f"- Aggression: {personality.get('aggression', 0.5)}")
-    lines.append(f"- Honor: {personality.get('honor', 0.5)}")
-    lines.append(f"- Greed: {personality.get('greed', 0.5)}")
-    lines.append("")
-
-    # ---- BEHAVIOR RULES (Patch 3: Binding) ----
-    lines.append("Behavior Rules:")
-    lines.append("- High aggression -> prefer attack")
-    lines.append("- High honor -> avoid betrayal")
-    lines.append("- High greed -> prefer trade/reward")
-    lines.append("")
-
-    # ---- MEMORY ----
-    if memory_summary:
-        lines.append("RECENT MEMORIES:")
-        for m in memory_summary[:10]:
-            if isinstance(m, dict):
-                lines.append(
-                    f"- {m.get('type', '?')}: "
-                    f"{m.get('actor', '?')} -> {m.get('target', '?')}"
-                )
-            else:
-                lines.append(f"- {m}")
-        lines.append("")
-
-    # ---- ACTIVE GOALS ----
-    if goals:
-        lines.append("ACTIVE GOALS:")
-        for g in goals:
-            if isinstance(g, dict):
-                lines.append(
-                    f"- {g.get('type', '?')} (priority={g.get('priority', 0):.2f})"
-                )
-            else:
-                lines.append(f"- {g}")
-        lines.append("")
-
-    # ---- WORLD STATE ----
-    lines.append("WORLD:")
-    visible = (
-        world.get("visible_entities", [])
-        if isinstance(world, dict)
-        else world.get("entities", [])
-        if isinstance(world, dict)
-        else []
-    )
-    location = (
-        world.get("location", "unknown")
-        if isinstance(world, dict)
-        else "unknown"
-    )
-    lines.append(f"Location: {location}")
-    if visible:
-        lines.append("Visible entities:")
-        for v in visible[:10]:
-            if isinstance(v, dict):
-                lines.append(
-                    f"  - {v.get('name', v.get('id', '?'))} "
-                    f"(role={v.get('role', '?')})"
-                )
-            else:
-                lines.append(f"  - {v}")
-    lines.append("")
-
-    # ---- RECENT EVENTS ----
-    if recent_events:
-        lines.append("RECENT EVENTS:")
-        for e in recent_events[:5]:
-            if isinstance(e, dict):
-                lines.append(
-                    f"- {e.get('type', '?')}: "
-                    f"{e.get('actor', '?')} -> {e.get('target', '?')}"
-                )
-        lines.append("")
-
-    # ---- INTENT RULES (Patch 7) ----
-    if intent_priority:
-        lines.append("INTENT PRIORITY RULES:")
-        lines.append(
-            "- If another NPC is present and relevant, prioritize interact_with_npc"
-        )
-        lines.append("- Otherwise, pursue your highest-priority goal")
-        lines.append(
-            "- React to events if something significant just happened"
-        )
-        lines.append("- Fall back to idle if none of the above apply")
-        lines.append("")
-
-    # ---- OUTPUT FORMAT ----
-    lines.append("OUTPUT FORMAT:")
-    lines.append("Respond with a JSON object containing:")
-    lines.append("{")
-    lines.append('  "intent": "interact_with_npc|pursue_goal|react_to_event|idle",')
-    lines.append('  "target": "<npc_id or goal or event>",')
-    lines.append('  "action": "<action_type>",')
-    lines.append('  "dialogue": "<what you say>",')
-    lines.append('  "emotion": "<happy|angry|neutral|fearful|suspicious>"')
-    lines.append("}")
-
-    return "\n".join(lines)
-
-
-def build_context(
-    npc: Dict[str, Any],
-    personality: Dict[str, float],
-    memory: Optional[List[Dict[str, Any]]] = None,
-    goals: Optional[List[Dict[str, Any]]] = None,
-    world: Optional[Dict[str, Any]] = None,
-    recent_events: Optional[List[Dict[str, Any]]] = None,
-    intent_priority: bool = True,
-) -> Dict[str, Any]:
-    """Build a prompt context dict.
-
-    Args:
-        npc: NPC identity (name, role).
-        personality: NPC traits (aggression, honor, greed).
-        memory: Memory summary list.
-        goals: Active goals list.
-        world: World state dict.
-        recent_events: Recent events list.
-        intent_priority: Whether to include intent priority rules.
-
-    Returns:
-        Context dict ready for prompt generation.
-    """
-    return {
-        "npc": npc,
-        "personality": personality,
-        "memory_summary": memory or [],
-        "goals": goals or [],
-        "world": world or {},
-        "recent_events": recent_events or [],
-        "intent_priority": intent_priority,
-    }
\ No newline at end of file
+__all__ = ["NPCPromptBuilder"]
diff --git a/src/app/rpg/ai/llm_mind/response_parser.py b/src/app/rpg/ai/llm_mind/response_parser.py
index 5ceabe4..0829c48 100644
--- a/src/app/rpg/ai/llm_mind/response_parser.py
+++ b/src/app/rpg/ai/llm_mind/response_parser.py
@@ -1,231 +1,3 @@
-"""Robust JSON Response Parser.
+from .npc_response_parser import NPCResponseParser
 
-Patch 4: Handles LLM JSON fragility
-- Extracts JSON block from messy LLM output
-- Handles trailing commas, comments, text before/after JSON
-- Returns a safe NPCDecision on parse failure
-"""
-
-from __future__ import annotations
-
-import json
-import re
-from dataclasses import dataclass
-from typing import Any, Dict, Optional
-
-
-@dataclass
-class NPCDecision:
-    """Represents a parsed NPC decision.
-
-    Attributes:
-        intent: Action intent type.
-        target: Target of the action.
-        action: Specific action to take.
-        dialogue: What the NPC says.
-        emotion: Emotional state.
-        raw: Raw parsed dict or None.
-    """
-
-    intent: str = "idle"
-    target: str = ""
-    action: str = ""
-    dialogue: str = ""
-    emotion: str = "neutral"
-    raw: Optional[Dict[str, Any]] = None
-
-    @classmethod
-    def fallback(cls) -> "NPCDecision":
-        """Return a safe fallback decision.
-
-        Returns:
-            Default idle decision.
-        """
-        return cls(
-            intent="idle",
-            target="",
-            action="wait",
-            dialogue="...",
-            emotion="neutral",
-        )
-
-    @classmethod
-    def from_dict(cls, d: Dict[str, Any]) -> "NPCDecision":
-        """Create a decision from a dict.
-
-        Args:
-            d: Dict with decision fields.
-
-        Returns:
-            NPCDecision instance.
-        """
-        return cls(
-            intent=d.get("intent", "idle"),
-            target=d.get("target", ""),
-            action=d.get("action", ""),
-            dialogue=d.get("dialogue", ""),
-            emotion=d.get("emotion", "neutral"),
-            raw=d,
-        )
-
-    def to_dict(self) -> Dict[str, Any]:
-        """Return dict representation.
-
-        Returns:
-            Dict with decision fields.
-        """
-        return {
-            "intent": self.intent,
-            "target": self.target,
-            "action": self.action,
-            "dialogue": self.dialogue,
-            "emotion": self.emotion,
-        }
-
-    def __repr__(self) -> str:
-        return (
-            f"NPCDecision(intent='{self.intent}', "
-            f"target='{self.target}', action='{self.action}', "
-            f"emotion='{self.emotion}')"
-        )
-
-
-VALID_INTENTS = frozenset({
-    "interact_with_npc",
-    "pursue_goal",
-    "react_to_event",
-    "idle",
-    "attack",
-    "trade",
-    "flee",
-    "help",
-    "talk",
-})
-
-VALID_EMOTIONS = frozenset({
-    "happy",
-    "angry",
-    "neutral",
-    "fearful",
-    "suspicious",
-    "sad",
-    "excited",
-    "calm",
-})
-
-
-class NPCResponseParser:
-    """Robust JSON parser for LLM NPC responses.
-
-    Patch 4: Extracts JSON from messy output, fixes trailing commas,
-    and returns a safe fallback on failure.
-    """
-
-    def parse(self, raw: str) -> NPCDecision:
-        """Parse raw LLM response into an NPCDecision.
-
-        Args:
-            raw: Raw response string.
-
-        Returns:
-            Parsed NPCDecision or fallback.
-        """
-        if not raw or not raw.strip():
-            return NPCDecision.fallback()
-
-        # Step 1: Extract JSON-like block
-        json_str = self._extract_json(raw)
-        if not json_str:
-            return NPCDecision.fallback()
-
-        # Step 2: Fix common LLM JSON issues
-        json_str = self._fix_json(json_str)
-
-        # Step 3: Parse
-        try:
-            d = json.loads(json_str)
-        except json.JSONDecodeError:
-            return NPCDecision.fallback()
-
-        if not isinstance(d, dict):
-            return NPCDecision.fallback()
-
-        # Step 4: Validate and normalize
-        return self._normalize(d)
-
-    def _extract_json(self, raw: str) -> Optional[str]:
-        """Extract the first JSON-like block from text.
-
-        Handles:
-        - Text before/after JSON
-        - Markdown code blocks
-        - Multiple JSON objects (takes first)
-
-        Args:
-            raw: Raw response text.
-
-        Returns:
-            JSON string or None.
-        """
-        # Try markdown code block first
-        code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
-        if code_match:
-            return code_match.group(1)
-
-        # Try to find first {...} block
-        match = re.search(r"\{.*?\}", raw, re.DOTALL)
-        if match:
-            return match.group(0)
-
-        return None
-
-    def _fix_json(self, json_str: str) -> str:
-        """Fix common LLM JSON problems.
-
-        Fixes:
-        - Trailing commas in objects and arrays
-        - Single-line comments (// and /* */)
-        - Unquoted keys
-
-        Args:
-            json_str: Potentially broken JSON string.
-
-        Returns:
-            Fixed JSON string.
-        """
-        # Remove single-line comments
-        json_str = re.sub(r"//[^\n]*", "", json_str)
-        # Remove multi-line comments
-        json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
-        # Remove trailing commas before } or ]
-        json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
-        return json_str
-
-    def _normalize(self, d: Dict[str, Any]) -> NPCDecision:
-        """Normalize parsed dict into a valid NPCDecision.
-
-        Validates intent and emotion values,
-        fills in defaults for missing keys.
-
-        Args:
-            d: Parsed dict from LLM.
-
-        Returns:
-            Validated NPCDecision.
-        """
-        intent = d.get("intent", "idle")
-        if intent not in VALID_INTENTS:
-            intent = "idle"
-
-        emotion = d.get("emotion", "neutral")
-        if emotion not in VALID_EMOTIONS:
-            emotion = "neutral"
-
-        return NPCDecision(
-            intent=intent,
-            target=str(d.get("target", "")),
-            action=str(d.get("action", "")),
-            dialogue=str(d.get("dialogue", "")),
-            emotion=emotion,
-            raw=d,
-        )
\ No newline at end of file
+__all__ = ["NPCResponseParser"]
diff --git a/src/app/rpg/ai/llm_mind/validator.py b/src/app/rpg/ai/llm_mind/validator.py
index ae71b61..42038be 100644
--- a/src/app/rpg/ai/llm_mind/validator.py
+++ b/src/app/rpg/ai/llm_mind/validator.py
@@ -1 +1,3 @@
-"""Validator."""
+from .npc_decision_validator import NPCDecisionValidator
+
+__all__ = ["NPCDecisionValidator"]
diff --git a/src/app/rpg/ai/world_scene_narrator.py b/src/app/rpg/ai/world_scene_narrator.py
index 6111d95..a6f127c 100644
--- a/src/app/rpg/ai/world_scene_narrator.py
+++ b/src/app/rpg/ai/world_scene_narrator.py
@@ -23,6 +23,34 @@ from typing import Any, Dict, List, Optional
 logger = logging.getLogger(__name__)
 
 
+# ---------------------------------------------------------------------------
+# Phase 6 — NPC mind context helpers
+# ---------------------------------------------------------------------------
+
+def _safe_str_p6(value):
+    if value is None:
+        return ""
+    return str(value)
+
+
+def _attach_npc_mind_context(actor, simulation_state):
+    """Attach Phase 6 NPC mind context to an actor dict."""
+    actor = dict(actor or {})
+    simulation_state = simulation_state or {}
+
+    npc_id = _safe_str_p6(actor.get("id"))
+    npc_minds = simulation_state.get("npc_minds") or {}
+    mind = npc_minds.get(npc_id) or {}
+
+    if isinstance(mind, dict):
+        actor["memory_summary"] = ((mind.get("memory") or {}).get("entries") or [])[:5]
+        actor["belief_summary"] = ((mind.get("beliefs") or {}).get("beliefs") or {})
+        actor["active_goals"] = ((mind.get("goals") or {}).get("goals") or [])[:5]
+        actor["last_decision"] = mind.get("last_decision") or {}
+
+    return actor
+
+
 # ---------------------------------------------------------------------------
 # Data models
 # ---------------------------------------------------------------------------
@@ -142,9 +170,12 @@ def build_npc_reaction_prompt(
     scene_title = scene.get("title", "Unknown Scene")
 
     # Phase 5.1: Inject NPC state (memory, beliefs, relationships)
+    # Phase 6: Enhanced with deterministic mind context
     npc_memory = npc.get("memory_summary", "")
-    npc_beliefs = npc.get("beliefs", {})
+    npc_beliefs = npc.get("beliefs", npc.get("belief_summary", {}))
     npc_relationships = npc.get("relationships", {})
+    npc_active_goals = npc.get("active_goals", [])
+    npc_last_decision = npc.get("last_decision", {})
 
     personality_info = f"Personality: {npc_personality}" if npc_personality else ""
     goals_info = f"Goals: {npc_goals}" if npc_goals else ""
@@ -152,6 +183,8 @@ def build_npc_reaction_prompt(
     memory_info = f"Recent memory: {npc_memory}" if npc_memory else ""
     beliefs_info = f"Current beliefs: {', '.join(str(v) for v in npc_beliefs.values())}" if npc_beliefs else ""
     relationships_info = f"Relationships: {', '.join(f'{k}: {v}' for k, v in npc_relationships.items())}" if npc_relationships else ""
+    goals_list_info = f"Active goals: {npc_active_goals}" if npc_active_goals else ""
+    last_decision_info = f"Last decision: {npc_last_decision}" if npc_last_decision else ""
 
     prompt = f"""You are generating NPC reactions for an RPG.
 
@@ -162,6 +195,8 @@ Character: {npc_name}
 {memory_info}
 {beliefs_info}
 {relationships_info}
+{goals_list_info}
+{last_decision_info}
 
 Scene: {scene_title}
 
@@ -170,7 +205,11 @@ Narrative:
 
 === INSTRUCTIONS ===
 Describe {npc_name}'s internal reaction to what just happened.
-Consider their memory, beliefs, and relationships when forming their reaction.
+- Use the NPC's active goals to shape what they want right now.
+- Use belief_summary about the player to determine tone.
+- Use memory_summary to maintain continuity.
+- Use last_decision so reactions align with recent intent.
+- Do not contradict the provided structured state.
 Then provide a short line of dialogue they might say.
 Specify their emotional state (one of: calm, tense, angry, fearful, curious, excited, neutral).
 Specify their immediate intent (one of: observe, act, confront, flee, negotiate, wait).
diff --git a/src/app/rpg/creator/world_player_actions.py b/src/app/rpg/creator/world_player_actions.py
index 63fab95..0215fb4 100644
--- a/src/app/rpg/creator/world_player_actions.py
+++ b/src/app/rpg/creator/world_player_actions.py
@@ -42,11 +42,44 @@ def _safe_list(value: Any) -> list[Any]:
     return []
 
 
+def _safe_str(value: Any) -> str:
+    """Return *value* as a string."""
+    if value is None:
+        return ""
+    return str(value)
+
+
 def _cap(value: int, lo: int = 0, hi: int = 5) -> int:
     """Clamp *value* to [lo, hi]."""
     return max(lo, min(hi, value))
 
 
+def _infer_affected_npc_ids(
+    simulation_state: dict[str, Any],
+    location_id: str = "",
+    faction_id: str = "",
+    target_id: str = "",
+) -> list[str]:
+    """Infer NPC IDs affected by an action based on npc_index."""
+    simulation_state = simulation_state or {}
+    npc_index = simulation_state.get("npc_index") or {}
+    affected = []
+
+    for npc_id, npc in sorted(npc_index.items()):
+        npc_loc = _safe_str(npc.get("location_id"))
+        npc_faction = _safe_str(npc.get("faction_id"))
+        if location_id and npc_loc == location_id:
+            affected.append(npc_id)
+            continue
+        if faction_id and npc_faction == faction_id:
+            affected.append(npc_id)
+            continue
+        if target_id and npc_id == target_id:
+            affected.append(npc_id)
+
+    return sorted(set(affected))
+
+
 # ---------------------------------------------------------------------------
 # Action types
 # ---------------------------------------------------------------------------
@@ -145,9 +178,18 @@ def apply_player_action(
             "type": "player_intervention",
             "origin": "player_action",
             "action_type": action_type,
+            "actor": "player",
             "target_id": target_id,
+            "target_kind": "thread",
+            "location_id": "",
+            "faction_id": "",
+            "affected_npc_ids": _infer_affected_npc_ids(
+                simulation_state=state,
+                target_id=target_id,
+            ),
             "summary": f"Player intervened in thread '{target_id}' (pressure {old_pressure} → {new_pressure})",
             "severity": "positive",
+            "salience": 0.8,
         })
         action_applied = True
 
@@ -171,9 +213,18 @@ def apply_player_action(
             "type": "player_support",
             "origin": "player_action",
             "action_type": action_type,
+            "actor": "player",
             "target_id": target_id,
+            "target_kind": "faction",
+            "location_id": "",
+            "faction_id": target_id,
+            "affected_npc_ids": _infer_affected_npc_ids(
+                simulation_state=state,
+                faction_id=target_id,
+            ),
             "summary": f"Player supported faction '{target_id}' (pressure {old_pressure} → {new_pressure})",
             "severity": "positive",
+            "salience": 0.8,
         })
         action_applied = True
 
@@ -209,10 +260,19 @@ def apply_player_action(
             "type": "player_escalation",
             "origin": "player_action",
             "action_type": action_type,
+            "actor": "player",
             "target_id": target_id,
+            "target_kind": "thread",
+            "location_id": "",
+            "faction_id": "",
             "related_factions": related_factions,
+            "affected_npc_ids": _infer_affected_npc_ids(
+                simulation_state=state,
+                target_id=target_id,
+            ),
             "summary": f"Player escalated conflict in thread '{target_id}' (pressure {old_pressure} → {new_pressure})",
             "severity": "negative",
+            "salience": 0.9,
         })
         action_applied = True
 
diff --git a/src/app/rpg/creator/world_scene_generator.py b/src/app/rpg/creator/world_scene_generator.py
index 6eb9373..f5136a4 100644
--- a/src/app/rpg/creator/world_scene_generator.py
+++ b/src/app/rpg/creator/world_scene_generator.py
@@ -53,6 +53,35 @@ def _safe_str(v: Any, default: str = "") -> str:
     return str(v)
 
 
+def _collect_scene_actors(source_id, simulation_state, max_actors=4):
+    """Collect NPC actors relevant to a scene source from Phase 6 state."""
+    simulation_state = simulation_state or {}
+    npc_index = simulation_state.get("npc_index") or {}
+    npc_minds = simulation_state.get("npc_minds") or {}
+
+    actors = []
+    for npc_id, npc in sorted(npc_index.items()):
+        npc_location_id = _safe_str(npc.get("location_id"))
+        npc_faction_id = _safe_str(npc.get("faction_id"))
+
+        if source_id and (source_id == npc_location_id or source_id == npc_faction_id or source_id == npc_id):
+            actor = {
+                "id": npc_id,
+                "name": _safe_str(npc.get("name")) or npc_id,
+                "role": _safe_str(npc.get("role")),
+                "faction_id": npc_faction_id,
+                "location_id": npc_location_id,
+            }
+            mind = npc_minds.get(npc_id) or {}
+            if isinstance(mind, dict):
+                actor["mind_context"] = {
+                    "last_decision": mind.get("last_decision") or {},
+                }
+            actors.append(actor)
+
+    return actors[:max_actors]
+
+
 def _build_scene_id(source_id: str, suffix: str) -> str:
     """Build a stable scene id from source and suffix.
 
@@ -433,6 +462,42 @@ def generate_scenes_from_simulation(
     extra = generate_extra_scenes(state, max_scenes=max_scenes, already=len(scenes))
     scenes.extend(extra)
 
+    # Phase 6: Enrich scenes with NPC actors from simulation state
+    for scene in scenes:
+        source_id = scene.get("source_incident_id") or ""
+        # Also try to match by scene actors (which are often source_ids)
+        if not source_id and scene.get("actors"):
+            source_id = _safe_str(scene["actors"][0]) if scene["actors"] else ""
+
+        enriched_actors = list(scene.get("actors") or [])
+        enriched_actors.extend(_collect_scene_actors(
+            source_id=source_id,
+            simulation_state=state,
+            max_actors=4,
+        ))
+
+        deduped = []
+        seen_actor_ids = set()
+        for actor in enriched_actors:
+            if isinstance(actor, dict):
+                actor_id = _safe_str(actor.get("id"))
+            else:
+                actor_id = _safe_str(actor)
+                actor = {"id": actor_id, "name": actor_id}
+
+            if not actor_id or actor_id in seen_actor_ids:
+                continue
+            seen_actor_ids.add(actor_id)
+            deduped.append(actor)
+
+        scene["actors"] = deduped[:6]
+        scene["primary_npc_ids"] = [
+            a["id"]
+            for a in deduped
+            if isinstance(a, dict) and _safe_str(a.get("id"))
+            and (state.get("npc_index") or {}).get(_safe_str(a.get("id")))
+        ][:4]
+
     return scenes[:max_scenes]
 
 
diff --git a/src/app/rpg/creator/world_simulation.py b/src/app/rpg/creator/world_simulation.py
index 01aa226..18095fa 100644
--- a/src/app/rpg/creator/world_simulation.py
+++ b/src/app/rpg/creator/world_simulation.py
@@ -43,6 +43,7 @@ from .world_incidents import (
     merge_incidents,
     spawn_incidents_from_state_diff,
 )
+from app.rpg.ai.llm_mind import NPCMind
 
 
 # ---------------------------------------------------------------------------
@@ -53,6 +54,101 @@ MAX_HISTORY = 20
 PRESSURE_CAP = 5
 
 
+# ---------------------------------------------------------------------------
+# Phase 6 — NPC mind helpers
+# ---------------------------------------------------------------------------
+
+
+def _safe_str_p6(value):
+    if value is None:
+        return ""
+    return str(value)
+
+
+def _iter_npc_definitions(setup_payload):
+    """Best-effort extractor for NPC definitions from creator setup."""
+    setup_payload = setup_payload or {}
+
+    direct = setup_payload.get("npcs")
+    if isinstance(direct, list):
+        for item in direct:
+            if isinstance(item, dict):
+                yield item
+
+    # Also check npc_seeds (the standard key in this codebase)
+    seeds = setup_payload.get("npc_seeds")
+    if isinstance(seeds, list):
+        for item in seeds:
+            if isinstance(item, dict):
+                yield item
+
+    for section_key in ("world", "actors", "entities", "cast"):
+        section = setup_payload.get(section_key)
+        if isinstance(section, dict):
+            npcs = section.get("npcs")
+            if isinstance(npcs, list):
+                for item in npcs:
+                    if isinstance(item, dict):
+                        yield item
+
+
+def _build_npc_index(setup_payload):
+    npc_index = {}
+    for item in _iter_npc_definitions(setup_payload):
+        npc_id = _safe_str_p6(item.get("id") or item.get("npc_id"))
+        if not npc_id:
+            continue
+        npc_index[npc_id] = {
+            "npc_id": npc_id,
+            "name": _safe_str_p6(item.get("name")) or npc_id,
+            "role": _safe_str_p6(item.get("role")),
+            "faction_id": _safe_str_p6(item.get("faction_id")),
+            "location_id": _safe_str_p6(item.get("location_id")),
+        }
+    return dict(sorted(npc_index.items()))
+
+
+def _load_npc_minds(simulation_state, npc_index):
+    simulation_state = simulation_state or {}
+    raw = simulation_state.get("npc_minds") or {}
+    minds = {}
+    for npc_id, npc_ctx in sorted(npc_index.items()):
+        if npc_id in raw and isinstance(raw[npc_id], dict):
+            minds[npc_id] = NPCMind.from_dict(raw[npc_id])
+        else:
+            minds[npc_id] = NPCMind(npc_id=npc_id)
+    return minds
+
+
+def _decision_to_event(decision_dict, npc_context, tick):
+    decision_dict = decision_dict or {}
+    npc_context = npc_context or {}
+
+    npc_id = _safe_str_p6(decision_dict.get("npc_id"))
+    action_type = _safe_str_p6(decision_dict.get("action_type"))
+    target_id = _safe_str_p6(decision_dict.get("target_id"))
+    target_kind = _safe_str_p6(decision_dict.get("target_kind"))
+    location_id = _safe_str_p6(decision_dict.get("location_id")) or _safe_str_p6(npc_context.get("location_id"))
+    urgency = float(decision_dict.get("urgency", 0.0) or 0.0)
+
+    if action_type in {"wait", ""}:
+        return None
+
+    return {
+        "event_id": f"npc_event:{tick}:{npc_id}:{action_type}:{target_id or 'none'}",
+        "tick": int(tick),
+        "type": action_type,
+        "actor": npc_id,
+        "target_id": target_id,
+        "target_kind": target_kind,
+        "location_id": location_id,
+        "faction_id": _safe_str_p6(npc_context.get("faction_id")),
+        "summary": _safe_str_p6(decision_dict.get("reason")) or f"{npc_id} chooses to {action_type}",
+        "salience": min(max(urgency, 0.2), 1.0),
+        "source": "npc_mind",
+    }
+
+
 # ---------------------------------------------------------------------------
 # Internal helpers
 # ---------------------------------------------------------------------------
@@ -486,6 +582,61 @@ def step_simulation_state(setup_payload: dict[str, Any]) -> dict[str, Any]:
     history_state["events"] = events
     history_state["consequences"] = consequences
 
+    # --- Phase 6: NPC Mind Integration ---
+    npc_index = _build_npc_index(setup)
+    npc_minds = _load_npc_minds(current, npc_index)
+
+    observed_events = []
+    for bucket_name in ("events", "consequences", "incidents"):
+        bucket = history_state.get(bucket_name) or []
+        if isinstance(bucket, list):
+            for item in bucket:
+                if isinstance(item, dict):
+                    observed_events.append(item)
+
+    new_npc_decisions = []
+    new_npc_events = []
+
+    for npc_id, mind in sorted(npc_minds.items()):
+        npc_context = dict(npc_index.get(npc_id) or {"npc_id": npc_id})
+        mind.observe_events(observed_events, tick=next_tick, npc_context=npc_context)
+        mind.refresh_goals(simulation_state=history_state, npc_context=npc_context)
+        decision = mind.decide(simulation_state=history_state, npc_context=npc_context, tick=next_tick)
+        decision_dict = decision.to_dict()
+        new_npc_decisions.append(decision_dict)
+
+        npc_event = _decision_to_event(decision_dict, npc_context=npc_context, tick=next_tick)
+        if npc_event is not None:
+            new_npc_events.append(npc_event)
+
+    new_npc_decisions = sorted(
+        new_npc_decisions,
+        key=lambda item: (
+            str(item.get("npc_id") or ""),
+            str(item.get("action_type") or ""),
+            str(item.get("target_id") or ""),
+        ),
+    )[:12]
+
+    new_npc_events = sorted(
+        new_npc_events,
+        key=lambda item: (
+            str(item.get("actor") or ""),
+            str(item.get("type") or ""),
+            str(item.get("target_id") or ""),
+        ),
+    )[:12]
+
+    history_state["npc_index"] = npc_index
+    history_state["npc_minds"] = {
+        npc_id: mind.to_dict()
+        for npc_id, mind in sorted(npc_minds.items())
+    }
+    history_state["npc_decisions"] = list(new_npc_decisions)
+
+    existing_events = history_state.get("events") or []
+    history_state["events"] = list(existing_events) + list(new_npc_events)
+
     # Write back into setup copy (final state with effects applied)
     meta["simulation_state"] = history_state
     setup["metadata"] = meta
```
