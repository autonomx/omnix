# RPG Response Generation and Narrative Continuity Roadmap

Status: proposed implementation plan  
Created: 2026-07-10  
Source of truth: `main`  
Primary principle: **preserve authoritative truth, interpret the player's intent, and keep the game moving.**

## 1. Vision

Build one response-generation system that makes the RPG feel like a living world rather than a command parser.

The system should:

- resolve supported actions through deterministic mechanics;
- answer the player's actual statement or question before adding flavor;
- treat unsupported or uncertain input as a recovery and interpretation problem, not as a reason to emit generic text;
- search current state, memories, campaign history, lore, and world packs for relevant information;
- use Hermes for bounded research and proposal generation when local knowledge is insufficient;
- transform impossible, unsupported, or anachronistic requests into the nearest meaningful in-world action;
- create a grounded answer, reaction, lead, choice, consequence, or investigation path on nearly every turn;
- keep inventory, currency, health, combat, travel, quest, relationship, discovery, and world-state changes simulation-authoritative;
- remain fast, streamable, replayable, and auditable.

The governing rule is:

> Favor conversational continuity and forward motion over rigid command correctness, but never over authoritative state integrity.

## 2. Non-negotiable boundaries

### 2.1 Hard truth remains simulation-owned

The LLM, retrieval layer, and Hermes may not directly mutate:

- player or NPC location;
- inventory or equipment;
- currency, prices, payment, debt, or service consumption;
- health, damage, defeat, death, capture, loot, XP, or skill growth;
- quest state or objective completion;
- relationship values or faction standing;
- discovered facts, unlocked locations, spawned entities, or persistent world objects;
- time, weather, schedules, or offscreen events;
- save/load and replay state.

Every such change must be represented by a deterministic resolver result and typed state delta.

### 2.2 Soft truth may be generated as bounded presentation or proposals

The response system may generate:

- NPC beliefs, suspicions, uncertainty, opinions, and emotional reactions;
- rumors, folklore, interpretations, and possible explanations;
- questions, investigative leads, suggestions, and possible next steps;
- descriptions of already-resolved facts;
- low-risk ambient proposals that do not become persistent until accepted by the simulation.

Soft truth must carry provenance and certainty. It becomes hard truth only through a deterministic acceptance policy.

### 2.3 The player should not see internal failure language

Normal gameplay must not expose phrases such as:

- "unsupported action";
- "the turn contract";
- "the model could not determine";
- "no matching resolver";
- "grounding failed";
- "the action resolves according to current state".

Those labels belong only in developer reports.

## 3. Existing problems this roadmap addresses

The current implementation has several overlapping concerns that should be consolidated:

1. A compact runtime narration path and a richer world-scene narration path can both participate in response creation.
2. Final output can concatenate narration, action text, result text, and NPC dialogue even when those fields repeat the same event.
3. Narration-quality checks can run before the final visible response has been selected and rendered.
4. Prompt construction repeats large state and rule blocks instead of using one compact, typed current-turn context.
5. Grounding relies heavily on text-pattern checks rather than a typed ledger of claims allowed by the resolved turn.
6. Grounded safe fallbacks can be ranked below older authoritative narration even when the older text answers the current input less directly.
7. Deterministic fallbacks can be generic, meta, repetitive, or inconsistent with the quality policy.
8. Import-order fixups and runtime monkey patches make the actual narration behavior difficult to reason about and test.
9. Response-length rules and model settings are duplicated across prompt builders and runtime code.
10. Unsupported inputs are too likely to collapse into safe but inert responses instead of becoming useful gameplay.

## 4. Target architecture

```text
Player input
    -> current-turn intent and affordance classifier
    -> deterministic mechanic resolver, when supported
    -> unknown-input recovery coordinator, when unresolved or incomplete
         -> local state and scene retrieval
         -> NPC persona, knowledge, and memory retrieval
         -> journal, campaign history, lorebook, and world-pack retrieval
         -> bounded Hermes research, when required
         -> forward-motion proposal generation
    -> typed NarrationContext compiler
    -> response candidate generation
    -> typed claim-ledger validation
    -> current-turn answer and forward-motion scoring
    -> final-output quality gate and bounded repair
    -> field-aware response renderer
    -> streaming delivery, persistence, and telemetry
```

