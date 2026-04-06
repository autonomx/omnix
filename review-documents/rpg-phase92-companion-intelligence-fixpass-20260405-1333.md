# Phase 9.2 — Companion Intelligence Fixpass

**Date:** 2026-04-05 13:33

## Issues Fixed

### Fix #1: Inventory/Equipment Ownership Conflict (CRITICAL)
- **Problem:** Equipment stored `{item_id, qty}` dict creating duplication — inventory owns quantity but equipment also tracked it
- **Fix:** Equipment now stores `item_id` as a string directly (pointer model). Inventory owns quantity, equipment only points to what item is equipped.
- **Files:** `party_state.py` (_normalize_companion, set_companion_equipment)

### Fix #2: Companion AI Double Execution Guard
- **Problem:** No guard against running companion AI twice within same tick (e.g., network retries)
- **Fix:** Added `_companions_ran` marker to encounters_state. Returns early if already set.
- **Files:** `companion_ai.py` (run_companion_turns)

### Fix #3: Loyalty Range + AI Behavior Bands
- **Problem:** [-1, 1] loyalty range collapsed negative/slightly-low into same behavior
- **Fix:** Explicit loyalty bands: < -0.3 = hostile (refuse), > -0.3 = cooperative
- **Files:** `companion_ai.py` (choose_companion_action)

### Fix #4: Downed Companion Mutation Guard
- **Problem:** Downed companions could still be equipped, use items, act
- **Fix:** Added `_is_companion_downed()` helper. All mutation paths check it.
- **Files:** `party_state.py`, `companion_effects.py`

### Fix #5: Migration Normalization
- **Problem:** Migration added fields but didn't fully normalize records
- **Fix:** Migration now calls `_normalize_companion()` for each companion, ensuring proper equipment structure
- **Files:** `v5_to_v6.py`

### Fix #6: Target Selection Determinism
- **Problem:** Targets from `participants` were not sorted — nondeterministic behavior
- **Fix:** Extracted `_get_hostile_targets()` that sorts by id before selection
- **Files:** `companion_ai.py`

### Fix #7: Atomic Effect Application
- **Problem:** Item effects read-apply-write in separate steps — partial state if interrupted
- **Fix:** Compute everything first, then mutate state once
- **Files:** `companion_effects.py`

### Fix #8: Party Summary Recomputation
- **Problem:** Summary could go stale if cached
- **Fix:** `build_party_summary` always recomputes from normalized state
- **Files:** `party_state.py`

### Fix #9: Phase Tracking
- **Problem:** No explicit companion phase in encounter model
- **Fix:** Set `encounter_state["phase"] = "companion"` during AI execution
- **Files:** `companion_ai.py`

### Fix #10: Equipment Slot Validation
- **Problem:** Arbitrary slot names were allowed
- **Fix:** `VALID_SLOTS = {"weapon", "armor", "consumable"}` enforced in set/clear
- **Files:** `party_state.py`

### Fix #11: Morale Integration in AI
- **Problem:** Morale was tracked but not used in decision logic
- **Fix:** morale < 0.3 causes hesitation (fear response)
- **Files:** `companion_ai.py`

## Test Results
- **Unit:** 18/18 passed
- **Functional:** 4/4 passed
- **Regression:** 5/5 passed
- **Total:** 27/27 passed