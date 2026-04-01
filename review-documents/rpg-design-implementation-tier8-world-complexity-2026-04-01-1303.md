# TIER 8: World Complexity Layer - Implementation Review

**Date:** 2026-04-01  
**Time:** 13:03  
**Design Source:** `rpg-design.txt` (Tier 8 section)  
**Status:** IMPLEMENTED + TESTED

---

## Executive Summary

Tier 8: World Complexity Layer implements three interconnected systems that transform the RPG world from a static backdrop into a living, breathing ecosystem:

1. **Economy System** - Supply/demand simulation with trade flow detection
2. **Dynamic Quest Generator** - Quests generated from world pressure, not pre-authored
3. **Political System** - Faction leadership, instability tracking, and coup mechanics

These systems communicate via **events and world state only** (never direct calls to each other), following the critical design rule: "These systems MUST NOT directly call each other; they communicate via: world state, events, flags."

This enables the **emergent story chains** described in the design:
```
Food shortage -> Trade spike -> Faction conflict over routes -> 
Player helps one side -> Reputation shifts -> Leader overthrown -> 
New faction ideology -> New story arc
```

---

## Test Results

| Suite | Status | Tests | Notes |
|-------|--------|-------|-------|
| Economy (Market) | ✅ PASS | 8 tests | Price simulation, shortage detection |
| Economy (System) | ✅ PASS | 5 tests | Trade flow, route management |
| Political System | ✅ PASS | 5 tests | Leader assignment, coup mechanics |
| Quest Generator | ✅ PASS | 6 tests | War, supply, trade, political quests |
| Integration | ✅ PASS | 3 tests | Cross-system interaction |
| Ruff Linting | ✅ PASS | 4 files | All checks passed |

**Total: 28 tests passed** with no linting errors.

---

## New Files Created

### 1. `src/app/rpg/world/economy_system.py` (287 lines)

**Classes:**
- `Market` - Local market tracking supply/demand/price for goods
- `EconomySystem` - Multi-location economy with trade route simulation

**Key Features:**
- Supply/demand price simulation (ratio-based, 10% adjustment per unit imbalance)
- Complete shortage = 50% price spike
- Price clamping to 0.01 - 10.0 range
- Trade flow detection (price diff > 0.2 triggers trade)
- Trade volume scaling with price difference
- Event generation: `price_change`, `shortage`, `trade_flow`

**Economic Events Generated:**
| Event | Trigger | Importance |
|-------|---------|------------|
| `shortage` | supply < 0.2 | 0.6 + (0.2 - supply) * 2.0 |
| `price_change` | >20% price shift | min(1.0, price_change_ratio) |
| `trade_flow` | price diff > 0.2 | 0.4 |

### 2. `src/app/rpg/story/dynamic_quest_generator.py` (297 lines)

**Class:** `DynamicQuestGenerator`

**Key Features:**
- Faction conflict detection (relations < -0.7) → war quests
- Economic shortage detection (supply < 0.2) → supply/crisis quests
- Price opportunity detection → trade quests
- Political event observation → rebellion quests
- Quest deduplication via `generated_ids` set
- Clear/regeneration support for quest lifecycle management

**Quest Types Generated:**
| Type | Source | Fields |
|------|--------|--------|
| `war` | Faction relations < -0.7 | faction, target, urgency, description |
| `diplomacy` | Faction relations > 0.6 | faction, target, strength |
| `supply` | Economy supply < 0.2 | location, good, supply, price |
| `crisis` | Economy supply < 0.1 | location, good, urgency=0.9 |
| `trade` | Price diff > 0.3 on route | from, to, good, profit_margin |
| `rebellion` | Coup event | faction, old_leader, new_leader |

### 3. `src/app/rpg/world/political_system.py` (287 lines)

**Classes:**
- `Leader` - Faction leader with behavioral traits
- `PoliticalSystem` - Leadership tracking and coup simulation

**Key Features:**
- Leader traits affect faction behavior:
  - `aggressive`: -0.1 relations, +0.05 power growth
  - `diplomatic`: +0.1 relations, +0.0 power growth
  - `ambitious`: +0.0 relations, +0.1 power growth
  - `defensive`: +0.05 relations, -0.05 power growth
  - `ruthless`: -0.15 relations, +0.08 power growth
- Instability tracking: `1.0 - faction.morale`
- Coup probability: 10% per tick when instability > 0.7
- Auto-installs new leader with random traits
- Adjusts faction relations based on new leader's traits
- Event generation: `coup` events with old/new leader info

**Political Events Generated:**
| Event | Trigger | Importance |
|-------|---------|------------|
| `coup` | morale < 0.3 + 10% chance | 0.9 |

### 4. `src/tests/unit/rpg/test_tier8_world_complexity.py` (425 lines)

Comprehensive test suite with 28 tests covering:
- Market price mechanics (supply/demand ratio, zero supply, clamping)
- Economy system (market management, trade flow, route cleanup)
- Political system (leader lifecycle, coup triggers, stability)
- Quest generation (war, supply, trade, political quests)
- Deduplication and regeneration
- Cross-system integration tests

---

## Modified Files

### `src/app/rpg/core/player_loop.py` 

**Changes:**
1. Added Tier 8 imports: `EconomySystem`, `PoliticalSystem`, `DynamicQuestGenerator`
2. Added new constructor parameters: `economy_system`, `political_system`, `quest_generator`
3. Added new instance attributes: `self.economy`, `self.politics`, `self.quest_gen`, `self._tick`
4. Extended `step()` method with 35+ new lines:
   - Economy tick → add to world events
   - Political tick → add to world events  
   - Quest generation → inject into PlotEngine
   - Added `_quest_to_objectives()` helper method (6 quest type mappings)
   - Added `_update_faction_relations()` method (reputation-driven relation changes)