Only the deterministic resolver and proposal-acceptance layer may produce authoritative state deltas.

## 5. Core contracts

### 5.1 `NarrationContext`

One compact, versioned context assembled for the final response generator.

Required fields:

- schema version and turn ID;
- response mode;
- raw player input;
- interpreted intent and confidence;
- must-answer question or requested outcome;
- resolved mechanic result;
- visible state facts;
- current scene and present entities;
- active speaker card;
- relevant NPC knowledge, personality, relationship, and memory;
- relevant journal, quest, lore, and campaign-history evidence;
- approved soft-truth proposals;
- allowed claims and forbidden claims;
- continuity constraints;
- tone and style profile;
- response word budget;
- latency and provider profile.

The prompt should be current-turn-first. Large raw state objects should not be passed when a typed compact card is sufficient.

### 5.2 `ClaimLedger`

A machine-checkable record derived from authoritative state and the resolved turn.

It should explicitly describe:

- allowed speakers;
- allowed location statements and whether movement occurred;
- currency and inventory deltas;
- service-payment results;
- combat participants, damage, defeat, loot, and XP;
- quest and objective changes;
- relationship and faction deltas;
- facts newly discovered this turn;
- facts known only to an NPC;
- facts hidden from the player;
- proposals approved for persistence;
- claims that are prohibited.

Regex checks remain a defense-in-depth backstop, not the primary truth model.

### 5.3 `RecoveryPlan`

Produced when normal mechanics cannot fully resolve the input.

Suggested shape:

```json
{
  "interpreted_intent": "ask_about_unknown_place",
  "confidence": 0.74,
  "knowledge_status": "partial",
  "evidence": [],
  "npc_knowledge": {
    "knows_answer": false,
    "can_offer_lead": true
  },
  "forward_strategy": "offer_investigation_lead",
  "proposals": [],
  "must_not_claim": []
}
```

### 5.4 `ResponseCandidate`

Each candidate should carry structured metadata rather than only prose:

- text or typed sections;
- source: provider, deterministic, recovery, or Hermes-assisted;
- response mode;
- grounding decision;
- current-turn answer score;
- forward-motion score;
- speaker-validity score;
- specificity score;
- repetition and style issues;
- latency and provider metadata;
- proposal references;
- repair history.

### 5.5 `RenderedResponse`

The renderer should assemble only the fields appropriate for the response mode. It must not blindly concatenate every available field.

## 6. Response modes and default budgets

| Mode | Purpose | Default visible budget |
|---|---|---:|
| `utility` | inventory, stats, map, journal, known status | 1-4 lines |
| `dialogue` | direct NPC answer or social exchange | 35-100 words |
| `observation` | look, inspect, listen, search | 50-130 words |
| `action` | resolved physical or general action | 35-100 words |
| `transaction` | shop, inn, payment, service | 35-100 words |
| `travel` | movement and arrival | 50-140 words |
| `combat` | one resolved combat beat | 60-160 words |
| `investigation` | uncertain question, clue, research, lead | 50-150 words |
| `recovery` | unsupported or ambiguous request transformed into gameplay | 45-140 words |
| `failure` | grounded failure with consequence or alternative | 30-100 words |
| `major_beat` | important reveal, arc transition, defeat, or resolution | 100-240 words |

Budgets are presentation targets, not permissions to omit required facts.

## 7. Unknown-input recovery policy

When a normal resolver cannot directly execute the player's request, the game should attempt the following in order:

