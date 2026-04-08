# Living World Ambient System — Code Diff Review

## Summary

Full implementation of the living world ambient system across 14 phases. The system advances the RPG simulation autonomously when the player is idle, extracts ambient events (NPC dialogue, world events, arrivals/departures, combat), scores them for salience, filters for player visibility, coalesces repetitive updates, and delivers them to the frontend via SSE/polling with professional rendering.

## Files Changed

| File | Change | Lines |
|------|--------|-------|
| `src/app/rpg/session/ambient_builder.py` | **New** | 362 |
| `src/app/rpg/ai/ambient_dialogue.py` | **New** | 278 |
| `src/app/rpg/session/ambient_policy.py` | **New** | 128 |
| `src/app/rpg/session/runtime.py` | Modified | +96 |
| `src/app/rpg/session/migrations.py` | Modified | +12 |
| `src/app/rpg/session/service.py` | Modified | +6 |
| `src/app/rpg/ai/world_scene_narrator.py` | Modified | +155 |
| `src/app/rpg/api/rpg_session_routes.py` | Modified | +169 |
| `src/static/rpg/rpg.js` | Modified | +343 |
| `src/static/style.css` | Modified | +100 |
| `src/tests/unit/rpg/test_living_world.py` | **New** | 740 |
| `src/tests/unit/rpg/test_phase183b_integration.py` | Modified | +2/-2 |

**Total: ~2,200 lines added across 12 files (3 new backend, 1 new test, 8 modified)**

---

## Architecture Overview

```
                    ┌──────────────────────┐
                    │    Frontend (rpg.js)  │
                    │  SSE / Poll / Heartbeat│
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Session Routes      │
                    │  idle_tick / poll /   │
                    │  stream / resume      │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Runtime (runtime.py)│
                    │  apply_idle_tick()    │
                    │  apply_idle_ticks()   │
                    │  apply_resume_catchup │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼──────┐ ┌──────▼──────┐ ┌───────▼───────┐
     │ Ambient Builder│ │ Ambient     │ │ Ambient       │
     │ (extraction,  │ │ Dialogue    │ │ Policy        │
     │  salience,    │ │ (candidates,│ │ (interrupt,   │
     │  coalesce,    │ │  cooldowns) │ │  classify)    │
     │  queue)       │ │             │ │               │
     └───────────────┘ └─────────────┘ └───────────────┘
              │
     ┌────────▼──────┐
     │ Narrator      │
     │ (template +   │
     │  LLM ambient) │
     └───────────────┘
```

---

## Detailed Diff Analysis

### 1. `src/app/rpg/session/ambient_builder.py` (NEW — 362 lines)

**Purpose:** Core ambient update system — extraction, scoring, filtering, coalescing, queueing.

**Key functions:**
- `make_ambient_update(**kwargs)` — Factory with guaranteed field defaults
- `ensure_ambient_runtime_state()` / `normalize_ambient_state()` — State normalization with hard caps
- `build_ambient_updates(before, after, runtime)` — Extracts new events, NPC decisions, faction changes, incidents
- `score_ambient_salience(update, context)` — Deterministic scoring (location, target, NPC proximity, urgency, repetition penalty)
- `is_player_visible_update(update, session)` — Filters omniscient leaks, distant events
- `coalesce_ambient_updates(updates, runtime)` — Merges: NPC chatter capped to 2, low-priority world events summarized
- `enqueue_ambient_updates()` / `get_pending_ambient_updates()` / `acknowledge_ambient_updates()` — Queue CRUD with seq numbering

**Hard caps (all configurable):**
- `_MAX_AMBIENT_QUEUE = 32`
- `_MAX_RECENT_AMBIENT_IDS = 64`
- `_MAX_IDLE_TICKS_PER_REQUEST = 6`
- `_MAX_RESUME_CATCHUP_TICKS = 12`
- `_MAX_AMBIENT_BATCH_PER_DELIVERY = 8`

**Review notes:**
- All extraction is diff-based (before vs after state) — no false positives
- Salience bounded to [0.0, 3.0]
- Queue respects FIFO with seq-based dedup

---

### 2. `src/app/rpg/ai/ambient_dialogue.py` (NEW — 278 lines)

**Purpose:** NPC ambient dialogue engine — deterministic candidate generation with cooldowns.

**Key functions:**
- `build_ambient_dialogue_candidates(sim, runtime, player_ctx)` — Generates dialogue candidates from NPC minds, beliefs, goals
- `select_ambient_dialogue_candidate(candidates, runtime)` — Cooldown-aware deterministic selection (sorted by salience then speaker_id)
- `apply_dialogue_cooldowns(runtime, candidate)` — Records speaker/kind/pair cooldowns
- `build_ambient_dialogue_request(candidate, session_ctx)` — Builds payload for narration

