# RPG Game Architecture and Source Map

## 1. Purpose and Scope

This document is the source-aligned architecture and feature map for the RPG system under `src/app/rpg`. It covers both the high-level design and the concrete feature ownership model used by the current implementation. It should be kept current whenever a bundle adds, removes, or moves gameplay, runtime, LLM, reporting, or persistence behavior.

The RPG is designed as a deterministic game runtime with AI-assisted interpretation and presentation. The core rule is simple: **simulation state is truth; LLM output is advisory or presentational unless deterministic runtime code explicitly resolves it into state**.

The system supports:

- Human-playable interactive turns.
- Interactive CLI / matrix regression scenarios.
- Manual service scenarios.
- Long autoplay campaigns.
- Rich HTML/JSON reports.
- Deterministic combat, travel, service, economy, survival, party, story, and memory systems.
- LLM first-call intent extraction and persona-rich dialogue.
- Deferred / deterministic / blocking narration modes.
- NPC profiles, biography, memory, relationship, and evolution arcs.
- Provider-independent LLM integration.

## 2. Non-Negotiable Architecture Rules

### 2.1 Runtime Is Authoritative

Authoritative game facts must come from deterministic runtime code. This includes:

- Player location.
- Inventory and currency.
- Service purchases.
- Shop stock and prices.
- Combat HP, damage, defeat, and combat end state.
- Quest state, objectives, and rewards.
- Rumors and world events.
- NPC memory and relationship state.
- Party and companion state.
- Survival values such as hunger, thirst, fatigue, rations, and water.
- Save/load state.

LLM text can describe or classify, but cannot directly create those facts.

### 2.2 LLM Is Bounded

The LLM can:

- Classify natural-language intent.
- Suggest a bounded action advisory.
- Produce non-stateful persona dialogue when the grounding packet supports it.
- Produce deferred narration after deterministic resolution.
- Assist with grounding diagnostics.

The LLM must not:

- Decide hit/miss, damage, HP, XP, rewards, prices, inventory mutation, travel success, quest completion, or final state.
- Invent backed quests or rumors.
- Reveal private NPC context unless runtime exposes it.
- Override runtime state with older memory/profile details.

### 2.3 Runtime Before Narration

The normal stateful flow is:

```text
player input
  -> interactive first-call runtime
  -> optional fast-direct deterministic action
  -> optional first-call LLM advisory
  -> canonical runtime state mutation
  -> narration contract
  -> deterministic/deferred/provider narration
  -> UI/report result
```

Narration is always downstream of state resolution for stateful turns.

### 2.4 Harnesses Do Not Own Gameplay

Manual scenario harnesses, CLI runners, and matrix tests are entry surfaces and reporting layers. They must not implement alternate gameplay shortcuts. CE.2.13 removed the old harness fast-direct route so fast-direct combat, survival, and travel now run through `app.rpg.session.interactive_first_call_runtime.apply_turn`.

### 2.5 Every Fallback Needs a Source

Repairs and fallbacks must expose source fields. Examples:

- `deterministic_combat_fast_summary`
- `deferred_runtime_narration_pending`
- `authoritative_runtime_result`
- `quest_repaired`
- `rumor_repaired`
- `dialogue_repaired`
- `survival_repaired`
- `fast_direct_runtime`

This lets reports explain what happened and why.

## 3. Source-Aligned Module Map

This section maps `src/app/rpg` by architectural responsibility. When adding features, update the section for the owning module area and include any new state contract, source field, and test/report impact.

### 3.1 `src/app/rpg/session/*` — Session Runtime, Turn Orchestration, Persistence, Narration Contracts

This is the central runtime area. It owns the player turn lifecycle, persistent session loading/saving, first-call wrapper path, narration mode contract, fast-combat skip hooks, grounding packets, tracing, and frontend payload shape.

Important modules and responsibilities:

