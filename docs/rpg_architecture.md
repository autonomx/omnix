# RPG Game Architecture and Design

## 1. Purpose

This document describes the current and intended architecture for the RPG game system in Omnix. The game is designed as a deterministic RPG runtime with AI-assisted interpretation and narration. The central design rule is that the simulation is authoritative and the LLM is a presentation, interpretation, or advisory layer only. The LLM may help understand a player's natural-language input, produce persona-rich dialogue, or narrate resolved events, but it must not invent state changes, inventory, prices, quests, rewards, damage, travel outcomes, or other authoritative facts.

The architecture supports human-playable interactive sessions, automated regression scenarios, long autoplay campaigns, rich HTML reports, and later expansion into a persistent living-world RPG with evolving NPCs, story arcs, factions, travel, combat, economy, party members, memory, and local media services.

## 2. Core Design Principles

### 2.1 Simulation Is Truth

All durable game facts must be produced by deterministic runtime logic. This includes location, inventory, currency, health, combat state, NPC memory, quest state, party composition, faction state, service purchases, shop transactions, travel progress, and world events.

LLM output can be accepted only when it is non-authoritative or when it maps into an explicit deterministic action that the runtime resolves. If LLM text says the player bought bread but the economy system did not subtract currency and add the item, then the purchase did not happen.

### 2.2 Runtime Before Narration

The runtime resolves player intent and state mutation before final narration. Narration is grounded in the result. This avoids the LLM narrating impossible events such as inventing a defeat, claiming a paid item was received without payment, or moving the player to a location that the travel graph did not allow.

The preferred interactive flow is:

```text
Player input
  -> grounded first-call intent/advisory
  -> deterministic runtime resolution
  -> deferred or deterministic final narration
  -> UI/report rendering
```

### 2.3 LLM Calls Must Have Explicit Jobs

The project uses separate LLM responsibilities rather than one all-powerful prompt. The LLM can be used for:

1. Intent extraction / semantic routing.
2. Persona-aware non-stateful NPC dialogue.
3. Deferred narration after the runtime resolves state.
4. Advisory diagnostics and grounding checks.

The LLM must not directly decide economy prices, inventory availability, quest rewards, combat damage, enemy defeat, location transitions, or save-state mutation.

### 2.4 Human Turn Latency Matters

The human-equivalent blocking turn should stay fast. Runtime and deterministic systems should return immediately where possible. Expensive LLM narration should be deferred, backgrounded, disabled, or replaced with deterministic narration in fast-turn scenarios.

Recent fast buckets such as combat, survival, and travel are expected to run around 0.05-0.15 seconds when fast-turn mode is enabled. First-call LLM scenarios such as dialogue, quest inquiry, rumors, and commerce may be slower because they intentionally call the provider.

### 2.5 Reports Are Part of the Product

Autoplay and matrix reports are not merely test logs. They are design tools. They must show conversations, state deltas, decisions, prompts, provider calls, warnings, fallbacks, slow turns, narrative sources, combat progress, party state, quest state, inventory, location travel, and validation failures in a readable format.

## 3. High-Level Architecture

```text
UI / CLI / Test Harness
  |
  v
Interactive First-Call Runtime
  |-- deterministic fast-direct routing for known fast actions
  |-- first-call LLM advisory for ambiguous / social / semantic actions
  |-- non-stateful dialogue shortcut when safe
  |
  v
Canonical Runtime / Simulation
  |-- service and commerce resolver
  |-- combat resolver
  |-- travel resolver
  |-- survival resolver
  |-- party resolver
  |-- quest / rumor / work inquiry resolvers
  |-- story director and world events
  |-- NPC memory and social state
  |
  v
Narration Layer
  |-- deterministic fallback narration
  |-- deferred runtime narration
  |-- provider narration when allowed
  |-- grounding validation / repair
  |
  v
Session Persistence + Reports + UI Rendering
```

The architecture is intentionally layered. The interactive harness, CLI, and tests should not implement gameplay shortcuts. They call the same application runtime path used by the game. This prevents test-only behavior from diverging from human-playable behavior.

## 4. Major Runtime Layers

### 4.1 UI, CLI, and Test Harness Layer

The entry surfaces are responsible for collecting player input, displaying responses, and collecting diagnostics. They should not own gameplay routing.

Responsibilities:

- Accept player input.
- Send input to `interactive_first_call_runtime.apply_turn` or the equivalent app runtime entrypoint.
- Render narration, NPC lines, state changes, and warnings.
- Emit trace data and reports.
- Preserve raw results when debug or full artifacts are requested.

