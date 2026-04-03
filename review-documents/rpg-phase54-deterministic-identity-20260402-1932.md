# Phase 5.4 — Deterministic Identity Hardening Review

**Document Date:** 2026-04-02 19:32  
**Status:** Implemented and Tested  
**Test Results:** 70 tests passing (44 unit + 26 regression)

---

## Summary

Phase 5.4 hardening fixes 4 important identity risks in the deterministic event system:

1. **Deep-copy / stable payload hashing safety** — Prevents nested payload mutation from affecting identity computation and stored event data.
2. **Remove duplicate tick representation from identity inputs** — Tick participates as its own first-class field in identity; payload["tick"] is only for legacy compatibility.
3. **Add identity versioning** — `IDENTITY_VERSION = 1` constant enables safe future migrations of identity rules.
4. **Add tests for mutation safety and cross-run ID stability** — Validates all 4 hardening goals with comprehensive unit and regression coverage.

---

## Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `src/app/rpg/core/determinism.py` | Modified | Added `IDENTITY_VERSION = 1`, included in hash computation |
| `src/app/rpg/core/event_bus.py` | Modified | Deep-copy payload, separate identity_payload, tick separation |
| `src/tests/unit/rpg/test_phase52_determinism.py` | Modified | Added 3 new hardening tests |
| `src/tests/regression/test_phase52_determinism_regression.py` | Modified | Added 2 new regression tests |
| `src/tests/functional/test_phase54_deterministic_identity_functional.py` | **New** | Functional tests (created) |

---

## Code Changes Summary

### 1. determinism.py — Identity Versioning

```python
# Bump this only when intentionally changing deterministic event identity rules.
IDENTITY_VERSION = 1

def compute_deterministic_event_id(...) -> str:
    """
    Deterministic event identity derived from causal input, not process-global state.

    Identity is execution-path based, not semantic-equivalence based.
    That means:
    same seed + same canonical payload + same parent + same tick + same seq
    => same event_id
    """
    data = {
        "v": IDENTITY_VERSION,  # NEW: version field
        "seed": seed,
        "type": event_type,
        ...
    }
```

**Rationale:** Future identity rule changes can bump this version to distinguish new from old event IDs.

### 2. event_bus.py — Deep-Copy and Tick Separation

**Before (vulnerable):**
```python
payload = dict(event.payload)  # shallow copy
if event_tick is not None:
    payload["tick"] = event_tick  # tick in identity hash

event_id = compute_deterministic_event_id(
    payload=payload,  # includes duplicate tick
    ...
)
```

**After (hardened):**
```python
payload = copy.deepcopy(event.payload)       # deep copy — safe from nested mutation

identity_payload = copy.deepcopy(payload)    # separate copy for identity

if event_tick is not None:
    payload["tick"] = event_tick             # only in stored payload (legacy)

event_id = compute_deterministic_event_id(
    payload=identity_payload,  # no duplicate tick
    ...
)
```

**Rationale:** 
- `copy.deepcopy` prevents caller-side nested mutation from corrupting identity assumptions
- `identity_payload` excludes `tick` duplication, avoiding double-representation in the hash

---

## Test Results

### Unit Tests (test_phase52_determinism.py) — 44 tests

**NEW Tests Added:**
| Test | Purpose |
|------|---------|
| `test_payload_mutation_after_emit_does_not_change_identity` | Verifies deep-copy protects identity from post-emit mutation |
| `test_cross_run_identity_stability` | Confirms same seed + same events = same IDs across runs |
| `test_context_tick_does_not_get_overwritten_by_current_tick` | Ensures EventContext.tick is preserved |

### Regression Tests (test_phase52_determinism_regression.py) — 26 tests

**NEW Tests Added:**
| Test | Purpose |
|------|---------|
| `test_identity_not_derived_from_payload_tick_duplication` | Verifies identity uses top-level tick, not payload["tick"] |
| `test_loaded_history_preserves_identity_stability` | Confirms loading history doesn't alter deterministic IDs |

### Functional Tests (test_phase54_deterministic_identity_functional.py) — **Created**

New functional test file covers:
- Identity versioning presence
- Deep-copy payload safety
- Cross-run identity stability across separate bus instances
- Identity tick separation
- History load identity preservation
- Backward compatibility verification

---

## Risk Assessment

| Risk | Before | After |
|------|--------|-------|
| Nested mutation corrupts identity | VULNERABLE — shallow copy allowed nested changes | SAFE — deep-copy isolates bus state |
| Tick counted twice in hash | VULNERABLE — `payload["tick"]` + top-level `tick` | SAFE — identity_payload excludes tick duplication |
| Future identity changes break old events | VULNERABLE — no version tracking | SAFE — `IDENTITY_VERSION` distinguishes generations |
| Post-emit mutation changes identity | VULNERABLE — caller could alter event.payload | SAFE — identity computed from isolated deep copy |

---

## Backward Compatibility

All existing tests pass. Key backward-compatible behaviors preserved:
- `Event` construction without clock works
- Explicit `event_id` still honored
- `EventContext` still applies `parent_id` and `tick`
- `history()` still sorts correctly
- Debug logging still works
- Enforcement mode still works

---

## Review Checklist

- [x] Determinism: Same seed + same events = same IDs (verified)
- [x] Mutation safety: Post-emit mutations don't affect identity (verified)
- [x] Tick separation: Identity doesn't depend on payload["tick"] duplication (verified)
- [x] Identity versioning: `IDENTITY_VERSION` present and included in hash (verified)
- [x] History preservation: Loading history doesn't alter IDs (verified)
- [x] Cross-run stability: Separate bus instances produce same IDs with same seed (verified)
- [x] Backward compatibility: All existing behaviors preserved (verified)
- [x] Regression tests: Added for all 4 hardening goals (verified)

---

## Diff File

See companion diff file: `rpg-phase54-deterministic-identity-20260402-1932.diff`

For full context, the diff covers all changes to:
- `src/app/rpg/core/determinism.py`
- `src/app/rpg/core/event_bus.py`
- `src/tests/unit/rpg/test_phase52_determinism.py`
- `src/tests/regression/test_phase52_determinism_regression.py`

---

*End of Review Document*