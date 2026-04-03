# Phase 5.3 — LLM Record/Replay Layer

**Date:** 2026-04-02 18:48  
**Status:** Implemented  
**Tests:** 17/17 passing

## Summary

Implemented deterministic LLM-backed execution by recording prompt→response pairs during live runs and replaying them during replay/simulation. This ensures that replay = original execution, eliminating non-determinism from LLM calls.

## Design Goals

1. **Record during live mode**: Capture every LLM prompt and response with context
2. **Replay during simulation**: Use recorded responses instead of calling LLM
3. **Context-aware keys**: Different contexts produce different cache keys
4. **Fail hard on missing**: KeyError if replay without recording (no silent fallback)
5. **Integration with existing systems**: GameLoop, ReplayEngine, BranchEvaluator

## Files Created

### 1. `src/app/rpg/core/llm_recording.py`
Core recording layer with two main classes:

- **LLMRecorder**: Records and replays LLM interactions
  - `make_key(prompt, context)` → stable JSON key
  - `record(prompt, response, context)` → stores interaction
  - `replay(prompt, context)` → retrieves recorded response
  - `load_records(records)` → bulk load for replay sessions

- **DeterministicLLMClient**: Wrapper around any LLM client
  - `complete(prompt, context)` → records or replays
  - `chat(messages, context)` → records or replays
  - `generate(prompt, context)` → records or replays
  - Respects `DeterminismConfig` for mode control

### 2. `src/tests/unit/rpg/test_phase53_llm_recording.py`
Unit tests (8 tests):
- `test_recorder_roundtrip` — record then replay returns same value
- `test_replay_missing_key_raises` — KeyError on missing recording
- `test_deterministic_llm_records_in_live_mode` — live mode records
- `test_deterministic_llm_replays_without_calling_inner` — replay skips LLM
- `test_deterministic_llm_chat` — chat method works
- `test_deterministic_llm_generate` — generate method works
- `test_load_records` — bulk loading works
- `test_recorder_context_differentiation` — different contexts = different keys

### 3. `src/tests/functional/test_phase53_llm_recording_functional.py`
Functional tests (2 tests):
- `test_branch_evaluator_records_then_replays` — end-to-end with AIBranchEvaluator
- `test_branch_evaluator_detailed_evaluation_deterministic` — detailed eval parity

### 4. `src/tests/regression/test_phase53_llm_recording_regression.py`
Regression tests (7 tests):
- `test_replay_without_record_fails_hard` — KeyError, no silent fallback
- `test_record_key_depends_on_context` — context affects key
- `test_multiple_recordings_same_key_override` — last write wins
- `test_deterministic_mode_isolation` — no state leakage between modes
- `test_empty_context_vs_default_context` — None and {} normalization
- `test_complex_context_hashing` — nested structures work
- `test_recorder_load_records_isolation` — load clears previous state

## Files Modified

### 1. `src/app/rpg/core/determinism.py`
Extended `DeterminismConfig` with:
- `record_llm: bool = True` — record LLM responses in live mode
- `use_recorded_llm: bool = False` — use recorded responses in replay mode

### 2. `src/app/rpg/core/__init__.py`
Added exports:
- `LLMRecorder`
- `DeterministicLLMClient`
- `LLMRecord`

### 3. `src/app/rpg/core/game_loop.py`
Added:
- `set_llm_recorder(recorder)` — attach LLM recorder
- `set_mode(mode)` — propagates replay/live mode to subsystems
- Mode propagation to systems with `determinism` attribute

### 4. `src/app/rpg/core/replay_engine.py`
Added:
- LLM replay mode activation during replay
- Disables recorded LLM usage when exiting replay
- Propagates `use_recorded_llm=True` to all subsystems