| Module | Responsibility | Deterministic / LLM Boundary |
|---|---|---|
| `session/runtime.py` | Canonical RPG session runtime. Loads/saves sessions, executes player turns, resolves gameplay through deterministic runtime systems, shapes frontend/bootstrap payloads, applies final visible presentation selection, combat narration selection, repairs stale visible result text, and coordinates provider narration when allowed. | Deterministic authority. May call LLM only for bounded narration paths; state mutation remains runtime-owned. |
| `session/interactive_first_call_runtime.py` | Player-facing two-call wrapper. Selects sessions, detects fast-direct actions, builds first-call action/semantic advisories, consumes safe non-stateful dialogue, routes stateful actions to canonical runtime, attaches first-call diagnostics, applies narration contracts. | LLM advisory before runtime; deterministic runtime for state. Fast-direct bypasses provider calls but still routes state mutation through canonical runtime. |
| `session/turn_grounding.py` | Builds grounded turn packets with player input, candidate action, scene, active modes, addressed NPCs, nearby NPCs, authoritative player/combat/quest state, rich NPC biography/personality/relationship/inventory/knowledge boundaries, private-context flags, and LLM safety rules. | Supplies bounded context. Does not mutate state. |
| `session/first_call_dialogue.py` | Builds safe non-stateful dialogue results from first-call visible responses when no runtime mutation is needed. | Allows LLM dialogue only when non-stateful and grounded. |
| `session/fast_combat_narration_skip.py` | Installs runtime hook to skip blocking synchronous combat narration in fast-direct mode. Marks deterministic combat narration payloads and source fields, wraps `apply_turn` to carry fast-combat skip context, and preserves non-fast provider behavior. | Performance/grounding hook. Does not change combat state. |
| `session/deferred_narration_guard.py` | Guards against unwanted provider narration during deferred or suppressed narration paths. | Prevents unexpected blocking LLM calls. |
| `session/narration_trace.py` | Records narration trace events and stack checkpoints for diagnostics. | Diagnostic only. |
| `session/turn_perf_trace.py` | Records turn-stage timing and performance traces. | Diagnostic only. |
| `session/session_store.py` | Session registry and in-memory/session lifecycle utilities such as get/list/save/archive. | Persistence support. |
| `session/durable_store.py` | Disk-backed durable session persistence, listing, loading, and saving. | Persistence support. |
| `session/__init__.py` | Session package exports and optional hook installation, including fast combat narration skip installation. | Package integration. |

Key runtime entrypoints:

```text
interactive_first_call_runtime.apply_turn(...)
runtime.apply_turn(...)
runtime.load_runtime_session(...)
runtime.save_runtime_session(...)
build_turn_grounding_packet(...)
force_install_fast_combat_narration_skip_for_tests(...)
```

Design constraints:

- App/CLI/matrix should prefer `interactive_first_call_runtime.apply_turn`.
- Canonical runtime remains the state authority.
- Fast-direct action detection belongs in the app wrapper, not the harness.
- Runtime narration cannot mutate state.
- Combat fast mode must not call synchronous combat provider narration.

### 3.2 `src/app/rpg/ai/*` — First-Call Intent, Semantic Advisory, and Structured LLM Classification

The AI directory owns bounded first-call interpretation. It should never own authoritative game outcome logic.

Important modules and responsibilities:

| Module | Responsibility | Boundary |
|---|---|---|
| `ai/action_intelligence.py` | Builds the first-call action-intelligence prompt, attaches grounding diagnostics, normalizes advisory JSON, merges advisory metadata into candidate actions, and restricts action types/difficulties/skills to explicit allowed sets. | LLM advisory only. Cannot resolve outcomes. |
| `ai/semantic_action_intelligence.py` | Semantic action advisory path for broader interpretation and current-turn-first classification. Helps route player text while keeping runtime authoritative. | LLM advisory only. |

Allowed first-call outputs include:

- `action_type`
- `difficulty`
- `skill_id`
- `intent_tags`
- `narrative_goal`
- `target_id`
- `target_name`
- `stateful`
- `needs_runtime_resolution`
- `visible_response` for non-stateful dialogue
- `reason`

The AI layer must attach diagnostics such as:

- Prompt preview.
- Raw text length.
- Provider called/parse status.
- Turn grounding packet.
- Normalized advisory.
- Provider error if any.

### 3.3 `src/app/rpg/interactions/*` — General Interaction Runtime

The interactions layer resolves non-specialized gameplay interactions and dispatches to deterministic interaction subsystems.

Important ownership:

- Detect interaction intent.
- Resolve general interactions.
- Route item/container/repair/consumable/crafting/merchant/loot/combat-like interaction results into a consistent visible reason.
- Produce deterministic interaction result payloads that runtime can patch into visible narration/result fields.

Known integration points:

```text
from app.rpg.interactions.resolver import detect_interaction_intent
from app.rpg.interactions.resolver import resolve_general_interaction
```

