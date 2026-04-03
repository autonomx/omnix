# Review Document: Unified Decision Pipeline (DecisionEngine)

**Date:** 2026-04-02 11:20 AM (PST)
**Reference Design:** `rpg-design.txt`
**Target:** Collapse GOAP + LLM mind + intent into ONE authoritative decision pipeline

---

## Summary

This refactoring implements the decision pipeline design from `rpg-design.txt`. The changes introduce a single authoritative entry point for NPC decisions, replacing the previous scattered call patterns.

### BEFORE
- 4 competing decision systems (`npc_mind.decide_action`, `planner.execute`, `behavior_driver.run`, `intent_engine.process`)
- Unpredictable NPC behavior
- LLM could return actions directly
- No structured debug visibility

### AFTER
- **1 pipeline**: `DecisionEngine.decide(npc, world_state)` → `(action, debug_trace)`
- Deterministic + expressive
- Fully debuggable (goap_plan → llm_adjustment → final_action → confidence)
- Extensible architecture

---

## Files Changed / Created

| File | Status | Lines | Description |
|------|--------|-------|-------------|
| `src/app/rpg/ai/decision/__init__.py` | **NEW** | 18 | Package initializer |
| `src/app/rpg/ai/decision/decision_engine.py` | **NEW** | 130 | Core pipeline orchestrator |
| `src/app/rpg/ai/decision/resolver.py` | **NEW** | 149 | ActionResolver + emotion step map |
| `src/app/rpg/ai/__init__.py` | Modified | +8 | Exports new DecisionEngine classes |
| `src/app/rpg/ai/goap/__init__.py` | Modified | +32 | Lazy wrapper exports |
| `src/app/rpg/ai/goap/actions.py` | Modified | -160 | Re-exports from planner.py |
| `src/app/rpg/ai/goap/planner.py` | Modified | +280 | Pure planner, no side effects |
| `src/app/rpg/ai/llm_mind/npc_mind.py` | Modified | +104 | Added `evaluate_plan()` method |

### Tests Created

| File | Type | Tests |
|------|------|-------|
| `src/tests/unit/rpg/test_decision_engine.py` | **Unit** | DecisionContext, ActionResolver, DecisionEngine, Confidence |
| `src/tests/functional/test_decision_engine_functional.py` | **Functional** | Survival/combat/idle plans, LLM emotion, override, multi-tick |
| `src/tests/regression/test_decision_engine_regression.py` | **Regression** | Determinism, edge cases, backward compat, plan immutability |

---

## Code Diff

### 1. NEW FILE — decision_engine.py

```python
# src/app/rpg/ai/decision/decision_engine.py

class DecisionContext:
    def __init__(self, npc, world_state):
        self.npc = npc
        self.world_state = world_state
        self.plan = None
        self.llm_adjustment = None
        self.final_action = None
        self.debug_trace = {}
        self.confidence = 0.5


class DecisionEngine:
    def __init__(self, goap_planner, llm_mind, resolver):
        self.goap_planner = goap_planner
        self.llm_mind = llm_mind
        self.resolver = resolver

    def decide(self, npc, world_state):
        ctx = DecisionContext(npc, world_state)

        # 1. Structured plan (deterministic backbone)
        ctx.plan = self.goap_planner.plan(npc, world_state)
        ctx.debug_trace["goap_plan"] = ctx.plan

        # 2. LLM cognitive modulation
        ctx.llm_adjustment = self.llm_mind.evaluate_plan(
            npc=npc, plan=ctx.plan, world_state=world_state
        )
        ctx.debug_trace["llm_adjustment"] = ctx.llm_adjustment

        # 3. Final resolution (single authority)
        ctx.final_action = self.resolver.resolve(
            npc=npc, plan=ctx.plan, llm_adjustment=ctx.llm_adjustment, world_state=world_state
        )
        ctx.debug_trace["final_action"] = ctx.final_action

        # Confidence scoring
        priority = ctx.plan.get("priority", 0.5) if ctx.plan else 0.5
        risk = ctx.llm_adjustment.get("risk_tolerance", 0.5) if ctx.llm_adjustment else 0.5
        ctx.confidence = priority * (1 - risk)
        ctx.debug_trace["confidence"] = ctx.confidence

        return ctx.final_action, ctx.debug_trace
```

### 2. MODIFY GOAP PLANNER (make it pure)

**BEFORE:**
```python
# src/app/rpg/ai/goap/planner.py
def plan(self, npc, world_state):
    action = self._compute_and_execute(npc, world_state)
    return action
```

**AFTER:**
```python
# src/app/rpg/ai/goap/planner.py
class GOAPPlanner:
    def plan(self, npc, world_state) -> Dict[str, Any]:
        # Returns structured plan, NOT action
        goals = self._derive_goals(npc, world_state)
        # ... A* search for best goal plan ...
        return {
            "goal": "survive",       # str
            "steps": ["find_cover", "draw_weapon", "attack"],  # List[str]
            "priority": 0.8          # float 0.0-1.0
        }
```

**RULE:** GOAP returns structured plan, not action.

### 3. MODIFY LLM MIND (change role completely)