### 5. `src/app/rpg/ai/branch_ai_evaluator.py`
Modified:
- Constructor accepts `recorder` and `determinism` parameters
- Wraps LLM client with `DeterministicLLMClient`
- Uses `llm.complete()` with context for recording/replay

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      GameLoop.tick()                        │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────┐ │
│  │ WorldSystem  │    │  NPCSystem   │    │ StoryDirector │ │
│  │              │    │              │    │               │ │
│  │ determinism  │    │ determinism  │    │ determinism   │ │
│  │   .replay    │    │   .replay    │    │   .replay     │ │
│  │   .use_llm   │    │   .use_llm   │    │   .use_llm    │ │
│  └──────┬───────┘    └──────┬───────┘    └──────┬────────┘ │
│         │                   │                   │           │
│         └───────────────────┼───────────────────┘           │
│                             │                               │
│                    ┌────────▼────────┐                      │
│                    │ Deterministic   │                      │
│                    │ LLMClient       │                      │
│                    │                 │                      │
│                    │ if replay:      │                      │
│                    │   return rec    │                      │
│                    │ else:           │                      │
│                    │   call inner    │                      │
│                    │   record resp   │                      │
│                    └────────┬────────┘                      │
│                             │                               │
│                    ┌────────▼────────┐                      │
│                    │  LLMRecorder    │                      │
│                    │                 │                      │
│                    │ records: Dict   │                      │
│                    │   key → resp    │                      │
│                    └─────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **Context-aware keys**: Keys include both prompt AND context, so the same prompt with different contexts produces different cache entries.

2. **Fail hard on missing**: During replay, if a recording is missing, `KeyError` is raised. This is intentional — it catches incomplete recordings rather than silently falling back to live LLM.

3. **Mode propagation**: `GameLoop.set_mode("replay")` propagates to all subsystems that have a `determinism` attribute, ensuring consistent behavior.

4. **Wrapper pattern**: `DeterministicLLMClient` wraps any existing LLM client without modifying it, making integration non-invasive.

## Test Results

```
============================= test session starts =============================
collected 17 items

test_phase53_llm_recording.py::TestPhase53LLMRecording::test_deterministic_llm_chat PASSED
test_phase53_llm_recording.py::TestPhase53LLMRecording::test_deterministic_llm_generate PASSED
test_phase53_llm_recording.py::TestPhase53LLMRecording::test_deterministic_llm_records_in_live_mode PASSED
test_phase53_llm_recording.py::TestPhase53LLMRecording::test_deterministic_llm_replays_without_calling_inner PASSED
test_phase53_llm_recording.py::TestPhase53LLMRecording::test_load_records PASSED
test_phase53_llm_recording.py::TestPhase53LLMRecording::test_recorder_context_differentiation PASSED
test_phase53_llm_recording.py::TestPhase53LLMRecording::test_recorder_roundtrip PASSED
test_phase53_llm_recording.py::TestPhase53LLMRecording::test_replay_missing_key_raises PASSED
test_phase53_llm_recording_functional.py::test_branch_evaluator_records_then_replays PASSED
test_phase53_llm_recording_functional.py::test_branch_evaluator_detailed_evaluation_deterministic PASSED
test_phase53_llm_recording_regression.py::test_complex_context_hashing PASSED
test_phase53_llm_recording_regression.py::test_deterministic_mode_isolation PASSED
test_phase53_llm_recording_regression.py::test_empty_context_vs_default_context PASSED
test_phase53_llm_recording_regression.py::test_multiple_recordings_same_key_override PASSED
test_phase53_llm_recording_regression.py::test_record_key_depends_on_context PASSED
test_phase53_llm_recording_regression.py::test_recorder_load_records_isolation PASSED
test_phase53_llm_recording_regression.py::test_replay_without_record_fails_hard PASSED

============================= 17 passed in 0.15s ==============================
```

## Usage Example

```python
from app.rpg.core.llm_recording import LLMRecorder, DeterministicLLMClient
from app.rpg.core.determinism import DeterminismConfig

# Live mode — record LLM responses
recorder = LLMRecorder()
det = DeterminismConfig(record_llm=True, use_recorded_llm=False)
llm = DeterministicLLMClient(inner_llm, recorder, det)

response = llm.complete("Evaluate this branch...", context={"npc": "guard"})
# → Calls inner LLM, records response

# Replay mode — use recorded responses
det_replay = DeterminismConfig(record_llm=False, use_recorded_llm=True)
llm_replay = DeterministicLLMClient(inner_llm, recorder, det_replay)

response = llm_replay.complete("Evaluate this branch...", context={"npc": "guard"})
# → Returns recorded response WITHOUT calling inner LLM
```

## Related Documents

- `rpg-design.txt` — Phase 5.3 specification
- `review-documents/rpg-phase52-deterministic-replay-hardening-20260402-1837.md` — Phase 5.2
- `review-documents/rpg-phase52-deterministic-identity-fixes-20260402-1751.md` — Phase 5.1.5