Design constraints:

- Interaction result reasons must be deterministic and visible.
- Stale result text such as `unknown_item` or `item_not_found` must be replaced by the current interaction reason when the interaction resolver has a better authoritative result.
- Interaction resolution must not depend on LLM narration.

### 3.4 `src/app/rpg/core/*` — Determinism, Event Bus, State Contracts, Boundaries, Effects

The core layer is the deterministic substrate. It supports reproducibility, event ordering, state boundary validation, effect application, replay, and sandbox execution.

Important modules and responsibilities:

| Module | Responsibility |
|---|---|
| `core/determinism.py` | Deterministic helpers and reproducibility utilities. |
| `core/event_bus.py` | Event dispatch and deterministic event ordering. |
| `core/state_contracts.py` | State contract definitions and expected boundaries. |
| `core/effects.py` | Structured effect application patterns. |
| `core/state_boundary_validator.py` | Validation that state mutations respect declared boundaries. |
| `core/__init__.py` | Core exports. |

Design constraints:

- Lower-priority event handlers should run first when ordering matters.
- Combat HP mutations must happen before downstream emotion/memory/scene updates that depend on damage/death facts.
- Replay and save/load depend on deterministic IDs, clocks, and effect ordering.

### 3.5 `src/app/rpg/systems/*` — Event-Driven RPG Systems

The systems layer is the event-driven runtime feature layer. It should use deterministic event ordering and explicit state updates.

Known ordering model:

```text
combat priority -10: mutates HP first
emotion priority 0: reacts to facts after combat
action/scene priority 5: updates scene/action consequences
memory priority 10: records perceived facts
debug priority 20: logs after state changes
```

Feature responsibilities:

- Combat consequences.
- NPC emotional reactions.
- Scene changes.
- Memory capture.
- Debug/trace systems.

Design constraints:

- Systems should consume events, not infer facts from narration.
- Systems should apply bounded effects and expose diagnostic output.
- Systems must avoid non-deterministic ordering.

### 3.6 `src/app/rpg/memory*` and NPC Memory Modules — Memory, Beliefs, Relationships, Prompt Context

NPC memory is a major RPG pillar. The memory layer records meaningful perceived events and retrieves them for planning, dialogue, and relationship state.

Important modules and responsibilities:

| Module | Responsibility |
|---|---|
| `memory_system.py` | Records perceived events into NPC memory, validates events, applies spatial filtering, updates relationships, integrates beliefs, handles damage/death/heal/dialogue, and centralizes entity lookup to avoid drift. |
| `memory_context.py` | Builds LLM memory context from relevant retrieved memories, relationship summaries, and beliefs. Prioritizes recent/relevant memories for planning or dialogue prompts. |

Memory features:

- Event validation.
- Spatial filtering.
- Relationship updates.
- Belief integration.
- Important memory marking.
- Recent relevant memory retrieval.
- Dialogue and planning context formatting.
- Avoidance of fake environment memories.

Design constraints:

- Environment-only targets must not create fake NPC social memories.
- Memory should be backed by perceived events or explicit runtime facts.
- Memory can inform LLM persona/context but cannot override current authoritative runtime state.

### 3.7 `src/app/rpg/npc*`, NPC Profiles, Biography, Persona, and Evolution

NPC features are spread across runtime state, profile loading, memory, story director, and grounding packet construction. The architectural contract is that NPCs have deterministic state and profile-backed persona.

NPC profile fields should include:

- NPC ID.
- Name.
- Role.
- Home/current location.
- Public biography.
- Private biography/secrets.
- Personality summary.
- Traits, values, fears.
- Speech style.
- Speech/dialogue examples.
- Relationship to player.
- Inventory/visible equipment/private inventory.
- Knowledge boundaries.
- Capabilities and skills.
- Merchant/service behavior when applicable.
- Party/companion status.
- Evolution arc state.

Current grounding integration:

- `turn_grounding.py` extracts addressed NPCs from player input and present NPC state.
- It builds rich profiles from runtime NPC data and optional profile loader data.
- It passes private fields only as private adjudication context with explicit no-reveal rules.
- First-call prompts can use persona and biography for non-stateful dialogue or intent classification.

Design constraints:

- NPCs should feel like people through biography, memory, relationship, and speech style.
- The LLM can roleplay an NPC only inside backed boundaries.
- NPC evolution must be triggered by backed world events or explicit arc state, not freeform narration.