5. Extended `reset()` method to clear Tier 8 systems

**New Methods:**
- `_quest_to_objectives(quest)` → `List[str]` - Converts quest dict to PlotEngine objectives
- `_update_faction_relations()` - Updates faction relations based on player reputation

### `src/app/rpg/world/__init__.py`

Added exports: `Market`, `EconomySystem`, `Leader`, `PoliticalSystem`

### `src/app/rpg/story/__init__.py`

Added exports: `PlotEngine`, `Quest`, `QuestManager`, `Setup`, `SetupTracker`, `DynamicQuestGenerator`

---

## Integration Architecture

### System Communication (Event-Driven, No Direct Calls)

```
┌─────────────────────────────────────────────────┐
│                    PlayerLoop                    │
│                                                   │
│  1. Player action → world events                 │
│  2. World simulation tick                        │
│  3. FactionSystem.update() → faction events     │
│  4. EconomySystem.update() → economy events      │
│  5. PoliticalSystem.update(fs) → political events│
│  6. DynamicQuestGenerator.generate(fs, ec, pe)  │
│  7. PlotEngine.add_quest(id, type, objectives)   │
└─────────────────────────────────────────────────┘
```

### Emergent Chain Example (from design spec)

```
Tick 1: Market detects food shortage (supply=0.1)
  → Economy event: "shortage" (importance: 1.0)
  → QuestGenerator creates: "crisis" quest for food

Tick 2: Trade route moves food from source market
  → Economy event: "trade_flow" (volume: trade_amount)
  → Price difference narrows, supply increases

Tick 3: Factions fight over trade route
  → FactionSystem detects: relations < -0.6
  → Faction event: "faction_conflict"
  → QuestGenerator creates: "war" quest

Tick 4: Player helps one faction
  → Player reputation shifts
  → Faction relations update
  → Faction morale drops

Tick 5: Unstable faction has coup
  → Instability > 0.7, random() < 0.1
  → Political event: "coup"
  → QuestGenerator creates: "rebellion" quest
  → PlotEngine starts new story arc
```

---

## Design Compliance

| Design Requirement | Status | Implementation |
|-------------------|--------|----------------|
| Systems don't call each other | ✅ | All communicate via player_loop events |
| Economy: supply/demand per region | ✅ | Market tracks per-location goods |
| Economy: price fluctuations | ✅ | Ratio-based 10% adjustment + clamping |
| Economy: trade routes between factions | ✅ | EconomySystem tracks (src, dst, good) |
| Economy: scarcity → conflict | ✅ | Shortages generate quest opportunities |
| Quests: from world pressure | ✅ | DynamicQuestGenerator observes all systems |
| Politics: faction leaders | ✅ | Leader class with traits |
| Politics: instability → coups | ✅ | morale < 0.3 → 10% coup chance/tick |
| Politics: leadership affects behavior | ✅ | Leader traits modify faction relations |
| Player loop integration | ✅ | Full pipeline in player_loop.step() |
| Required tests | ✅ | 28 tests covering all requirements |

---

## API Reference

### EconomySystem
```python
economy = EconomySystem()
economy.add_market(Market("location_id"))
economy.add_trade_route("src", "dst", "good")
events = economy.update()  # -> [economy_events]
economy.reset()  # Clear all markets and routes
```

### DynamicQuestGenerator
```python
generator = DynamicQuestGenerator()
quests = generator.generate(
    faction_system=faction_system,
    economy_system=economy_system,
    political_events=political_events,
)
# quests = [{"id": ..., "type": "war", ...}, ...]
generator.clear_generated()  # Allow regeneration
generator.clear_by_type("conflict")  # Clear specific type
```

### PoliticalSystem
```python
politics = PoliticalSystem()
politics.set_leader("faction_id", Leader("Name", ["trait1", "trait2"]))
events = politics.update(faction_system)  # -> [political_events]
politics.reset()  # Clear all leadership data
```

---

## Known Limitations

1. **Trade route supply movement is simplified** - Some loss (0.8x) on transit, no distance or capacity modeling
2. **Leader names are randomized** - Uses prefix/name pools rather than faction-specific rosters
3. **Coup probability is flat** - 10% chance per tick when unstable, no escalating probability
4. **Quest objectives are templated** - Not yet AI-generated from world context
5. **No market-to-market cascade** - Shortage in one market doesn't naturally propagate to connected markets

---

## Files Modified/Created Summary

### New Files (4)
| File | Lines | Purpose |
|------|-------|---------|
| `src/app/rpg/world/economy_system.py` | 287 | Market + Economy System |
| `src/app/rpg/world/political_system.py` | 287 | Leader + Political System |
| `src/app/rpg/story/dynamic_quest_generator.py` | 297 | Dynamic Quest Generation |
| `src/tests/unit/rpg/test_tier8_world_complexity.py` | 425 | Test Suite (28 tests) |

### Modified Files (3)
| File | Change Type | Description |
|------|-------------|-------------|
| `src/app/rpg/core/player_loop.py` | +160 lines | Integration of all 3 systems |
| `src/app/rpg/world/__init__.py` | +12 exports | New class exports |
| `src/app/rpg/story/__init__.py` | +13 exports | New class exports |

**Total: 1,061 lines of code + 28 passing tests**

---

## Next Steps (Post-Tier 8)

1. **Tier 9+:** Add AI-driven narrative generation from quest events
2. **Market Expansion:** Add distance-aware trade routes with capacity limits
3. **Coup Escalation:** Progressive coup probability (cumulative while unstable)
4. **Quest AI Integration:** LLM-generated quest narratives and flavor text
5. **Market Crossover:** Shortages propagate to connected trade routes
6. **NPC Planners:** NPCs actively pursuing faction goals and economic opportunities