Non-responsibilities:

- Do not decide combat, travel, survival, or purchase actions.
- Do not bypass the app runtime for fast-direct gameplay.
- Do not invent LLM diagnostics.
- Do not mutate simulation state outside runtime APIs.

CE.2.13 specifically moved manual fast-direct gameplay routing out of the manual harness and into the app runtime wrapper. The harness now functions as a diagnostic/reporting layer rather than an alternate gameplay engine.

### 4.2 Interactive First-Call Runtime

The interactive runtime is the player-facing orchestrator. It handles the two-call design: grounded intent before runtime, then narration after runtime.

Core responsibilities:

- Load or select the active session.
- Identify deterministic fast-direct actions when fast-turn mode is enabled.
- Build grounded action advisories for provider-assisted routing.
- Build semantic advisories when enabled.
- Allow safe non-stateful NPC dialogue to be consumed before runtime mutation.
- Route stateful actions to the canonical runtime.
- Attach first-call diagnostics and prompt context to the result.
- Apply narration contracts that describe whether narration was disabled, deterministic, deferred, or blocking.

Fast-direct examples:

- Survival status and provision use.
- Known travel commands such as continuing toward the old mill.
- Known combat commands such as attacking a road bandit.

Fast-direct actions still call the canonical runtime for state mutation. They bypass only unnecessary provider calls.

### 4.3 Canonical Runtime / Simulation Layer

The canonical runtime is the authoritative state mutation layer. All final game state comes from this layer.

Responsibilities:

- Resolve player actions into deterministic game outcomes.
- Enforce economy, inventory, combat, travel, party, quest, and survival rules.
- Update runtime state and simulation state.
- Produce authoritative result payloads.
- Save and load runtime sessions.
- Trigger world events, memory updates, and story progression where allowed.
- Produce deterministic fallback narration and state summaries.

The canonical runtime should not depend on test harness shortcuts or UI assumptions.

### 4.4 Narration Layer

The narration layer turns resolved state into player-facing text. It may be deterministic, deferred, blocking, disabled, or provider-generated depending on settings and performance mode.

Narration modes:

- `disabled`: no narrative text beyond state summaries.
- `deterministic`: use deterministic runtime-generated text only.
- `deferred`: return the authoritative result immediately and queue or attach narration later.
- `blocking`: wait for provider narration before returning.

Combat fast mode should avoid synchronous combat narration. Combat results can expose deterministic payloads with sources such as `deterministic_combat_fast_summary`, while the visible matrix source may be `deferred_runtime_narration_pending` or `authoritative_runtime_result`.

### 4.5 Persistence Layer

Sessions persist game and runtime state to disk. The persistence system must support:

- Save/load for human play.
- Checkpoint validation for long autoplay.
- Compact save formats for performance.
- Durable session registries.
- Long-term NPC memory and evolving profiles.
- Report artifact references.

Persistence must be deterministic enough for validation. Loading a saved state should preserve runtime-critical fields such as combat state, party state, quest state, inventory, currency, NPC memories, world events, and story arcs.

## 5. Data Model

### 5.1 Session

A session is the top-level container for gameplay state. It generally contains:

- Manifest: session ID, created metadata, scenario metadata.
- Simulation state: authoritative world/player/NPC state.
- Runtime state: transient turn state, settings, pending narration, combat state, diagnostics.
- Journal / recap state.
- World events.
- Reports and artifact metadata.

### 5.2 Simulation State

Simulation state should be the main source of game truth.

Typical fields:

- Player character state.
- Current location.
- Inventory and currency.
- Active quests and objectives.
- NPC registry and social state.
- Party members.
- Story arcs and campaign director state.
- World events and rumors.
- Survival state.
- Faction/reputation state.

### 5.3 Runtime State

Runtime state contains operational data needed for turn execution.

Typical fields:

- Tick / turn counters.
- Runtime settings.
- Narration mode.
- Combat state.
- Pending narration jobs.
- Fast-direct flags.
- First-call grounding diagnostics.
- Provider timing and token usage.
- Current scenario/test metadata.

Runtime state can include transient diagnostics, but any fact needed after save/load must be persisted deliberately.

### 5.4 Turn Contract

The turn contract is the structured representation of what the player did and how the runtime interpreted it.

It should contain:

- Raw player input.
- Final action type.
- Target IDs and names.
- Requested terms.
- Service kind when relevant.
- Runtime-resolved result.
- Narration status.
- Diagnostics and sources.

The turn contract helps prevent LLM hallucination by separating what the player asked from what the runtime actually resolved.

## 6. Player Turn Pipeline

### 6.1 Normal Stateful Turn

```text
1. Player enters natural-language command.
2. Interactive runtime loads session and state.
3. Runtime checks for fast-direct match if fast-turn mode is enabled.
4. If no fast-direct match, first-call LLM advisory may classify intent.
5. Safe non-stateful dialogue may be returned directly if no state mutation is needed.
6. Stateful action is passed to canonical runtime.
7. Canonical runtime mutates state deterministically.
8. Narration contract is applied.
9. Result is returned to UI/harness/report.
```

### 6.2 Fast-Direct Turn

```text
1. Player enters a known fast command.
2. Interactive runtime maps it to a deterministic action.
3. Canonical runtime resolves the action.
4. Provider calls are disabled or skipped.
5. Deterministic or deferred narration is attached.
6. Result returns quickly.
```

Fast-direct exists for performance and reliability. It should be narrow, explicit, and covered by regression tests.

### 6.3 Non-Stateful Dialogue Turn

Some NPC dialogue can be answered without mutating game state. For example, asking Bran who he is or what he knows about the tavern can be handled as interpretive dialogue if the first-call grounding packet has enough persona context and no stateful intent is detected.

The result can include:

- Narration.
- NPC speaker and line.
- Grounding diagnostics.
- Fallback source if used.
- No authoritative state mutation.

### 6.4 Commerce / Service Turn

Commerce and services must be deterministic. The player may ask about food, room prices, wares, or purchase items, but the runtime decides:

- Whether the service exists.
- The canonical price.
- Whether the player can afford it.
- Inventory/currency changes.
- Failure reason if purchase is not possible.

NPC text can present the result, but cannot invent stock or prices.

### 6.5 Combat Turn

Combat is deterministic and stateful.

Combat state includes:

- Active flag.
- Participants.
- Sides.
- HP values.
- Initiative or turn order.
- Last action.
- Damage applied.
- Defeat state.
- Combat end state.

Combat narration must not decide damage or defeat. In fast mode, synchronous combat narration is skipped and deterministic summaries are used. The combat resolver applies HP changes and marks defeat when enemy HP reaches zero.

### 6.6 Travel Turn

Travel must respect the location graph and route constraints. The runtime decides whether travel is allowed, whether progress is made, whether the destination changes, and what location state is updated.

LLM narration can describe movement after the runtime validates the destination.

### 6.7 Survival Turn

Survival state includes hunger, thirst, fatigue, water, rations, and related resource pressure. Fast-turn survival checks and provision use can be deterministic because they are common and should not require provider calls.

## 7. LLM Integration Design

### 7.1 Provider Gateway

The app uses a central provider gateway rather than hardcoding one provider into gameplay logic. This allows swapping LM Studio, OpenAI-compatible endpoints, OpenRouter, Cerebras, or other providers without changing gameplay code.

Provider-specific concerns such as model speed, prompt shape, token usage, and raw response handling belong in the gateway or LLM utility layer, not in deterministic runtime systems.

### 7.2 First-Call Intent Extraction

The first call receives grounded context. It should know:

- Current player input.
- Relevant location and NPC context.
- Addressed NPCs.
- Candidate action if any.
- Recent memory and persona data.
- Available deterministic state.

It returns structured advisory data, not final game state.

### 7.3 Deferred Narration

Deferred narration happens after runtime resolution. It receives grounded context that includes:

- What the player attempted.
- What the runtime actually did.
- State deltas.
- NPC persona and memory.
- Allowed presentation boundaries.

Deferred narration can improve prose quality while preserving fast blocking turns.

### 7.4 Grounding Validator

The grounding validator checks whether narration or dialogue contradicts deterministic state. It can flag or repair claims about:

- Currency.
- Inventory.
- Location.
- Combat defeat.
- Quest state.
- Unsupported rewards or jobs.

The validator should distinguish hard state claims from harmless flavor text.

### 7.5 Fallbacks

Fallbacks must be explicit and traceable. Common fallback types include:

- Deterministic fallback narration.
- Safe non-stateful dialogue fallback.
- Commerce repair fallback.
- Quest/no-backed-state fallback.
- Rumor/no-backed-rumor fallback.
- Survival repair fallback.