1. Resolve the underlying goal through an existing mechanic.
2. Answer socially through an NPC's knowledge, belief, memory, or uncertainty.
3. Retrieve relevant facts from visible state, journal, campaign history, lorebook, and world packs.
4. Ask Hermes to research or synthesize a proposal when local retrieval remains insufficient and the turn warrants the added latency.
5. Convert the input into a supported investigation, social action, inspection, substitution, travel lead, or proposed world action.
6. Return an in-world failure that creates a consequence, alternative, or next step.

The final response should normally leave the player with at least one of:

- an answer;
- an NPC reaction;
- a discovered clue;
- a grounded lead;
- a meaningful choice;
- a consequence;
- a valid alternative action;
- an explicit uncertainty worth investigating.

## 8. Narrative affordance families

The recovery classifier should map unusual input into broad affordances rather than exact command syntax.

| Player input class | Recovery affordance |
|---|---|
| unknown person, place, item, faction, or event | knowledge check, lore search, rumor, or lead |
| unsupported object use | inspect, improvise, substitute, craft, or ask for help |
| unsupported spell or power | arcana attempt, ritual research, analogous skill check, or consequential failure |
| unknown travel destination | memory/map search, ask directions, create a lead, or reject as unverified |
| invented prior history | memory search, treat as an unverified player claim, or invite clarification in-world |
| invented NPC | search known entities, interpret as a description, or create a non-persistent lead proposal |
| impossible technology | translate the underlying goal into a world-appropriate method |
| unusual social action | persuasion, deception, intimidation, insight, performance, etiquette, or relationship check |
| broad world question | retrieve lore and answer from the current speaker's perspective |
| request beyond current mechanics | simulate the nearest safe abstraction and explain the in-world result |

## 9. Hermes role and safety boundary

Hermes should act as a bounded investigator and proposal generator, not as the authoritative game master.

Hermes may:

- search relevant campaign and lore sources;
- reconcile multiple pieces of evidence;
- identify related NPCs, locations, factions, quests, and events;
- suggest interpretations and forward strategies;
- generate proposed lore additions, rumors, clues, or quest seeds;
- rank possible responses and explain missing information;
- return structured evidence, inference, uncertainty, and proposal objects.

Hermes may not:

- mutate RPG state;
- mark quests complete;
- grant inventory, currency, XP, skills, or relationships;
- move the player;
- create confirmed locations, people, or events without simulation acceptance;
- execute tools or external actions on behalf of the RPG recovery path;
- expose hidden world facts to the player unless the retrieval policy marks them visible.

The existing proposal-only Hermes pattern should be reused, with RPG-specific schemas, bounded timeouts, explicit provenance, and a local-recovery fallback.

## 10. Soft-truth classification

Every non-authoritative fact used during recovery should have one class:

- `confirmed_fact` — already authoritative and player-visible;
- `retrieved_lore` — authoritative lore available to this speaker or player;
- `npc_belief` — a character's belief, which may be wrong;
- `rumor` — attributed and unconfirmed;
- `inference` — reasoned from evidence but not confirmed;
- `generated_proposal` — candidate world addition awaiting acceptance;
- `unverified_player_claim` — asserted by the player but not established;
- `hidden_fact` — authoritative but unavailable to the player and prohibited from narration.

The player-facing prose should express uncertainty naturally. Internal labels remain available in debug reports.

## 11. Implementation phases

Each phase should land as a narrow PR with deterministic tests and a roadmap status update.

### Phase 0 — Baseline corpus and response metrics

Goal: Measure the current behavior before changing routing or prose.

Work:

- create a fixed scenario corpus covering supported actions, unknown lore, invented entities, unsupported spells, impossible technology, ambiguous social actions, contradictory player claims, failed purchases, invalid travel, and combat edge cases;
- capture current final responses, candidate source, grounding decision, latency, repetition, and fallback reason;
- define metrics:
  - generic fallback rate;
  - current-turn answer rate;
  - forward-motion rate;
  - unsupported hard-state claim rate;
  - repeated-content rate;
  - stale-response selection rate;
  - local-retrieval hit rate;
  - Hermes invocation, success, timeout, and usefulness rates;
  - p50 and p95 blocking latency by response mode.

Acceptance:

- no runtime behavior changes;
- fixtures are deterministic and versioned;
- reports distinguish final visible text from intermediate candidates;
- baseline results can be compared in CI.

### Phase 1 — Canonical response envelope and field-aware renderer

Goal: Stop duplicated or log-like response assembly.

Work:

- add typed response modes and one `RenderedResponse` contract;
- centralize rendering for dialogue, observation, action, combat, travel, transaction, utility, investigation, recovery, failure, and major beats;
- prevent automatic concatenation of narration, result, action, and dialogue when they repeat the same event;
- keep authoritative deltas available to UI and reports without forcing them into prose;
- adapt existing runtime and world-scene paths to return the common envelope.

Acceptance:

- one renderer owns final visible assembly;
- no response repeats the same resolved action in multiple labeled sections unless the mode explicitly requires it;
- existing authoritative state and turn contracts are unchanged;
- snapshot tests cover every response mode.

### Phase 2 — Final-candidate ranking and post-selection quality gate

Goal: Evaluate the text that the player will actually see.

Work:

- replace source-order selection with candidate scoring;
- score current-turn relevance, grounding, speaker validity, contract coverage, specificity, naturalness, forward motion, and repetition;
- ensure a grounded safe candidate outranks stale prior narration;
- run repetition, low-value phrase, opening-pattern, overlap, and style checks after candidate selection and rendering;
- add deterministic repairs for removable labels, duplicate sentences, repeated action summaries, and banned meta language;
- allow at most one bounded provider rewrite when deterministic repair is insufficient.

Acceptance:

- quality reports describe the final visible response;
- safe fallback candidates are not discarded merely because they are fallbacks;
- deterministic repairs cannot change authoritative facts;
- final output contains no internal system terminology.

### Phase 3 — Typed current-turn-first `NarrationContext`

Goal: Reduce prompt overload and make response behavior understandable.

Work:

- create the versioned context compiler;
- include only relevant scene, entity, memory, quest, lore, and continuity cards;
- make the player's latest statement or question and the must-answer objective the first-class prompt input;
- replace repeated special-case prompt prose with typed constraints;
- centralize response budgets and tone/style profiles;
- record context omissions and truncation decisions in developer traces.

Acceptance:

- both narration entry points consume the same context contract;
- prompt size decreases materially on the baseline corpus;
- current-turn answer rate does not regress;
- hidden information cannot enter the visible context card.

### Phase 4 — Typed claim ledger and exact grounding

Goal: Validate meaning against resolved state rather than primarily scanning prose.

Work:

- derive a `ClaimLedger` from the authoritative turn result;
- validate speakers, movement, inventory, currency, services, combat, quests, relationships, discovery, and approved proposals;
- require explicit evidence for location-change and progression claims;
- keep regex and named-fact checks as secondary guards;
- classify violations as repairable, candidate-rejecting, or pipeline-fatal.

Acceptance:

- unsupported hard-state claims remain zero in deterministic tests;
- each rejection points to a typed ledger mismatch;
- grounding cannot be silently disabled for production RPG responses;
- soft truth is validated by class and provenance rather than treated as a hard fact.

### Phase 5 — Intent hypothesis and narrative-affordance resolver

Goal: Interpret unusual input before invoking a generic fallback.

Work:

- add broad intent and affordance families;
- produce one or more hypotheses with confidence and required evidence;
- distinguish unsupported mechanics from unknown lore, ambiguous references, player claims, impossible actions, and social improvisation;
- translate the player's underlying goal into supported actions where possible;
- add deterministic low-confidence policies that prefer an in-world question, inspection, or lead over inert prose.

Acceptance:

- every baseline unsupported scenario receives a typed recovery classification;
- the classifier cannot mutate state;
- the selected affordance is visible in reports;
- ambiguous inputs do not default directly to the generic narration fallback.

### Phase 6 — Local knowledge and lore retrieval

Goal: Exhaust relevant local knowledge before using Hermes.

Retrieval order:

1. resolved current-turn facts;
2. current scene and visible entities;
3. active speaker biography, knowledge boundaries, relationships, and memory;
4. party knowledge and recent dialogue;
5. journal, quests, clues, rumors, and chronicle;
6. campaign history and discovered world events;
7. structured lorebook and world-pack entries;
8. approved generated proposals.

Work:

- introduce evidence records with source, visibility, confidence, timestamp, and entity IDs;
- add entity aliases and fuzzy reference resolution;
- prevent hidden-event leakage;
- cache stable lore retrieval by world-pack/version and entity ID;
- return partial and conflicting evidence explicitly.

Acceptance:

- retrieval is deterministic for the same state and query;
- hidden facts never reach the narrator context;
- NPC answers are limited by NPC knowledge unless the narrator mode allows broader exposition;
- local retrieval latency is reported separately.

### Phase 7 — RPG Hermes recovery adapter

Goal: Use Hermes when local retrieval cannot produce a satisfying forward path.

Work:

- add an RPG-specific, proposal-only Hermes request and result schema;
- send compact evidence and the unresolved question, not the entire raw save state;
- require structured evidence, inference, uncertainty, forward strategies, and proposals;
- prohibit execution and direct state mutation;
- use bounded timeout, cancellation, retry, and circuit-breaker policies;
- cache safe research results by campaign/lore version and normalized query;
- fall back to local recovery without blocking the turn indefinitely;
- support streaming delivery without promising a future answer that the runtime cannot actually deliver.

Acceptance:

- Hermes unavailability never prevents a valid in-world response;
- all Hermes-derived facts retain provenance and truth class;
- no Hermes result can directly create a state delta;
- baseline reports show why Hermes was or was not invoked.

### Phase 8 — Soft-truth proposal acceptance

Goal: Allow careful world expansion without surrendering determinism.

Work:

- add proposal types for rumor leads, investigative targets, ambient objects, NPC references, location stubs, quest seeds, and lore annotations;
- define risk tiers:
  - low risk: reversible ambient detail;
  - medium risk: rumor, lead, stub, or future hook;
  - high risk: progression, reward, location move, combat result, or canonical identity;
- create deterministic acceptance policies using world rules, seed, duplication checks, visibility, and consistency constraints;
- record accepted proposals as explicit simulation events;
- keep rejected proposals available only as non-persistent inference when safe.

Acceptance:

- accepted proposals replay identically;
- high-risk proposals always require an existing deterministic resolver;
- every persisted addition has source, seed, acceptance reason, and event ID;
- save/load preserves accepted proposals without duplication.

### Phase 9 — Forward-motion policy and recovery strategies

Goal: Make useful progression a first-class validation criterion.

Work:

- require a `forward_strategy` for unresolved turns;
- implement strategies such as:
  - answer with bounded uncertainty;
  - offer a knowledgeable NPC or source;
  - reveal an approved clue;
  - start or advance an investigation;
  - propose a valid substitute action;
  - translate an impossible action into an in-world equivalent;
  - create a social consequence;
  - expose a meaningful failure and alternative;
  - offer a small set of grounded choices;
- integrate loop detection so repeated no-progress recovery changes strategy;
- coordinate with the world director, journal, and rumor-to-lead pipeline.

Acceptance:

- at least 95% of unsupported-input fixtures produce an answer, reaction, lead, choice, consequence, or valid alternative;
- generic inert fallback rate is below 1% on the fixture corpus;
- repeated recovery attempts do not loop on the same suggestion;
- all suggested actions are valid or explicitly framed as proposals.

### Phase 10 — Deterministic fallback library rewrite

Goal: Make the final degraded path specific, natural, and useful.

Work:

- replace one-size-fits-all fallbacks with mode-specific templates;
- populate templates only from authoritative facts, visible evidence, NPC stance, and selected forward strategy;
- remove meta language and phrases banned by the quality policy;
- provide failure-with-consequence and failure-with-alternative variants;
- ensure deterministic variation by seed without changing facts.

Acceptance:

- no fallback references internal architecture;
- every fallback addresses the current player input;
- fallback prose passes the same final quality gate as provider prose;
- fallbacks remain available when all model and Hermes calls fail.

### Phase 11 — Narration pipeline convergence and fixup removal

Goal: Make one explicit response-generation dependency graph authoritative.

Work:

- define a canonical `RpgResponseGenerator` orchestration service;
- select one provider-generation implementation and adapt the other path as a compatibility wrapper;
- remove star-import facades, import-order behavior, monkey patches, and fixup modules;
- inject parser, grounding validator, retriever, Hermes adapter, quality gate, renderer, and profile registry explicitly;
- preserve existing public turn APIs during migration;
- add source guards preventing new bypass paths.

Acceptance:

- one orchestration service owns final candidate selection and rendering;
- imports no longer alter runtime behavior by side effect;
- old and new paths produce equivalent authoritative deltas;
- compatibility wrappers are tracked for later deletion.

### Phase 12 — Prompt profiles, model routing, streaming, and latency

Goal: Improve prose without making every unusual turn expensive.

Work:

- make the prompt-profile registry authoritative for provider, model, temperature, token budget, timeout, retries, streaming, and blocking/deferred behavior;
- use deterministic or lightweight local classification for intent and affordance routing;
- reserve stronger prose models for high-value responses;
- invoke Hermes only after local retrieval and confidence checks;
- cache stable entity cards, lore evidence, and research results;
- stream the chosen response while preserving final validation boundaries;
- record time spent in resolver, retrieval, Hermes, generation, validation, repair, and rendering.

Acceptance:

- known utility and mechanic actions avoid heavy generation;
- normal supported turns do not incur Hermes latency;
- recovery timeout has a strict upper bound and a useful local fallback;
- 20-turn benchmarks show no regression in normal-turn latency;
- the program continues toward sub-5-second human-equivalent blocking turns.

### Phase 13 — Developer observability and player-facing presentation

Goal: Make the system auditable without exposing machinery during play.

Developer report fields:

- raw player input;
- interpreted intent and affordance;
- resolver result;
- retrieval sources and visibility decisions;
- Hermes request decision and status;
- recovery plan and proposals;
- claim ledger;
- candidate scores and rejection reasons;
- final quality issues and repair actions;
- selected response mode and budget;
- latency by stage;
- final visible response.

Player-facing behavior:

- natural prose only;
- optional concise indicators for journal updates, discovered clues, accepted leads, or state changes;
- no raw prompts, grounding labels, proposal schemas, or model errors.

Acceptance:

- every final response can be traced to evidence and a selection decision;
- reports separate hard truth, soft truth, inference, rumor, and proposal;
- telemetry contains no hidden prompt or private-memory content by default.

### Phase 14 — Regression, autoplay, and release gates

Goal: Prove that fluidity improved without weakening correctness.

Tests:

- unit tests for every new contract and policy;
- golden tests for response modes and deterministic fallback rendering;
- adversarial grounding tests;
- hidden-information leakage tests;
- unsupported-input recovery fixtures;
- Hermes unavailable, timeout, malformed response, conflicting evidence, and cancellation tests;
- save/load and replay tests for accepted proposals;
- 100-turn campaigns emphasizing dialogue, lore questions, unusual actions, investigation, combat, economy, travel, and companions;
- 1000-turn endurance runs for loop detection, memory pressure, proposal duplication, and latency drift.

Release gates:

- zero unsupported hard-state claims in deterministic coverage;
- zero direct LLM or Hermes state mutation paths;
- at least 95% forward-motion rate for unsupported-input fixtures;
- less than 1% generic inert fallback rate;
- no hidden-fact leakage;
- no repeated-action duplication in final rendering;
- replay hash stability for identical seeds and accepted proposals;
- normal-turn p95 latency does not regress beyond the agreed budget;
- RPG Phase 0 architecture compliance and RPG deterministic PR gates pass on the exact PR head SHA.

### Phase 15 — Staged rollout and legacy removal