### 3.8 `src/app/rpg/director.py` and Story/Arc Modules — Story Direction and Character Arcs

The story director manages long-term narrative progression. It should operate on state-backed arcs and memory patterns, not ad hoc LLM invention.

Known arc patterns:

- Revenge arcs can trigger from repeated damage or ally death.
- Alliance arcs can trigger from repeated healing or positive support.
- Duplicate arcs should be checked by originator, target, and type.

Story director responsibilities:

- Seed or advance arcs.
- Track originator/target/type.
- Avoid duplicate arcs.
- Connect world events to story beats.
- Surface active objectives or pressure.
- Preserve deterministic pacing under seeded runs.

Design constraints:

- Story arcs must have explicit state.
- NPC emotional/personality evolution must reference backed events.
- Reports should show arc phase, triggers, and progression.

### 3.9 `src/app/rpg/world_scene_narrator.py` and Narration Modules — Scene/Narrative Presentation

The world scene narrator and runtime narration code produce structured narrative output. They must use schema/versioned payloads and preserve raw LLM output for diagnostics.

Narration responsibilities:

- Build structured narration requests.
- Parse structured narration JSON.
- Preserve raw narrative text.
- Provide deterministic fallback behavior when provider output is missing, malformed, or ungrounded.
- Attach source fields and validation state.

Design constraints:

- Narration output is presentation, not state mutation.
- Structured narration should include a schema/version marker such as `rpg_narration_v2` where applicable.
- Runtime must be able to ignore or repair narration when it conflicts with state.

### 3.10 `src/app/rpg/llm_app_gateway.py` and Provider Integration

The provider gateway isolates gameplay code from provider-specific APIs.

Responsibilities:

- Build the active app LLM gateway.
- Route completion or JSON-completion calls to the configured provider.
- Keep provider selection centralized.
- Support provider swaps without changing runtime mechanics.

Provider-related implementation may include OpenRouter, LM Studio, OpenAI-compatible, Cerebras, or other active app providers. Runtime code should call the central gateway rather than hardcoding a provider.

Design constraints:

- Provider calls must include purpose-specific prompts.
- Provider failures should produce explicit diagnostics.
- Gameplay must remain valid when provider calls fail.
- Tests should distinguish provider-call requirements from deterministic runtime requirements.

### 3.11 Replay, Snapshot, Sandbox, and Game Loop Modules

The broader RPG app includes runtime infrastructure for replay, snapshot validation, sandbox execution, and game loop state boundaries.

Important module responsibilities:

| Module | Responsibility |
|---|---|
| `game_loop.py` | Orchestrates loop-level runtime execution and state transitions where used. |
| `replay_engine.py` | Replays events/turns for determinism validation. |
| `snapshot_manager.py` | Stores and loads snapshots/checkpoints. |
| `simulation/sandbox.py` | Runs bounded simulation experiments or isolated checks. |

Design constraints:

- Replay must not depend on fresh LLM calls for deterministic state.
- Snapshots must include all state needed to continue gameplay.
- Sandbox execution must respect state boundaries.
- Long autoplay readiness depends on checkpoint validation.

### 3.12 Frontend/API Shape and UI Payloads

The runtime shapes bootstrap and turn payloads for the frontend. UI-facing payloads should include:

- Visible narration.
- NPC speaker/line.
- Player state.
- Location/scene state.
- Inventory/currency.
- Combat state.
- Quest/journal state.
- Party state.
- World events.
- Warnings and diagnostics when debug is enabled.

Design constraints:

- UI should render authoritative result fields, not infer state from prose.
- UI should expose optional scene/portrait/TTS buttons without changing state.
- UI should support deferred narration updates where available.

## 4. Feature Ownership Matrix