Every fallback should include a source field and reason so reports can explain why it happened.

## 8. NPC Architecture

### 8.1 NPC Profiles

NPCs should have file-backed profiles. A profile should include:

- NPC ID.
- Name.
- Role.
- Location or home region.
- Biography.
- Personality profile.
- Speech examples.
- Relationships.
- Known services or shop behavior.
- Faction affiliations.
- Memory settings.
- Evolution arcs.

The profile should be more descriptive than a few tags. The LLM roleplay quality depends heavily on paragraph-level biography, history, attitudes, and examples of speaking style.

### 8.2 Persona and Dialogue

Persona context should be attached to first-call and narration prompts when the NPC is addressed or relevant. For example, Bran should not be a generic innkeeper. His profile should define his temperament, speaking style, history, and current relationship with the player.

Dialogue should be grounded in:

- NPC profile.
- Current location.
- Known backed rumors/events/quests.
- NPC memory.
- Social relationship state.
- Current player input.

NPCs can speak with style, but they cannot invent authoritative state.

### 8.3 NPC Memory

NPC memory should record meaningful interactions and world events. It should avoid fake or synthetic memories for environment-only targets.

Memory types may include:

- Player promises.
- Past purchases.
- Threats or kindness.
- Shared combat events.
- Quest involvement.
- Reputation changes.
- Personal losses or victories.
- Long-term relationship markers.

Memory should support aging, summarization, importance scoring, and retrieval by relevance.

### 8.4 NPC Evolution

NPCs should evolve over time. For example, Bran might begin as a tavern keeper, lose his tavern to bandits, join the player as a companion, and gradually become more hardened or adventurous.

NPC evolution requires:

- Backed world events.
- Explicit arc state.
- Memory updates.
- Profile evolution records.
- Behavior changes.
- Dialogue style changes.
- Party/companion state changes when applicable.

Evolution must be state-backed. The LLM can express evolution, but the runtime decides when it is true.

## 9. World and Story Architecture

### 9.1 Story Arcs

Story arcs define longer-running narrative structure. They should be deterministic state machines or state-backed planners rather than freeform LLM inventions.

An arc can include:

- Arc ID.
- Current phase.
- Trigger conditions.
- Beat history.
- Active objectives.
- Related NPCs.
- Related locations.
- Failure or escalation rules.
- Completion rules.

### 9.2 Campaign Director

The campaign director manages pacing and progression. It should select or advance backed story beats based on current state, not force the same story every run unless the seed requires it.

Director responsibilities:

- Seed arcs.
- Advance beats.
- Avoid repetition loops.
- Apply pressure when the player stalls.
- Surface objectives.
- Track progression quality.
- Preserve determinism with seeds.

### 9.3 Quests and Objectives

Quest state must be explicit. Asking for a quest when no backed quest exists should return a grounded no-backed-state response, not invent a job.

Quest architecture should include:

- Quest ID.
- Title.
- Giver.
- Objectives.
- Completion state.
- Rewards.
- Known hints.
- Journal text.
- Prerequisites.
- Failure states.

### 9.4 Rumors and News

Rumors must be backed by world state, event state, or rumor seeds. If no confirmed rumor exists, the NPC should say so or answer generally without asserting false facts.

Rumors should support:

- Source.
- Confidence.
- Expiration.
- Location relevance.
- NPC knowledge boundaries.
- Link to quests or arcs.

### 9.5 World Events

World events are deterministic records of meaningful changes. They can drive rumors, NPC memory, story arcs, and reports.

Examples:

- Bandit attack.
- Tavern damage.
- Merchant arrival.
- Faction movement.
- Quest completion.
- Combat victory.
- Companion recruitment.

## 10. Mechanics Architecture

### 10.1 Economy

The economy uses canonical currency and deterministic pricing. The current preferred model is gold, silver, and copper. Example: a room at Bran's tavern can cost 5 silver per night.

Economy rules:

- Prices come from deterministic service/shop data.
- Purchases require sufficient currency.
- Currency deltas must be recorded.
- Items are added only after successful purchase.
- Failed purchases must provide clear reason.
- NPC narration cannot override economy rules.

### 10.2 Inventory

Inventory is authoritative state. Items should have canonical IDs and display names. Starter items and currency should be seeded deliberately rather than starting with empty inventory unless a scenario demands it.

Inventory actions include:

- Add item.
- Remove item.
- Consume item.
- Equip item.
- Sell item.
- Inspect item.