Goal: Replace the existing behavior safely.

Rollout:

1. shadow mode records new classifications, candidate scores, and recovery plans without changing visible text;
2. renderer-only mode enables canonical rendering while keeping existing candidate generation;
3. quality-gate mode enables final selection and repair;
4. local-recovery mode enables affordances and lore retrieval;
5. Hermes-recovery mode enables bounded agent research;
6. proposal-acceptance mode enables low- and medium-risk persistent additions;
7. canonical pipeline becomes default;
8. compatibility wrappers, old fallbacks, and fixup modules are deleted.

Acceptance:

- every stage has a feature flag and rollback path;
- reports compare legacy and new output during shadowing;
- no state migration is irreversible without a documented downgrade path;
- legacy deletion occurs only after production and autoplay evidence meets release gates.

## 12. Recommended PR sequence

| PR | Slice | Depends on |
|---:|---|---|
| 1 | baseline scenario corpus and metrics | none |
| 2 | response modes, envelope, and canonical renderer | PR 1 |
| 3 | final candidate scoring and post-selection quality gate | PR 2 |
| 4 | typed `NarrationContext` compiler | PR 2 |
| 5 | typed `ClaimLedger` and exact validators | PR 4 |
| 6 | intent hypothesis and narrative-affordance classifier | PR 1 |
| 7 | local evidence and lore retrieval | PR 4, PR 6 |
| 8 | deterministic recovery-plan coordinator | PR 6, PR 7 |
| 9 | RPG proposal-only Hermes adapter | PR 8 |
| 10 | soft-truth classes and proposal schemas | PR 5, PR 8 |
| 11 | deterministic proposal acceptance and replay events | PR 10 |
| 12 | forward-motion strategies and loop breaking | PR 8, PR 10 |
| 13 | mode-specific deterministic fallback library | PR 2, PR 12 |
| 14 | canonical `RpgResponseGenerator` orchestration | PR 3-13 |
| 15 | remove fixups, monkey patches, and duplicate pipeline ownership | PR 14 |
| 16 | authoritative prompt/model profiles and performance pass | PR 14 |
| 17 | developer trace and UI/report surfaces | PR 14 |
| 18 | 100-turn/1000-turn gates and staged default rollout | PR 15-17 |

## 13. Suggested module boundaries

Names may be adjusted to match repository conventions, but responsibilities should remain explicit.

```text
src/app/rpg/response_generation/
    contracts.py
    context_compiler.py
    claim_ledger.py
    intent_affordance.py
    retrieval.py
    recovery.py
    hermes_adapter.py
    proposal_policy.py
    candidate_ranker.py
    quality_gate.py
    renderer.py
    fallback_library.py
    profiles.py
    orchestration.py
    telemetry.py
```

Existing modules under `src/app/rpg/narration`, `src/app/rpg/ai`, `src/app/rpg/narration_quality`, and `src/app/rpg/session` should migrate behind these boundaries rather than being duplicated again.

## 14. Completion definition

This roadmap is complete when:

- the RPG has one canonical response-generation pipeline;
- the player receives a direct, natural, mode-appropriate response to the latest input;
- unsupported input is normally transformed into grounded gameplay rather than generic prose;
- lore and memory are searched before deeper agent research;
- Hermes can research and propose but cannot mutate state;
- soft truth is typed, attributed, and promoted to hard truth only through deterministic acceptance;
- final output is grounded and quality-checked after selection and rendering;
- deterministic fallbacks remain specific and forward-moving even with every model unavailable;
- prompt/model profiles and response budgets are enforced centrally;
- monkey patches and duplicate narrator ownership are removed;
- replay, save/load, CI, 100-turn, and 1000-turn evidence demonstrate both state integrity and fluid progression.

## 15. Status log

- 2026-07-10: Roadmap created from the RPG response-generation architecture review and the decision to prioritize fluid progression, graceful improvisation, lore retrieval, and bounded Hermes-assisted recovery while preserving deterministic state authority.
