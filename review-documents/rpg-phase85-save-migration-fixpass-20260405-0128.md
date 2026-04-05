# Phase 8.5 — Save Migration Fixpass

**Date:** 2026-04-05 01:28 UTC

## Summary

Fixed 3 critical bugs + 2 improvements identified in Phase 8.5 review:

| ID | Severity | Status |
|----|----------|--------|
| BUG 1 — Migration infinite loop protection | Critical | Fixed |
| BUG 2 — package_builder duplicates simulation_state | Critical | Fixed |
| BUG 3 — import route returns 500 instead of structured error | Critical | Fixed |
| IMPROVEMENT 1 — Add schema version to simulation_state | Recommended | Fixed |
| IMPROVEMENT 2 — Deterministic timestamps in package_builder | Recommended | Fixed |

## Changes

### 1. Migration Manager — Infinite Loop Protection
**File:** `src/app/rpg/persistence/migration_manager.py`

Added `prev_version` tracking to detect if migration fails to advance:
```python
while version < CURRENT_RPG_SCHEMA_VERSION:
    prev_version = version
    # ... migration logic ...
    version = _safe_int(package.get("schema_version"), version + 1)
    if version <= prev_version:
        raise ValueError(f"Migration did not advance schema version (stuck at {version})")
```

### 2. Package Builder — Remove Duplicate simulation_state
**File:** `src/app/rpg/persistence/package_builder.py`

Removed `simulation_state` from metadata to avoid duplication (canonical location is now `state.simulation_state`):
```python
metadata = dict(metadata)
metadata.pop("simulation_state", None)
```

### 3. Package Builder — Deterministic Timestamps
**File:** `src/app/rpg/persistence/package_builder.py`

Added optional `now` parameter for testable deterministic output:
```python
def build_save_package(setup_payload: Dict[str, Any], now: str | None = None) -> Dict[str, Any]:
    ts = now or _utc_now()
```

### 4. Package Import — Structured Error Response
**File:** `src/app/rpg/api/rpg_package_routes.py`

Changed from 500 to structured 400 error with message:
```python
try:
    setup_payload = load_save_package(package)
    return jsonify({"ok": True, "setup_payload": setup_payload})
except Exception as e:
    return jsonify({"ok": False, "error": str(e)}), 400
```

### 5. Package Loader — Schema Version in simulation_state
**File:** `src/app/rpg/persistence/package_loader.py`

```python
simulation_state.setdefault("save_meta", {})
simulation_state["save_meta"]["schema_version"] = package.get("schema_version")
```

### 6. Package Validator — Enforce schema_version
**File:** `src/app/rpg/persistence/package_validator.py`

```python
if not isinstance(package.get("schema_version"), int):
    errors.append({"field": "schema_version", "error": "missing or invalid schema_version"})
```

### 7. Pre-existing Bug Fix — unified_brain.py import
**File:** `src/app/rpg/brain/unified_brain.py`

Fixed `from rpg.` → `from app.rpg.` imports (2 lines)

### 8. Pre-existing Bug Fix — npc_planner.py imports
**File:** `src/app/rpg/ai/npc_planner.py`

Fixed `from rpg.` → `from app.rpg.` imports (10 lines total: 6 top-level + 4 function-level)

## Test Status

- **36/44 tests pass** (all unit + regression tests)
- **8 functional tests error** at setup due to pre-existing systemic `from rpg.` import bug in ~91 files across the RPG module (unrelated to Phase 8.5)

The 8 failing functional tests fail at `create_app()` → `pipeline.py` → `unified_brain.py` → `npc_planner.py` → `app.rpg.ai.goap` → `rpg.ai.goap` (ModuleNotFoundError). The full dependency tree has ~91 files needing import fixes across the entire codebase.

## New Diff

See `review-documents/rpg-phase85-save-migration-fixpass-20260405-0128.diff` for complete code diff.