**BEFORE:**
```python
# src/app/rpg/ai/llm_mind/npc_mind.py
def decide_action(self, npc, world_state):
    return llm_generate_action(...)  # Returns action directly
```

**AFTER:**
```python
# src/app/rpg/ai/llm_mind/npc_mind.py
def evaluate_plan(self, npc, plan, world_state) -> Dict[str, Any]:
    """
    Takes structured plan and returns adjustment:
    - modify priority
    - veto action
    - inject emotion/behavior
    """
    # ... build LLM prompt for plan evaluation ...
    return {
        "override": response.get("override", False),
        "override_action": response.get("override_action"),
        "new_goal": response.get("new_goal"),
        "emotional_bias": response.get("emotion"),
        "risk_tolerance": response.get("risk", 0.5),
    }
```

### 4. NEW FILE — resolver.py

```python
# src/app/rpg/ai/decision/resolver.py

class ActionResolver:
    def resolve(self, npc, plan, llm_adjustment, world_state):
        llm_adj = llm_adjustment or {}

        # LLM override (rare, but allowed)
        if llm_adj.get("override"):
            return self._handle_override(npc, llm_adj)

        # No plan → safe fallback
        if not plan:
            return "idle"

        # Adjust plan based on emotion/risk
        adjusted_plan = self._apply_adjustments(plan, llm_adj)

        # Select final action
        return self._select_action(adjusted_plan)

    def _select_action(self, plan) -> Any:
        return plan["steps"][0] if plan.get("steps") else "idle"
```

### 5. REPLACE ALL DECISION ENTRY POINTS

**BEFORE:**
```python
action = npc_mind.decide_action(npc, world_state)
action = planner.execute(npc, world_state)
action = behavior_driver.run(npc)
action = intent_engine.process(npc)
```

**AFTER:**
```python
action, debug = decision_engine.decide(npc, world_state)
```

**Example debug output:**
```python
{
    "goap_plan": {"goal": "combat", "steps": ["approach", "attack"], "priority": 0.85},
    "llm_adjustment": {"override": False, "emotional_bias": "anger", "risk_tolerance": 0.3},
    "final_action": "attack",
    "confidence": 0.595
}
```

---

## Strict Rules Enforced

| Rule | Description |
|------|-------------|
| **No direct LLM → action** | LLM only returns adjustments, never final actions (except override) |
| **No side effects in planner** | `GOAPPlanner.plan()` is pure — no state mutations |
| **Only resolver returns action** | `ActionResolver` is the single authority for final action selection |
| **Everything flows through DecisionEngine** | All NPC decision entry points route through one method |

---

## Test Coverage

### Unit Tests (test_decision_engine.py)
- DecisionContext default state and serialisation
- ActionResolver: no plan → idle, plan with steps → first step, LLM override, emotion bias injection
- DecisionEngine: full pipeline orchestration, LLM override via engine, confidence formula
- **10 test cases**

### Functional Tests (test_decision_engine_functional.py)
- Survival plan when low HP
- Combat plan when enemies visible
- Default idle when no goals
- LLM emotion step injection
- Multi-tick consistency
- Planner returns dict, no side effects
- All 8 emotion types tested
- **14 test cases**

### Regression Tests (test_decision_engine_regression.py)
- Deterministic output for identical inputs
- No action returned outside resolver
- Empty plan handling
- None / empty LLM adjustment handling
- Plan immutability (not mutated by resolver)
- NPCMind.evaluate_plan compatibility check
- **14 test cases**

---

## Architecture Diagram

```
                          ┌─────────────────────────────────┐
                          │     DecisionEngine.decide()      │
                          │    (ONLY entry point)            │
                          └──────────────┬──────────────────┘
                                         │
               ┌─────────────────────────┼─────────────────────────┐
               │                         │                         │
     ┌────────▼────────┐      ┌─────────▼─────────┐     ┌────────▼────────┐
     │   GOAP Planner   │      │     LLM Mind       │     │ ActionResolver  │
     │  (deterministic)  │      │  (expressive layer)│     │  (final action) │
     └───────────────────┘      └───────────────────┘     └─────────────────┘
             │                          │                          │
     ┌───────▼───────┐         ┌─────────▼───────┐        ┌───────▼───────┐
     │  plan:        │         │  adjustment:     │        │  action:      │
     │   goal        │         │   override       │        │   "attack"    │
     │   steps       │         │   new_goal       │        │               │
     │   priority    │         │   emotion        │        │   (final)     │
     │               │         │   risk_tolerance │        │               │
     └───────────────┘         └─────────────────┘        └───────────────┘
```

---

## How to Use

```python
from rpg.ai.decision import DecisionEngine, ActionResolver
from rpg.ai.goap import GOAPPlanner

# Initialise once
decision_engine = DecisionEngine(
    goap_planner=GOAPPlanner(),
    llm_mind=npc_mind,          # Must have evaluate_plan()
    resolver=ActionResolver(),
)

# Every NPC tick:
action, debug = decision_engine.decide(npc, world_state)
print(debug)  # Full pipeline visibility
```

---

**Generated:** 2026-04-02T11:20:00-07:00
**Commit:** fc3cd20..(new)