### 10.3 Stats, Skills, XP, and Leveling

The system should support player progression with deterministic rules.

Design direction:

- XP from kills and quests only.
- Skills improve from use.
- Stats such as strength, charisma, and archery affect outcomes.
- Leveling should be transparent in reports.
- Rewards should be state-backed.

### 10.4 Combat

Combat design should support:

- Initiative.
- Player turns.
- Enemy turns.
- Action gating.
- Damage calculation.
- Hit/miss logic.
- Defeat handling.
- Loot and XP rules.
- Combat log.
- Narration grounding.

Combat should not spam repeated text. Combat reports should show HP progression, damage, actor, target, defeat, and combat end state.

### 10.5 Party and Companions

Party state should include companions, roles, follow modes, recruitment history, and companion dialogue. Companion acceptance should require backed eligibility or explicit offer state.

Party systems should support:

- Offer to join.
- Acceptance.
- Rejection.
- Follow mode.
- Companion combat participation.
- Companion opinions.
- Relationship changes.
- Companion personal arcs.

### 10.6 Travel and Location Graph

The travel graph defines reachable locations. Travel should be deterministic and should update location state only through valid transitions.

Location design should include:

- Location ID.
- Name.
- Description.
- Connected locations.
- NPCs present.
- Services.
- Hazards.
- Events.
- Rumors.
- Discovery state.

### 10.7 Survival

Survival introduces long-term pressure through hunger, thirst, fatigue, provisions, rest, and environmental pressure.

Survival should be clear but not tedious. It should generate meaningful decisions, not constant punishment.

## 11. Reporting and Diagnostics Architecture

### 11.1 Manual Scenario Reports

Manual scenario reports should show:

- Scenario name.
- Turn list.
- Player input.
- Narration.
- NPC speaker and line.
- Raw result keys.
- Final classification.
- First-call diagnostics.
- Grounding packet.
- Warnings and fallbacks.
- Runtime state deltas.

### 11.2 Interactive Intent Matrix

The matrix validates realistic interactive CLI flows. It covers commerce, quest inquiries, rumors, survival, NPC dialogue, combat, travel, and party recruitment.

The matrix should report:

- Pass/fail per scenario.
- Expected text checks.
- Final action type checks.
- Provider call checks.
- Narration source checks.
- Combat progress.
- Party progress.
- Performance rollups.
- Slowest scenarios.

### 11.3 Autoplay Campaign Reports

Autoplay reports validate long-run behavior. They should include:

- Summary.
- Story arcs.
- NPC sections.
- Lore and worldbuilding.
- Player progression/stats.
- Inventory and economy.
- Combat history.
- Location journey.
- Journal and recap.
- Performance metrics in seconds.
- Token usage.
- Prompt previews.
- Fallthrough/fallback counts.
- Repair pressure by category.
- Growth budget diagnostics.

### 11.4 Performance Diagnostics

Performance diagnostics should separate:

- Harness overhead.
- First-call provider time.
- Runtime resolution time.
- Narration provider time.
- Report writing time.
- Background drain time.
- Slow turns by phase.

This separation is necessary because a 5-second turn can be caused by the first-call provider, not the deterministic runtime.

## 12. Test Architecture

### 12.1 Unit Tests

Unit tests cover deterministic functions, validators, fast skip hooks, and helper behavior.

Examples:

- Fast combat narration skip bypasses provider.
- Matrix-shaped fast-direct markers bypass provider.
- Runtime hook installs after import.
- Non-fast combat still calls provider.
- Runtime/harness convergence tests.

### 12.2 Manual Service Scenarios

Manual scenarios cover specific player-facing interactions. They should be executable, inspectable, and reportable.

Examples:

- Shop success.
- Room purchase.
- NPC replies after player join.
- Combat narration validation.
- Rumor seed expiration.
- Companion recruitment.

### 12.3 Interactive Intent Matrix

The matrix is the primary regression suite for the interactive CLI path. It should be run with live provider mode when validating real performance and provider behavior.

### 12.4 Long-Run Autoplay

Autoplay validates progression over 100 and 1000 turns. It is used to detect loops, stale prompts, hallucinations, missing mechanics, report bloat, and save/load issues.

### 12.5 Regression Warnings

Warnings should fail when explicitly requested by `--fail-on-regression-warnings`. Scenario warnings should also fail when they indicate regression-critical behavior.

## 13. Media Services

The RPG architecture can integrate local media services without making them part of authoritative simulation.