| Feature | Owning runtime area | LLM role | Report/test signals |
|---|---|---|---|
| Player turn execution | `session/interactive_first_call_runtime.py`, `session/runtime.py` | Intent advisory and narration only | turn contract, result source, timings |
| Grounded first-call packet | `session/turn_grounding.py` | Receives bounded context | prompt preview, grounding diagnostics |
| Non-stateful dialogue | `session/first_call_dialogue.py`, `ai/*` | Can generate persona line if safe | `first_call_visible_response_selection`, NPC line |
| Stateful action resolution | `session/runtime.py`, interactions/core systems | No state authority | resolved_result, authoritative payload |
| Fast combat | `interactive_first_call_runtime.py`, `fast_combat_narration_skip.py`, `runtime.py` | Skipped in fast mode | combat avg ~0.06-0.10s, `llm_turn_count=0` |
| Combat HP/damage/defeat | canonical runtime / combat systems | Narration only | combat progress rows, HP before/after |
| Combat narration | `runtime.py`, `fast_combat_narration_skip.py` | Optional provider narration when not fast | `combat_narration_payload`, source fields |
| Survival | interactive fast-direct + canonical runtime | Usually none in fast mode | survival repaired/source, provision state |
| Travel | interactive fast-direct + canonical runtime | Narration after route validation | location/destination result source |
| Commerce/services | canonical runtime + repair paths | Clarifies intent only | price/stock/currency deltas, service_kind |
| Quest inquiry | canonical quest/work inquiry repair | May classify request | no-backed quest source if absent |
| Rumor/news inquiry | rumor repair path | May classify request | backed rumor/no-backed source |
| Party/companions | canonical runtime and party state | Dialogue only | companion acceptance, party summary |
| NPC persona | profiles + `turn_grounding.py` + memory | Roleplay within boundaries | addressed NPC context, NPC speaker/line |
| NPC memory | memory modules/systems | Prompt context only | memory rows, relationship deltas |
| Story arcs | director/arc state | Presentation only | arc phase, beat history, progression |
| World events | runtime/systems/director | Presentation only | event list, rumor seeds, journal |
| Narration validation | narration/grounding validator | Checks/repairs LLM text | warnings, fallback source |
| Persistence | session store/durable store/snapshots | None | save/load checkpoint validation |
| Reports | tests/manual/autoplay reporting | Displays diagnostics | HTML/JSON artifacts |

## 5. End-to-End Turn Pipeline

### 5.1 Fast Deterministic Turn

```text
1. UI/CLI/test passes player input to interactive_first_call_runtime.apply_turn.
2. Runtime checks fast_turn_mode.
3. Runtime detects narrow fast-direct action.
4. Runtime builds deterministic action + first-call diagnostics.
5. Canonical runtime resolves state.
6. Provider calls are disabled or skipped.
7. Deterministic/deferred narration payload is attached.
8. Result returns with source fields and performance trace.
```

Examples:

- `I attack the bandit.` -> combat action against `enemy:road_bandit`, skip sync combat narration.
- `I drink water from my waterskin.` -> survival/provision action.
- `I continue along the road toward the old mill.` -> travel action.

### 5.2 LLM-Assisted Stateful Turn

```text
1. Player input enters interactive runtime.
2. First-call action/semantic intelligence receives grounded packet.
3. Advisory classifies target/action and marks stateful.
4. Runtime constructs bounded action metadata.
5. Canonical runtime resolves state.
6. Narration contract prevents first-call text from mutating state.
7. Deferred or provider narration presents resolved result.
```

Examples:

- Asking for food or price.
- Asking Bran for a quest.
- Asking for rumors/news.
- Ambiguous social or investigative action.

### 5.3 Non-Stateful NPC Dialogue Turn

```text
1. Player addresses NPC.
2. Grounding packet supplies persona, biography, relationship, scene, memory, and knowledge boundaries.
3. First-call advisory marks stateful=false and supplies visible_response.
4. first_call_dialogue builds safe dialogue result.
5. Runtime returns without mutating authoritative state.
```

Examples:

- `Bran, who are you?`
- `What do you know about this place?`

The response may be rich and persona-aware, but must not reveal private context or invent backed quests/rumors.

## 6. State Model

### 6.1 Session

A session contains:

- `manifest`: session ID and metadata.
- `simulation_state`: authoritative world/player/NPC state.
- `runtime_state`: operational turn state, settings, combat state, diagnostics.
- journal/recap state.
- world events.
- report/artifact metadata.

### 6.2 Simulation State

Authoritative long-lived game facts:

- player state.
- current location.
- inventory/currency.
- stats/skills/XP.
- active/completed quests.
- NPC profiles/social state.
- party state.
- story arcs.
- world events/rumors.
- faction/reputation.
- survival state.

### 6.3 Runtime State

Operational and transient data:

- current turn index.
- runtime settings.
- narration mode.
- combat state.
- pending/deferred narration jobs.
- fast-direct flags.
- first-call diagnostics.
- performance trace.
- recent turn history.

