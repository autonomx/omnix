# RPG Design Implementation — Tier 11: Hybrid Cognitive Simulation

**Implementation Date**: April 1, 2026 (14:15 UTC-7)
**Status**: Complete — 113 tests passing (93 unit + 20 integration)
**Commit**: `3ed0b2e`

---

## Overview

Tier 11 implements **Hybrid Cognitive Simulation** — a deterministic core augmented by controlled LLM-assisted cognitive capabilities. This is NOT replacing deterministic agents with chatbots; it uses LLM only in constrained layers for intent enrichment, with strict guardrails.

### What Was NOT Done (Correctly)
- ❌ No AgentBrain replacement with LLM
- ❌ No LLM planning every tick
- ❌ No LLM mutating world state directly

### What WAS Done (Correctly)

| Feature | Module | Description |
|---------|--------|-------------|
| **Layer 1: Intent Enrichment** | `cognitive/intent_enrichment.py` | LLM-assisted priority & target refinement |
| **Layer 4: Identity System** | `cognitive/identity.py` | Reputation, fame, rumors tracking |
| **Layer 5: Coalition System** | `cognitive/coalition.py` | Coordinated NPC faction behavior |
| **Layer 6: Learning System** | `cognitive/learning.py` | Outcome tracking & behavioral adaptation |
| **Unified API** | `cognitive/cognitive_layer.py` | Single entry point (`CognitiveLayer`) |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│               CognitiveLayer (Unified)               │
│  ┌───────────────────┐  ┌──────────────────────────┐│
│  │ IntentEnrichment   │  │ IdentitySystem            ││
│  │ (LLM-assisted)     │  │ (reputation, fame, rumors)││
│  │ - Guard rail types │  │ - Faction reputation      ││
│  │ - Priority adjust  │  │ - Character relationships ││
│  │ - Target suggest   │  │ - Rumor propagation       ││
│  │ - Cooldown control │  │ - Action history          ││
│  └───────────────────┘  └──────────────────────────┘│
│  ┌───────────────────┐  ┌──────────────────────────┐│
│  │ CoalitionSystem    │  │ LearningSystem            ││
│  │ (coordinated acts) │  │ (outcome tracking)        ││
│  │ - Faction search   │  │ - Failure detection       ││
│  │ - Trust tracking   │  │ - Priority adaptation     ││
│  │ - Coalition forms  │  │ - Alternative suggestion  ││
│  │ - Stability check  │  │ - History windowing       ││
│  └───────────────────┘  └──────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Controlled LLM Injection
LLM is only called through `IntentEnrichment.enrich()` which:
- Validates response against whitelisted intent types
- Bounded priority range (0-10)
- Cooldown prevents every-tick LLM calls
- Falls back to original intent on any failure

### 2. Reputation System
Actions affect faction reputation:
- Positive actions (`heal`, `protect`, `save`) → positive reputation
- Negative actions (`attack`, `damage`, `betray`) → negative reputation
- Max single change: 0.3 (prevents wild swings)
- Notable actions generate rumors that fade over time

### 3. Coalition Formation
Weak factions naturally seek coalitions when:
- Power < 0.3 (survival pressure)
- Stronger enemies detected
- Positive relations exist with potential partners
- Coalition size max: 5 members
- Coalitions dissolve on trust failure or stale behavior

### 4. Learning Without ML
Simple outcome tracking with behavioral adaptation:
- Records last N actions per character (max 30)
- Detects repeated failures (3 in 10-action window)
- Reduces intent priority based on failures
- Suggests alternative action based on historical success rates
- Adaptation cooldown prevents thrashing

---

## Files Changed

| File | Lines | Purpose |
|------|-------|---------|
| `src/app/rpg/cognitive/__init__.py` | 32 | Package init/exports |
| `src/app/rpg/cognitive/intent_enrichment.py` | 430 | Layer 1: LLM-assisted intent |
| `src/app/rpg/cognitive/identity.py` | 540 | Layer 4: Reputation/fame/rumors |
| `src/app/rpg/cognitive/coalition.py` | 558 | Layer 5: Faction coordination |
| `src/app/rpg/cognitive/learning.py` | 452 | Layer 6: Outcome tracking |
| `src/app/rpg/cognitive/cognitive_layer.py` | 441 | Unified API facade |
| `src/tests/unit/rpg/test_tier11_cognitive.py` | 973 | 93 unit tests |
| `src/tests/integration/test_tier11_cognitive.py` | 613 | 20 integration tests |

**Total: 4,639 lines added (8 new files)**

---

## Test Results

### Unit Tests (93 passed)
- IntentEnrichment: 12 tests
- IdentitySystem: 17 tests  
- CoalitionSystem: 17 tests
- LearningSystem: 17 tests
- CognitiveLayer: 17 tests
- Guardrails: 4 tests
- Regression: 9 tests

### Integration Tests (20 passed)
- Full cognitive cycle: 4 tests
- Multi-tick simulation: 3 tests
- Emergent behavior: 3 tests
- Edge cases: 5 tests
- Regression: 5 tests

---

## Usage

```python
from rpg.cognitive import CognitiveLayer

# Initialize with optional LLM
cognitive = CognitiveLayer(llm_client=llm_client)

# Process NPC decisions
intent = brain.decide(character, world_state)
enriched = cognitive.process_decision(character, intent, world_state, tick)

# Record outcomes after execution
cognitive.record_outcome(char_id, action_type, success, tick)

# Periodic maintenance
cognitive.tick_update(tick)

# Get reputation summary
summary = cognitive.get_character_summary("hero_alice")
```

---

## Guardrails Summary

| Risk | Mitigation |
|------|-----------|
| LLM changes intent type | Intent type whitelist enforced |
| LLM returns invalid priority | Range validation (0-10), fallback to original |
| LLM called every tick | Cooldown (default: 5 ticks) |
| Reputation swings wildly | Max change per action: 0.3 |
| Coalition size explodes | Max 5 members |
| History grows unbounded | Deque maxlen enforced |
| NPC stuck in failing loop | Failure threshold triggers adaptation |

---

## Integration Notes

1. The CognitiveLayer is designed to wrap around existing `AgentBrain.decide()` without modifying its logic
2. No changes to core RPG systems are required
3. Existing tests remain unaffected (113 passing total for Tier 11)
4. LLM integration follows the same pattern as `NarrativeGenerator` (uses `generate_json()`)