### 13.1 Image Generation

Image generation should be optional and externally served. Scene and portrait generation can use local FLUX models, but generated images do not mutate state.

### 13.2 Text-to-Speech

TTS should read grounded narration or NPC dialogue. It should not generate new dialogue independently.

### 13.3 Speech-to-Text

STT can convert player speech into input text. The resulting text enters the same player turn pipeline.

## 14. Configuration and Provider Strategy

Provider selection should remain centralized. Runtime code should ask the provider gateway for LLM work rather than directly calling one provider implementation.

Configuration should support:

- Provider type.
- Model name.
- Endpoint.
- Timeout.
- Token budget.
- Narration mode.
- Fast-turn mode.
- Semantic advisory toggle.
- Background narration toggle.
- Grounding validation toggles.

The user can swap providers without changing gameplay logic.

## 15. Current Validated State

As of the CE.2.12 and CE.2.13 work:

- Fast combat skips synchronous combat narration.
- Combat can run around 0.06-0.10 seconds in live matrix fast mode.
- Combat provider call count is zero in the fast combat scenario.
- The matrix remains 8/8.
- The manual harness no longer owns fast-direct gameplay routing.
- Fast-direct detection now lives in `interactive_first_call_runtime`.
- The manual harness prefers `interactive_first_call_runtime.apply_turn`.
- CE.2.12 unit tests pass.
- CE.2.13 convergence tests pass.

## 16. Known Design Risks

### 16.1 LLM Hallucination

Risk: LLM narration invents unsupported state.

Mitigation:

- Runtime-first design.
- Grounding validation.
- Source fields.
- Deterministic fallbacks.
- No state mutation from narration.

### 16.2 Harness/App Drift

Risk: Tests pass through harness shortcuts that human play does not use.

Mitigation:

- Harness must call app runtime.
- Regression tests verify selected runtime module.
- Fast-direct logic lives in app runtime.

### 16.3 Report Bloat

Risk: Long transcripts and debug fields grow to massive sizes.

Mitigation:

- Compact summary mode.
- Debug/full artifact modes.
- Payload budget checks.
- Growth offender reports.

### 16.4 Slow Turns

Risk: Provider calls make human play too slow.

Mitigation:

- Fast-direct deterministic buckets.
- Deferred narration.
- Provider timing diagnostics.
- Narrow first-call usage.
- Background narration and audits.

### 16.5 Static NPCs

Risk: NPCs do not evolve and feel fake over long play.

Mitigation:

- File-backed profiles.
- Memory extraction.
- Evolution arcs.
- Relationship state.
- Backed world events.

## 17. Roadmap

### 17.1 Near-Term

- Keep matrix 8/8 while removing remaining harness-only behavior.
- Improve first-call provider latency.
- Expand deterministic fast-direct coverage only where safe.
- Improve report sections for prompts, fallback reasons, and state deltas.
- Ensure save/load checkpoint validation is robust.

### 17.2 100-Turn Readiness

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

### 17.3 1000-Turn Readiness

Additional requirements:

- Robust travel/location graph.
- Long-term economy/resource pressure.
- Complete combat lifecycle.
- Long-term NPC schedules and agency.
- Faction/reputation consequences.
- World-state compression/summarization.
- Memory aging and importance scoring.
- Story pacing controls.
- Arc completion/failure rules.
- End-state detection.
- Automated evals for long-run coherence.

## 18. Development Rules for Future Bundles

1. Do not let LLM narration mutate state.
2. Do not add harness-only gameplay behavior.
3. Add source fields for every fallback or repair.
4. Add tests before relying on new routing behavior.
5. Preserve provider independence through the gateway.
6. Keep performance phase timing visible.
7. Keep reports readable for humans.
8. Prefer deterministic logic for common fast actions.
9. Use file-backed NPC profiles and memory for persona richness.
10. Treat matrix and autoplay results as product-quality validation artifacts.

## 19. Architectural Summary

The RPG engine is a deterministic game runtime with AI-assisted interpretation and presentation. The game should feel like an AI RPG because NPCs can speak richly, remember, evolve, and react, but it should behave like a reliable game engine because rules, state, rewards, combat, economy, and travel are authoritative and reproducible.

The long-term goal is a living RPG world where the player can speak naturally, NPCs can roleplay with grounded persona and memory, the world can evolve over hundreds or thousands of turns, and every meaningful change remains backed by deterministic state rather than LLM hallucination.
