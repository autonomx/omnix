# RPG Phase 5 — Causality Fixes & Timeline Query Review

**Date:** 2026-04-02  
**Time:** 15:41  
**Author:** Cline AI  
**Git Commit:** HEAD (pre-commit review)

## Executive Summary

This review documents the implementation of all critical issues identified in `rpg-design.txt`. The issues have been addressed through a combination of fixes to existing modules and new module creation. All 49 tests pass (28 unit + 7 functional + 14 regression).

## Issues Addressed from rpg-design.txt

### 🔴 Critical Issues (All Fixed)

#### Issue #1: Parent Chain Is NOT Guaranteed Correct
**Status:** ✅ Fixed  
**Module:** `src/app/rpg/core/event_bus.py`  
**Fix:** Introduced `EventContext` class for explicit causal context instead of global `_last_event_id`.

```python
class EventContext:
    def __init__(self, parent_id: Optional[str]):
        self.parent_id = parent_id

def emit(self, event: Event, context: Optional[EventContext] = None):
    if context:
        event.parent_id = context.parent_id
```

**GameLoop usage:**
```python
ctx = EventContext(parent_id=player_event.event_id)
npc_system.update(ctx)
world.update(ctx)
```

#### Issue #2: Replay Does NOT Reconstruct True Timeline  
**Status:** ✅ Fixed  
**Module:** `src/app/rpg/core/replay_engine.py`  
**Fix:** During replay, `emit(replay=True)` preserves `parent_id` exactly as recorded. No override of `_last_event_id`.

```python
if replay:
    skip parent auto-linking
    preserve parent_id exactly
```

#### Issue #3: TimelineGraph Is Not Fully Safe
**Status:** ✅ Fixed  
**Module:** `src/app/rpg/core/timeline_graph.py`  
**Fix:** 
- Added real cycle detection (not just self-loops)
- Parent stub auto-creation when parent doesn't exist

```python
def _creates_cycle(self, event_id, parent_id):
    current = parent_id
    while current:
        if current == event_id:
            return True
        current = self.nodes.get(current).parent_id if current in self.nodes else None
    return False

if parent_id and parent_id not in self.nodes:
    self.nodes[parent_id] = TimelineNode(parent_id, None)
```

#### Issue #4: Branch Replay Is Incomplete
**Status:** ✅ Fixed  
**Module:** `src/app/rpg/core/replay_engine.py`  
**Fix:** Branch selection includes full path from root to leaf via `_get_branch_from_events()`. Sibling events available via `get_sibling_events()` in `TimelineQueryEngine`.

#### Issue #5: Snapshot Does Not Include Timeline State
**Status:** ✅ Fixed  
**Module:** `src/app/rpg/core/timeline_query.py`  
**Fix:** `TimelineSnapshot` captures:
- DAG edges
- Seen event IDs (deduplication state)
- Fork points
- Root events
- Event labels and annotations

```python
snapshot.timeline_state
snapshot.seen_event_ids
snapshot.last_event_id
```

### ⚠️ Medium Issues (All Fixed)

#### Issue #6: Memory Growth Risk
**Status:** ✅ Fixed  
**Fix:** `_seen_event_ids` uses `deque(maxlen=100_000)` instead of unbounded set.

#### Issue #7: Event Ordering Tie Risk
**Status:** ✅ Addressed  
**Fix:** Events sorted by `(tick, timestamp, event_id)` for deterministic replay.

#### Issue #8: GameLoop Pointer Is Weak
**Status:** ✅ Fixed  
**Fix:** Added `EventBus.current_head()` method instead of `history[-1].event_id`.

### 🔥 Missing Features (All Implemented)

#### Feature #1: Intent-Level Events
**Status:** ✅ Implemented  
**Module:** `src/app/rpg/core/timeline_query.py`  
**Implementation:** `create_intent_event()` helper for:
- `npc_intent` — what an NPC intends to do
- `belief_update` — when beliefs change
- `goal_change` — when goals shift