### 6.4 Turn Contract

A turn contract should capture:

- raw player input.
- candidate/final action type.
- target IDs/names.
- requested terms.
- service kind.
- resolved result.
- narration source/status.
- diagnostics and fallbacks.

## 7. Major Gameplay Systems

### 7.1 Combat

Combat is deterministic. Runtime owns:

- Combat start/end.
- Participants and sides.
- HP before/after.
- Damage applied.
- Actor/target IDs.
- Defeat flag.
- Combat log/progress rows.

LLM narration cannot decide damage or defeat. In fast mode, `fast_combat_narration_skip.py` prevents blocking provider narration and exposes deterministic source payloads.

### 7.2 Economy, Commerce, and Services

Economy is deterministic. Runtime owns:

- Canonical prices.
- Shop/service availability.
- Room/meal purchase rules.
- Currency deltas.
- Inventory mutation.
- Failure reasons.

LLM may classify the request but cannot invent stock or prices.

### 7.3 Travel and Locations

Travel is deterministic. Runtime owns:

- Valid route selection.
- Destination preservation.
- Location transition.
- Travel failure reasons.
- Location history/report data.

Narration describes the route only after validation.

### 7.4 Survival

Survival includes hunger, thirst, fatigue, water, rations, and resource pressure. Fast-turn survival checks can bypass provider calls.

### 7.5 Party and Companions

Party state includes:

- Companion IDs/names.
- Roles.
- Follow mode.
- Recruitment offer/acceptance state.
- Companion presence in final party state.
- Companion dialogue and relationship state.

Companion acceptance must be backed by deterministic state.

### 7.6 Quests, Work, Rumors, and News

Quests and rumors must be backed by state. If none exist, the runtime should return a no-backed-state response rather than inventing a job or rumor.

### 7.7 NPC Memory, Persona, and Evolution

NPCs should have:

- Rich biography and personality.
- Speech style examples.
- Relationship/memory state.
- Knowledge boundaries.
- Evolution arcs.

NPC evolution is state-backed. Example: Bran can evolve from innkeeper to companion/adventurer only after backed events and party/runtime state support it.

## 8. Reporting and Diagnostics

Reports are product-quality debugging tools. They should expose:

- Scenario and turn list.
- Player input.
- Final classification.
- Raw/result keys.
- Narration source.
- NPC speaker/line.
- First-call prompt/diagnostics.
- Grounding packet.
- Runtime narration diagnostics.
- Provider called / parse status.
- Token usage.
- Warnings/fallbacks.
- Combat progress rows.
- Party progress rows.
- Performance phase timings.
- Slow turn lists.
- Story arcs, journal, locations, inventory, economy, and world events.

The interactive intent matrix is the main regression suite for interactive behavior. The current expected matrix covers:

- commerce food purchase.
- no-backed quest inquiry.
- no-backed rumor/news inquiry.
- survival food/water.
- NPC persona dialogue.
- combat basic attack.
- travel route choice.
- party companion recruitment.

## 9. Test Architecture

Important current test families:

| Test family | Purpose |
|---|---|
| `test_ce2121_fast_combat_narration_skip.py` | Verifies fast combat skip, source fields, install behavior, non-fast provider preservation. |
| `test_ce213_runtime_harness_convergence.py` | Verifies manual harness prefers `interactive_first_call_runtime`, old harness fast-direct routing is gone, and fast-direct detection lives in app runtime. |
| interactive intent matrix | End-to-end CLI/matrix behavior and performance. |
| manual service scenarios | Focused service, combat, NPC, dialogue, memory, rumor, party, and quest validations. |
| autoplay campaign tests | Long-run coverage, report quality, loop detection, performance, and progression checks. |

Regression rules:

- Unit tests should cover helper behavior and source fields.
- Matrix must validate realistic player-facing commands.
- Live-provider matrix validates real latency and provider behavior.
- Long autoplay catches loops, stale prompts, hallucination, and report bloat.

## 10. Provider and Media Services

### 10.1 LLM Provider Strategy

Runtime uses the central app provider gateway. It should not hardcode LM Studio, Cerebras, OpenRouter, OpenAI-compatible, or any specific provider in gameplay logic.

Provider-specific behavior belongs in provider/gateway code. Runtime code should specify purpose and prompt contract.

### 10.2 Image, TTS, and STT