**Cooldown constants:**
- Speaker: 3 ticks between same NPC speaking
- Kind: 2 ticks between same dialogue type
- Pair: 5 ticks between same speaker→target pair

**Review notes:**
- Deterministic: sorted iteration over npc_index keys
- Suppresses chatter during active encounters
- Only one NPC-to-NPC candidate per speaker per tick
- Companion/gossip detection via NPC role field

---

### 3. `src/app/rpg/session/ambient_policy.py` (NEW — 128 lines)

**Purpose:** Interruption policy and delivery classification.

**Key functions:**
- `should_interrupt_player(session, update)` — Combat/warning always interrupt; gossip/system never; rate-limited to 3-tick minimum gap
- `classify_ambient_delivery(session, update, is_typing)` — Returns `"interrupt"`, `"badge"`, or `"silent"`
- `record_interrupt(session, update)` — Records last interrupt tick for rate limiting

**Review notes:**
- Combat bypasses rate-limit
- Typing awareness downgrades non-urgent interrupts to badges
- Medium priority (≥0.4) shows badge; low priority is silent

---

### 4. `src/app/rpg/session/runtime.py` (MODIFIED — +96 lines)

**Changes:**
- Schema version bumped `3 → 4`
- New imports from `ambient_builder`
- `build_session_from_start_result()` — Adds ambient state defaults to new sessions
- `apply_turn()` — Records `last_player_turn_at`, resets `idle_streak`
- **New:** `_advance_simulation_for_idle()` — Steps simulation without player action
- **New:** `apply_idle_tick(session_id)` — Full idle tick pipeline: advance → extract → filter → score → coalesce → enqueue → persist
- **New:** `apply_idle_ticks(session_id, count)` — Multi-tick with clamping
- **New:** `apply_resume_catchup(session_id, elapsed_seconds)` — Bounded catch-up with excess summarization
- Replay safety: idle ticks recorded in `llm_records`/`llm_records_index`, consumed in replay mode

**Review notes:**
- Reuses existing `step_simulation_state()` — no simulation logic duplication
- Each idle tick loads/saves canonical session (consistent with apply_turn pattern)
- Replay mode raises RuntimeError-style returns on missing captured data

---

### 5. `src/app/rpg/ai/world_scene_narrator.py` (MODIFIED — +155 lines)

**Changes (appended to end):**
- `_AMBIENT_TEMPLATES` dict — Template strings for 13 ambient kinds
- `_AMBIENT_PROMPTS` dict — LLM prompt templates for 6 key kinds
- `narrate_ambient_update(ambient_update, simulation_state, current_scene, llm_gateway)` — LLM with template fallback

**Review notes:**
- LLM only styles phrasing — never invents world truth (prompt says "ONLY with the spoken line")
- `_bound_text()` limits LLM output to 250 chars
- Error responses (`[ERROR:`) trigger fallback
- Speaker turns tagged with `"ambient": True` for frontend differentiation

---

### 6. `src/app/rpg/api/rpg_session_routes.py` (MODIFIED — +169 lines)

**New endpoints:**
- `POST /api/rpg/session/idle_tick` — Advance world by N idle ticks (capped)
- `POST /api/rpg/session/poll` — Long-poll for ambient updates after a seq
- `GET /api/rpg/session/stream` — Persistent SSE stream with heartbeats
- `POST /api/rpg/session/resume` — Bounded catch-up on reconnect

**Turn payload enrichment:**
- `ambient_updates`, `latest_ambient_seq`, `unread_ambient_count` added to turn response

**Review notes:**
- SSE stream uses `asyncio.sleep` loop (max ~50 minutes)
- Heartbeats every 5 seconds with latest seq
- All endpoints validate `session_id`, return appropriate HTTP status codes

---

### 7. `src/static/rpg/rpg.js` (MODIFIED — +343 lines)

**New state fields:** `sessionStream`, `ambientSeq`, `unreadAmbient`, `isTyping`, `heartbeatTimer`, `pollTimer`, `ambientFeedBuffer`