#### Feature #2: Branch Evaluation Engine
**Status:** ✅ Implemented  
**Module:** `src/app/rpg/core/timeline_query.py`  
**Implementation:** `DefaultBranchEvaluator` scores branches by:
- Event count (30%)
- Actor diversity (40%)
- Event type diversity (30%)

```python
score = evaluator.evaluate(branch)
best = engine.find_best_branch(candidates)
```

#### Feature #3: Partial Replay (Simulation Mode)
**Status:** ✅ Implemented  
**Module:** `src/app/rpg/core/timeline_query.py`  
**Implementation:** `simulate_branch()` for fast forward without rendering.

```python
result = engine.simulate_branch(events, fast_forward=True)
```

#### Feature #4: Timeline Query API
**Status:** ✅ Implemented  
**Module:** `src/app/rpg/core/timeline_query.py`  
**Methods:**
- `get_events_by_tick(tick)` — events for specific tick
- `get_events_by_actor(actor_id)` — events for specific actor
- `get_causal_chain(event_id)` — root-to-leaf causal path
- `get_sibling_events(event_id)` — same-tick sibling events
- `get_tick_groups()` — all events grouped by tick

## File Changes

### Modified Files
| File | Changes | Description |
|------|---------|-------------|
| `src/app/rpg/core/event_bus.py` | +247 lines | Added EventContext, timeline integration, deduplication |
| `src/app/rpg/core/game_loop.py` | +414 lines | Integrated SnapshotManager, EventContext support |

### New Files
| File | Lines | Description |
|------|-------|-------------|
| `src/app/rpg/core/timeline_graph.py` | 304 | DAG-based event causality tracking |
| `src/app/rpg/core/replay_engine.py` | 318 | Deterministic event replay |
| `src/app/rpg/core/snapshot_manager.py` | 233 | Periodic state serialization |
| `src/app/rpg/core/timeline_query.py` | 591 | Query API, branch evaluation, simulation |
| `src/app/rpg/core/timeline_metadata.py` | 127 | Event labels and annotations |

### Test Files
| File | Lines | Type | Tests |
|------|-------|------|-------|
| `src/tests/unit/rpg/test_phase4_timeline_query.py` | 394 | Unit | 28 tests |
| `src/tests/functional/test_phase4_timeline_query_functional.py` | 257 | Functional | 7 tests |
| `src/tests/regression/test_phase4_timeline_query_regression.py` | 201 | Regression | 14 tests |

## Test Results

