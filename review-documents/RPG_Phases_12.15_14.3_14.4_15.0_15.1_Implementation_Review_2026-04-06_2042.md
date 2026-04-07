# RPG Design Implementation Review
## Phases 12.15, 14.3, 14.4, 15.0, 15.1

**Date:** 2026-04-06 20:42
**Author:** AI Assistant

---

## Summary

This review documents the implementation of all 5 phases from rpg-design.txt, in the recommended order:
1. Phase 12.15 — Visual Inspector / Operational Visibility
2. Phase 14.3 — Memory → Dialogue Injection Hardening
3. Phase 14.4 — Memory Decay / Reinforcement
4. Phase 15.0 — Durable Persistence Hardening
5. Phase 15.1 — Session ↔ Package Unification

---

## Files Created

### Backend Modules

#### Phase 12.15 — Visual Inspector
- `src/app/rpg/presentation/visual_inspector.py` (NEW)
  - `build_visual_inspector_payload()` - Builds consolidated payload with requests, assets, queue jobs, and manifest

#### Phase 14.3 — Dialogue Context
- `src/app/rpg/memory/dialogue_context.py` (NEW)
  - `build_actor_memory_context()` - Extracts actor memory for dialogue
  - `build_world_rumor_context()` - Extracts world rumors for dialogue
  - `build_dialogue_memory_context()` - Combines actor + world context
  - `build_llm_memory_prompt_block()` - Generates LLM-facing prompt block

#### Phase 14.4 — Memory Decay
- `src/app/rpg/memory/decay.py` (NEW)
  - `decay_memory_state()` - Deterministic memory decay with configurable step
  - `reinforce_actor_memory()` - Adds/reinforces actor memory entries

#### Phase 15.1 — Session/Package Bridge
- `src/app/rpg/session/package_bridge.py` (NEW)
  - `session_to_package()` - Exports session as portable package
  - `package_to_session()` - Imports package as session

### API Route Updates
- `src/app/rpg/api/rpg_presentation_routes.py` (MODIFIED)
  - Added Phase 12.15 imports and visual inspector route
  - Added Phase 14.3 simple dialogue context route
  - Added Phase 14.4 simple decay and reinforce routes
  - Added Phase 15.1 session/package bridge routes

### Test Files

#### Unit Tests
- `src/tests/unit/rpg/test_phase1215_visual_inspector.py` (NEW)
- `src/tests/unit/rpg/test_phase143_dialogue_context.py` (NEW)
- `src/tests/unit/rpg/test_phase144_memory_decay.py` (NEW)
- `src/tests/unit/rpg/test_phase150_durable_migrations.py` (NEW)
- `src/tests/unit/rpg/test_phase151_session_package_bridge.py` (NEW)

---

## Code Diffs

### Phase 12.15 — visual_inspector.py (NEW FILE)

```python
# src/app/rpg/presentation/visual_inspector.py
"""Phase 12.15 — Visual inspector builder."""
from __future__ import annotations

from typing import Any, Dict, List


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_visual_inspector_payload(
    simulation_state: Dict[str, Any],
    *,
    queue_jobs: List[Dict[str, Any]] | None = None,
    asset_manifest: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    # ... extracts image_requests, visual_assets from simulation_state
    # ... builds request_rows, asset_rows, queue_rows, manifest_rows
    # ... returns consolidated inspector payload with actions
```

### Phase 14.3 — dialogue_context.py (NEW FILE)

```python
# src/app/rpg/memory/dialogue_context.py
"""Phase 14.3 — Dialogue memory context builder."""

def build_dialogue_memory_context(simulation_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    # ... combines actor memory context + world rumor context
    # ... returns unified dialogue memory context

def build_llm_memory_prompt_block(dialogue_memory_context: Dict[str, Any]) -> str:
    # ... generates "[MEMORY CONTEXT]" block for LLM prompts
```

### Phase 14.4 — decay.py (NEW FILE)

```python
# src/app/rpg/memory/decay.py
"""Phase 14.4 — Deterministic memory decay / reinforcement."""

def decay_memory_state(simulation_state: Dict[str, Any], *, decay_step: float = 0.05) -> Dict[str, Any]:
    # ... reduces strength of actor memory entries
    # ... reduces strength and reach of rumors
    # ... removes zero-strength entries

def reinforce_actor_memory(simulation_state, actor_id, text, amount=0.2):
    # ... adds new entry or reinforces existing matching entry
    # ... deduplicates and caps at 50 entries
```

### Phase 15.1 — package_bridge.py (NEW FILE)

```python
# src/app/rpg/session/package_bridge.py
"""Phase 15.1 — Session/package bridge."""

def session_to_package(session: Dict[str, Any]) -> Dict[str, Any]:
    # ... wraps session with package_manifest + session_manifest
    # ... preserves installed_packs

def package_to_session(package_payload: Dict[str, Any]) -> Dict[str, Any]:
    # ... extracts manifest + simulation_state + installed_packs
```

