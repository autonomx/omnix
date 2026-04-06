# Phase 10.6 — LLM Orchestration Layer Fix-Pass

**Date:** 2026-04-05 17:10  
**Status:** All 8 fixes applied and verified (31/31 tests passing)

## Fixes Applied

### 1. Disabled mode semantics
**File:** `src/app/rpg/orchestration/controller.py`

Disabled mode without fallback now correctly marks the request as failed instead of success:
- When status is `"disabled"`, calls `fail_llm_request()` with explicit error
- Otherwise calls `finalize_llm_request()` normally

### 2. Replay artifact selection tightening
**File:** `src/app/rpg/orchestration/replay.py`

`find_replayable_llm_request()` now filters by status, only accepting artifacts with status in `{complete, replayed, failed}`. Applied to both `request_id` and `turn_id` lookup paths.

### 3. Provider mode normalization
**File:** `src/app/rpg/orchestration/provider_interface.py`

`set_llm_provider_mode()` now returns through `trim_llm_orchestration_state()` ensuring bounded state caps are enforced after every provider mode change.

### 4. Explicit unsupported-mode reporting
**File:** `src/app/rpg/orchestration/controller.py`

`NotImplementedError` message now includes "in Phase 10.6" for clearer inspector/debug output when capture or live is selected before those paths are implemented.

### 5. Deterministic request-id counter helper
**File:** `src/app/rpg/orchestration/controller.py`

Added `_request_id_counter()` helper for safe request ID counter extraction. Used in `_latest_active_request_id_for_turn()` for deterministic sort ordering.

### 6. Orchestration bridge determinism
**File:** `src/app/rpg/presentation/orchestration_bridge.py`

- `_build_request_payload()` now includes `is_replayed` and `is_failed` boolean flags
- `active_requests` and `completed_requests` are sorted by (tick, request_id, turn_id)
- `last_error` is compacted to only include `request_id` and `error` fields
- `live_execution_supported` explicitly set to `False`

### 7. Route-level orchestration visibility
**File:** `src/app/rpg/api/rpg_presentation_routes.py`

Scene, dialogue, and speakers routes now include orchestration payload in response:
- `build_orchestration_presentation_payload()` called alongside scene/dialogue/speaker builders
- Payload merged additively into dict response (no destructive override)

### 8. Regression tests
**Files created:**
- `src/tests/regression/test_phase106_disabled_mode_semantics_regression.py` — 1 test
- `src/tests/regression/test_phase106_routes_orchestration_regression.py` — 1 test

## Test Results

| Suite | Count | Status |
|-------|-------|--------|
| Unit | 18 | PASS |
| Functional | 6 | PASS |
| Regression (original) | 5 | PASS |
| Regression (new disabled-mode) | 1 | PASS |
| Regression (new routes) | 1 | PASS |
| **Total** | **31** | **PASS** |