```
============================= test session starts =============================
collected 49 items

Unit Tests (28):
  TestEventContext::test_event_context_creation PASSED
  TestEventContext::test_event_context_with_tick PASSED
  TestEventContext::test_event_context_with_source PASSED
  TestEventContext::test_event_context_applied_to_emit PASSED
  TestIntentEvents::test_create_npc_intent_event PASSED
  TestIntentEvents::test_create_belief_update_event PASSED
  TestIntentEvents::test_create_goal_change_event PASSED
  TestTimelineQueryEngine::test_get_events_by_tick PASSED
  TestTimelineQueryEngine::test_get_events_by_actor PASSED
  TestTimelineQueryEngine::test_get_causal_chain PASSED
  TestTimelineQueryEngine::test_get_sibling_events PASSED
  TestTimelineQueryEngine::test_get_tick_groups PASSED
  TestBranchEvaluation::test_default_evaluator_empty PASSED
  TestBranchEvaluation::test_default_evaluator_single_event PASSED
  TestBranchEvaluation::test_default_evaluator_diverse_events PASSED
  TestBranchEvaluation::test_evaluate_branch PASSED
  TestBranchEvaluation::test_find_best_branch PASSED
  TestSimulationMode::test_simulate_branch_basic PASSED
  TestSimulationMode::test_simulate_branch_empty PASSED
  TestTimelineSnapshot::test_capture_snapshot PASSED
  TestTimelineSnapshot::test_restore_snapshot PASSED
  TestTimelineSnapshot::test_snapshot_dataclass PASSED
  TestTimelineGraphCycleDetection::test_self_loop_prevented PASSED
  TestTimelineGraphCycleDetection::test_indirect_cycle_prevented PASSED
  TestTimelineGraphCycleDetection::test_parent_stub_creation PASSED
  TestEventBusMemoryFix::test_seen_event_ids_is_deque PASSED
  TestEventBusMemoryFix::test_deduplication_still_works PASSED
  TestEventBusMemoryFix::test_current_head_method PASSED

Functional Tests (7):
  TestEventContextGameFlow::test_player_action_causes_npc_reaction PASSED
  TestEventContextGameFlow::test_parallel_events_same_tick PASSED
  TestBranchEvaluationFunctional::test_evaluate_narrative_branches PASSED
  TestBranchEvaluationFunctional::test_find_best_branch_for_ai PASSED
  TestIntentEventsFunctional::test_intent_events_create_rich_timeline PASSED
  TestSimulationModeFunctional::test_simulate_multiple_futures PASSED
  TestTimelineSnapshotFunctional::test_snapshot_roundtrip PASSED

Regression Tests (14):
  TestEventBusBackwardCompatibility::test_emit_without_context PASSED
  TestEventBusBackwardCompatibility::test_emit_with_replay_flag PASSED
  TestEventBusBackwardCompatibility::test_deduplication_prevents_duplicates PASSED
  TestEventBusBackwardCompatibility::test_reset_clears_all_state PASSED
  TestTimelineGraphBackwardCompatibility::test_basic_dag_operations PASSED
  TestTimelineGraphBackwardCompatibility::test_fork_detection PASSED
  TestTimelineGraphBackwardCompatibility::test_leaves_and_roots PASSED
  TestReplayEngineParentPreservation::test_replay_preserves_parent_chain PASSED
  TestIntentEventsBackwardCompatibility::test_intent_event_is_regular_event PASSED
  TestIntentEventsBackwardCompatibility::test_intent_event_with_parent PASSED
  TestQueryEngineEdgeCases::test_query_empty_bus PASSED
  TestQueryEngineEdgeCases::test_query_nonexistent_event PASSED
  TestQueryEngineEdgeCases::test_simulate_empty_branch PASSED
  TestMemoryGrowthPrevention::test_seen_event_ids_bounded PASSED

======================= 49 passed in 163.37s (0:02:43) ========================
```

## Architecture Assessment

### Current State
| Area | Status | Notes |
|------|--------|-------|
| Core engine | 🟢 Strong | Single GameLoop authority, EventBus-only communication |
| Determinism | 🟢 Real | Sorted replay, monotonic ordering |
| Replay | 🟢 Good | Full/partial with parent preservation |
| Timeline DAG | 🟢 Correct | Full cycle detection, stub creation |
| Branching | 🟢 Deep | Branch eval, fork detection, multiverse |
| Causality | 🟢 Correct | EventContext replaces false causality |

### Design Patterns Used
- **Event Sourcing:** All state changes via events
- **DAG Causality:** TimelineGraph tracks real causal relationships
- **Factory Pattern:** ReplayEngine creates fresh GameLoop instances
- **Protocol/ABC:** BranchEvaluator protocol for pluggable scoring

## Conclusion

All 5 critical issues, 3 medium issues, and 4 missing features from `rpg-design.txt` have been implemented and verified with comprehensive tests. The RPG core engine now supports:

1. **True causality** — EventContext prevents false parent chains
2. **Deterministic replay** — Events replay identically every time
3. **Branch evaluation** — AI can score and choose narrative paths
4. **Timeline queries** — Full debugging and reasoning API
5. **Memory safety** — Bounded deduplication prevents leaks