# Phase 5.6 — LLM Boundary Hardening Implementation Review

**Date:** 2026-04-02 20:52
**Status:** Implementation Complete
**Tests:** 16/16 passed (6 unit, 2 functional, 8 regression)

## Goals

After this implementation:
1. replay/simulation cannot silently call live LLMs
2. LLM-backed systems must go through a single deterministic gateway
3. missing recorded outputs in replay become hard failures
4. prompt/response records become snapshot-able engine state
5. effect policy and LLM policy become aligned
6. validation can prove whether a subsystem is replay-safe

## Files Added

- `src/app/rpg/core/llm_boundary.py` — Single deterministic gateway (`LLMGateway`, `LLMCallSpec`)
- `src/tests/unit/rpg/test_phase56_llm_boundary.py` — 6 unit tests
- `src/tests/functional/test_phase56_llm_boundary_functional.py` — 2 functional tests
- `src/tests/regression/test_phase56_llm_boundary_regression.py` — 8 regression tests

## Files Modified

- `src/app/rpg/core/llm_recording.py` — Added `serialize_state()`/`deserialize_state()` to LLMRecorder; added `effect_manager` parameter and `_check_live_llm_allowed()` to `DeterministicLLMClient`; added `_check_live_llm_allowed()` to `chat()` and `generate()` methods
- `src/app/rpg/core/state_contracts.py` — Added `LLMRecorderAware` protocol
- `src/app/rpg/core/snapshot_manager.py` — Added `llm_state` field; integrated LLM recorder serialization in save/load; enhanced timeline state to include seen_event_ids, seq, current_tick; added LLM state restoration in load_snapshot
- `src/app/rpg/core/__init__.py` — Exported `LLMGateway`, `LLMCallSpec`, `LLMRecorderAware`
- `src/app/rpg/core/determinism.py` — Added `SeededRNG.getstate()`, `setstate()`, `serialize_state()`, `deserialize_state()` for snapshot support
- `src/app/rpg/validation/state_boundary_validator.py` — Added `validate_llm_replay_safety()` method
- `src/app/rpg/ai/branch_ai_evaluator.py` — Replaced raw LLM client usage with `LLMGateway`

## Key Design Decisions

### LLMGateway as Single Entry Point
All LLM access now flows through `LLMGateway.call()`. Subsystems no longer call raw LLM clients directly. This provides:
- Centralized effect-manager awareness for gating live LLM calls
- Automatic mode switching via `set_mode("replay")` / `set_mode("live")`
- Propagation of effect manager, LLM recorder, and determinism config to the wrapped client

### DeterministicLLMClient Effect Manager Integration
The `DeterministicLLMClient.complete()`/`.chat()`/`.generate()` methods now call `_check_live_llm_allowed()` before making any live LLM call. If the effect manager blocks `live_llm`, a `RuntimeError` is raised.

### Hard Failure on Missing Recording
In replay mode (`use_recorded_llm=True`), the `LLMRecorder.replay()` method raises `KeyError` if no recorded response exists. This ensures replay cannot silently diverge from the original execution.

### Serializability
`LLMRecorder.serialize_state()` and `LLMRecorder.deserialize_state()` enable the recorder state to be captured in snapshots and restored during replay, making deterministic state fully reconstructable.

### SeededRNG Snapshot Support
Added `getstate()`, `setstate()`, `serialize_state()`, `deserialize_state()` methods to `SeededRNG` class to enable RNG state to be captured in snapshots.

### Snapshot Enhancements
- Timeline state now includes `seen_event_ids`, `seq`, and `current_tick` for full event bus state restoration
- Snapshot manager restores LLM recorder state on load
- Snapshot manager handles dict-form timeline state restoration for enhanced timeline data

## Test Coverage

### Unit Tests (6 passed)
- `test_live_llm_call_blocked_by_effect_policy` — Live LLM blocked when policy forbids
- `test_live_llm_call_allowed_and_recorded` — Live LLM succeeds and records output
- `test_replay_uses_recorded_output_only` — Replay retrieves recorded output, no LLM call
- `test_replay_missing_record_fails_hard` — KeyError raised on unrecorded prompt in replay
- `test_set_mode_switches_between_replay_and_live` — Mode propagation works correctly
- `test_set_effect_manager_propagates_to_client` — Effect manager swap updates client

### Functional Tests (2 passed)
- `test_replay_blocks_fresh_llm_and_uses_recorded` — End-to-end GameLoop integration
- `test_llm_recorder_serialization_roundtrip` — LLMRecorder state survives serialize/deserialize

### Regression Tests (8 passed)
- `test_recorded_outputs_are_snapshot_serializable` — Records survive serialization roundtrip
- `test_llm_gateway_no_client_raises_error` — Empty gateway rejects all calls
- `test_llm_gateway_unsupported_method_raises_error` — Unknown methods raise ValueError
- `test_effect_policy_live_vs_replay` — Live/replay policies behave as expected
- `test_state_boundary_validator_llm_replay_safety` — Replay safety validation passes
- `test_deterministic_llm_client_with_effect_manager` — Direct client gating works
- `test_multiple_records_load_and_replay` — Bulk record operations work
- `test_gateway_mode_switch_preserves_state` — Mode changes don't corrupt state

## Commits

1. `a7f9143` — Phase 5.6: LLM Boundary Hardening (initial implementation)
2. `2e20024` — Phase 5.6 Fix#2: LLM boundary hardening fixes (effect manager in chat/generate, SeededRNG snapshot support)

## Code Diff
See: `review-documents/rpg-phase56-llm-boundary-implementation-20260402-2052.diff`