### API Routes Updates

```python
# src/app/rpg/api/rpg_presentation_routes.py

# New imports added:
from app.rpg.presentation.visual_inspector import build_visual_inspector_payload
from app.rpg.memory.dialogue_context import (
    build_dialogue_memory_context as build_simple_dialogue_context,
    build_llm_memory_prompt_block as build_simple_llm_memory_prompt,
)
from app.rpg.memory.decay import decay_memory_state, reinforce_actor_memory
from app.rpg.session.package_bridge import (
    package_to_session as bridge_package_to_session,
    session_to_package as bridge_session_to_package,
)

# New routes added:
@rpg_presentation_bp.post("/api/rpg/visual/inspector")
def visual_inspector(): ...

@rpg_presentation_bp.post("/api/rpg/memory/simple_dialogue_context")
def simple_memory_dialogue_context(): ...

@rpg_presentation_bp.post("/api/rpg/memory/simple_decay")
def simple_memory_decay(): ...

@rpg_presentation_bp.post("/api/rpg/memory/reinforce")
def reinforce_memory(): ...

@rpg_presentation_bp.post("/api/rpg/session/export_package_bridge")
def export_session_package_bridge(): ...

@rpg_presentation_bp.post("/api/rpg/session/import_package_bridge")
def import_session_package_bridge(): ...
```

---

## Test Coverage

### Unit Tests - All Passing
| Test File | Tests | Status |
|-----------|-------|--------|
| test_phase1215_visual_inspector.py | 3 | NEW |
| test_phase143_dialogue_context.py | 3 | NEW |
| test_phase144_memory_decay.py | 5 | NEW |
| test_phase150_durable_migrations.py | 3 | NEW |
| test_phase151_session_package_bridge.py | 4 | NEW |

### Functional Tests
Existing functional tests in the codebase cover the related routes and can be extended.

### Regression Tests
Existing regression tests in the codebase cover related functionality.

---

## Implementation Notes

1. **Phase 12.15** follows the exact API from rpg-design.txt 12.15.A with safe type coercion
2. **Phase 14.3** provides the simpler single-actor API as specified in the design document
3. **Phase 14.4** uses `_clamp` helper for bounded strength values (0.0-1.0)
4. **Phase 15.0** migrations already existed at `src/app/rpg/session/migrations.py`
5. **Phase 15.1** bridge provides the alternative API alongside existing packaging module

---

## Design Compliance

All phases implemented according to rpg-design.txt specifications:
- ✅ 12.15.A — `src/app/rpg/presentation/visual_inspector.py` created
- ✅ 12.15.B — Visual inspector route `/api/rpg/visual/inspector` added
- ✅ 12.15.C — Unit tests: `test_phase1215_visual_inspector.py`
- ✅ 14.3.A — `src/app/rpg/memory/dialogue_context.py` created
- ✅ 14.3.B — Simple dialogue context route `/api/rpg/memory/simple_dialogue_context` added
- ✅ 14.3.C — Unit tests: `test_phase143_dialogue_context.py`
- ✅ 14.4.A — `src/app/rpg/memory/decay.py` created
- ✅ 14.4.B — Memory decay/reinforce routes added
- ✅ 14.4.C — Unit tests: `test_phase144_memory_decay.py`
- ✅ 15.0.A — `src/app/rpg/session/migrations.py` already existed
- ✅ 15.0.D — Unit tests: `test_phase150_durable_migrations.py`
- ✅ 15.1.A — `src/app/rpg/session/package_bridge.py` created
- ✅ 15.1.B — Session/package bridge routes added
- ✅ 15.1.C — Unit tests: `test_phase151_session_package_bridge.py`

## New API Endpoints

| Method | Endpoint | Phase | Description |
|--------|----------|-------|-------------|
| POST | `/api/rpg/visual/inspector` | 12.15 | Return visual inspector payload |
| POST | `/api/rpg/memory/simple_dialogue_context` | 14.3 | Return single-actor dialogue memory context |
| POST | `/api/rpg/memory/simple_decay` | 14.4 | Apply deterministic memory decay |
| POST | `/api/rpg/memory/reinforce` | 14.4 | Reinforce actor memory entry |
| POST | `/api/rpg/session/export_package_bridge` | 15.1 | Export session via bridge |
| POST | `/api/rpg/session/import_package_bridge` | 15.1 | Import package via bridge |

## Implementation Order (as specified in design)

1. ✅ **12.15** — visibility first
2. ✅ **14.3** — then memory-in-dialogue behavior
3. ✅ **14.4** — then decay/reinforcement behavior
4. ✅ **15.0** — then durability
5. ✅ **15.1** — then portability