Media services are optional presentation services:

- Image generation can produce scene/portrait images.
- TTS can read grounded narration or NPC lines.
- STT can convert voice into player input.

Media services must not mutate RPG state.

## 11. Current Validated State

As of CE.2.12 and CE.2.13:

- Fast combat skips synchronous combat narration.
- Combat fast path runs around 0.06-0.10 seconds in live matrix.
- Combat provider call count is zero in the fast combat scenario.
- Interactive intent matrix remains 8/8.
- Manual harness no longer owns fast-direct gameplay routing.
- Fast-direct detection lives in `interactive_first_call_runtime`.
- CE.2.12 unit tests pass.
- CE.2.13 convergence tests pass.
- Ruff checks for the touched CE.2.12/CE.2.13 modules pass when locally run.

## 12. Known Risks and Mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinated state | Runtime-first design, grounding validation, deterministic fallbacks, source fields. |
| Harness/app drift | Harness calls app runtime; regression checks selected apply_turn module. |
| Slow turns | Fast-direct paths, deferred narration, performance traces, no sync combat narration in fast mode. |
| Report bloat | Artifact detail modes, compact summaries, growth budget checks. |
| Static NPCs | File-backed profiles, memory, relationships, evolution arcs. |
| Save/load drift | Durable session store, snapshots, replay/checkpoint validation. |
| Stale visible text | Runtime patches stale result fields with authoritative interaction reasons. |

## 13. 100-Turn Readiness

Required pillars:

- Story arcs.
- Quest log/objectives.
- Campaign director.
- NPC memory/social state.
- Service/travel/combat hooks.
- Narration contract.
- Journal/recap.
- Player action context and suggested actions.
- Loop detection.
- Progress metrics.
- Save/load checkpoint validation.

## 14. 1000-Turn Readiness

Additional requirements:

- Robust travel/location graph.
- Long-term economy/resource pressure.
- Complete combat lifecycle with enemy turns and outcomes.
- Long-term NPC schedules and agency.
- Faction/reputation consequences.
- World-state compression/summarization.
- Memory aging and importance scoring.
- Story pacing controls.
- Arc completion/failure rules.
- End-state detection.
- Automated evals for long-run coherence.

## 15. Maintenance Rules for Future Bundles

1. Keep simulation/runtime authoritative.
2. Keep LLM state mutation impossible by design.
3. Keep harnesses out of gameplay routing.
4. Add source fields for fallbacks and repairs.
5. Add tests for new routing, source fields, and state contracts.
6. Keep provider selection centralized.
7. Keep performance phase timings visible.
8. Keep reports readable and source-backed.
9. Prefer deterministic fast paths only for narrow, safe, common commands.
10. Update this file whenever `src/app/rpg` architecture changes.

## 16. Quick Ownership Reference

```text
src/app/rpg/session/                 turn orchestration, canonical runtime, persistence, narration contracts
src/app/rpg/ai/                      first-call LLM advisory and semantic classification
src/app/rpg/interactions/            deterministic general interaction resolution
src/app/rpg/core/                    determinism, effects, state contracts, event bus, boundaries
src/app/rpg/systems/                 event-driven combat/emotion/scene/memory/debug systems
src/app/rpg/memory*                  NPC memory, relationship, belief, prompt memory context
src/app/rpg/npc*                     NPC profiles, persona, biography, roleplay/evolution integration
src/app/rpg/director.py              story/behavior arc direction and progression
src/app/rpg/world_scene_narrator.py  structured scene narration and fallback behavior
src/app/rpg/llm_app_gateway.py       provider-independent LLM gateway
src/app/rpg/game_loop.py             loop-level runtime orchestration
src/app/rpg/replay_engine.py         replay/determinism support
src/app/rpg/snapshot_manager.py      snapshot/checkpoint support
src/app/rpg/simulation/              sandboxed simulation support
```

## 17. Architectural Summary

The RPG engine is a deterministic game engine with AI-assisted interpretation and narration. It should feel like an AI RPG because NPCs can speak richly, remember, evolve, and react; it should behave like a reliable game because rules, state, rewards, combat, economy, travel, and persistence are reproducible and runtime-owned.

The long-term design target is a living RPG world where the player can speak naturally, NPCs roleplay with grounded persona and memory, the world evolves over hundreds or thousands of turns, and every meaningful change remains backed by deterministic state rather than LLM hallucination.