**New functions:**
- `connectSessionStream()` / `disconnectSessionStream()` — SSE with auto-reconnect (max 10 attempts)
- `startAmbientHeartbeat()` / `stopAmbientHeartbeat()` — 5s interval idle_tick calls
- `startAmbientPolling()` / `stopAmbientPolling()` — Fallback polling (6s interval)
- `handleAmbientUpdate(update)` — Dedup by seq, typing-aware buffering
- `appendAmbientUpdate(update)` — Renders card + triggers TTS
- `renderAmbientCard(update)` — Kind-specific rendering (NPC speech, arrival, combat, warning, etc.)
- `updateUnreadBadge()` / `flushAmbientBuffer()` — Badge management
- `startLivingWorld()` — Master entry: resume → heartbeat → SSE → typing detection
- `stopLivingWorld()` — Clean shutdown

**Integration points:**
- `loadGame()` → `startLivingWorld()`
- Adventure Builder launch callback → `startLivingWorld()`
- First turn completion → `startLivingWorld()`
- `init()` → `startLivingWorld()` (if session exists)
- `resetSession()` → `stopAmbientHeartbeat()` + `disconnectSessionStream()`

**Review notes:**
- EventSource with exponential backoff reconnect
- `document.hidden` check prevents ticking when tab is background
- localStorage `omnix_rpg_last_activity` for resume elapsed calculation
- Public API extended with debug helpers: `startLivingWorld`, `stopLivingWorld`, `flushAmbient`, `pollAmbient`

---

### 8. `src/static/style.css` (MODIFIED — +100 lines)

**New CSS classes:**
- `.rpg-ambient` — Base ambient card with left-border, fade-in animation
- `.rpg-ambient--{kind}` — Kind-specific colors (blue=NPC-to-player, purple=NPC-to-NPC, green=arrival/departure, red=combat, amber=warning, cyan=companion, gray=system)
- `.rpg-ambient-speaker/says/text/urgent/summary/time` — Inner element styling
- `.rpg-ambient-badge` — Unread count badge with pulse animation

---

### 9. `src/app/rpg/session/migrations.py` (MODIFIED — +12 lines)

**Change:** Added v3→v4 migration that adds all ambient runtime state fields to existing sessions.

---

### 10. `src/app/rpg/session/service.py` (MODIFIED — +6 lines)

**Change:** `create_or_normalize_session()` now calls `ensure_ambient_runtime_state()` + `normalize_ambient_state()` on every session load.

---

### 11. `src/tests/unit/rpg/test_living_world.py` (NEW — 740 lines)

**62 tests across 14 classes:**
- `TestAmbientUpdateContract` (3 tests) — Field presence, defaults, unknown key rejection
- `TestEnsureAmbientRuntimeState` (3 tests) — Empty/existing/null input handling
- `TestNormalizeAmbientState` (3 tests) — Queue/IDs/cooldowns bounded trimming
- `TestBuildAmbientUpdates` (4 tests) — Event extraction, NPC arrival, no-change, combat detection
- `TestSalienceScoring` (4 tests) — Location bonus, player target, repetition penalty, bounds
- `TestVisibilityFilter` (4 tests) — NPC-to-player visible, distant filtered, system visible, low-priority filtered
- `TestCoalescing` (4 tests) — Chatter capped, low-world merged, high-priority preserved, empty input
- `TestAmbientQueue` (7 tests) — Seq assignment, increment, bounds, pending, limit, acknowledge, metrics
- `TestBuildDialogueCandidates` (3 tests) — Nearby NPC, hostile NPC, distant NPC
- `TestDialogueCooldowns` (4 tests) — Speaker cooldown, salience selection, cooldown application, deterministic ordering
- `TestDialogueRequest` (1 test) — Request structure
- `TestInterruptionPolicy` (6 tests) — Combat/gossip/system/NPC/rate-limit/warning
- `TestDeliveryClassification` (4 tests) — Typing combat, typing badge, silent, medium badge
- `TestRecordInterrupt` (1 test) — State recording
- `TestAmbientNarration` (6 tests) — Template fallback, world event, summary, LLM path, LLM error, dialogue kinds
- `TestMigration` (3 tests) — v3 migration, v4 no-change, service normalize
- `TestHardCaps` (2 tests) — Positive integers, delivery limit

**Run command:** `cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_living_world.py -v --noconftest`

---

## Potential Review Points

1. **Idle tick frequency:** Currently hardcoded to 5s frontend heartbeat. Should this be configurable per-session?
2. **SSE stream lifetime:** 50-minute max loop. Consider reconnect-on-close for longer sessions.
3. **Queue persistence cost:** Each idle tick loads + saves full session. For high-frequency ticks, consider batch persistence.
4. **Ambient update retention:** Queue capped at 32. Older updates are lost. Consider archival for session replay.
5. **LLM cost:** Each ambient narration with LLM costs a call. The template fallback path is always available.
