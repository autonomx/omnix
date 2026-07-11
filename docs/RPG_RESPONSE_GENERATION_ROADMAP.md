# RPG Response Generation and Narrative Continuity Roadmap

Status: proposed implementation source of truth  
Created: 2026-07-10  
Revised: 2026-07-10 after architecture review  
Source of truth: `main`

Primary principle:

> **Maximize meaningful forward motion, subject to authoritative truth, lore consistency, and player agency.**

## 1. Vision

Build one response-generation system that makes the RPG feel like a living world rather than a command parser.

The system should:

- resolve supported actions through deterministic mechanics;
- answer the player's latest statement or question before adding flavor;
- treat unsupported or uncertain input as an interpretation and recovery problem, not as a reason to emit generic text;
- search current state, memories, campaign history, lore, and world packs for relevant information;
- use Hermes for bounded research and proposal generation only when local knowledge is insufficient;
- transform impossible, unsupported, or anachronistic requests into the nearest meaningful in-world option;
- create a grounded answer, reaction, lead, choice, consequence, or investigation path on nearly every turn;
- avoid confidently misinterpreting the player, canonizing arbitrary inventions, exposing hidden lore, or imposing consequences from a weak guess;
- keep inventory, currency, health, combat, travel, quest, relationship, discovery, and persistent world changes simulation-authoritative;
- remain fast, streamable, replayable, auditable, and reversible when interpretation confidence is low.

The product goal is not "flow over correctness." State integrity, lore consistency, visibility, speaker knowledge, and player agency are all correctness requirements. Fluidity is optimized only inside those boundaries.

## 2. Non-negotiable boundaries

### 2.1 Hard truth remains simulation-owned

The LLM, retrieval layer, renderer, quality repair, and Hermes may not directly mutate:

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
- low-risk ambient details that remain turn- or scene-scoped;
- proposals that do not become persistent until accepted by a deterministic policy.

Soft truth must carry provenance, visibility, certainty, and lifetime. It becomes hard truth only through deterministic acceptance.

### 2.3 Player agency is a hard requirement

Recovery must distinguish between offering a path and taking that path.

Invariants:

- low-confidence interpretation may ask an in-world question or offer alternatives;
- a proposed lead is not automatically accepted as the player's objective;
- an investigation is not automatically started merely because it is a useful option;
- irreversible consequences require clear player intent or an existing deterministic mechanic;
- uncertain recovery actions should be reversible;
- the system may reinterpret an impossible method, but should preserve the player's underlying goal;
- a player assertion is not canon solely because it was stated confidently;
- consequences may follow an attempted action only when the simulation resolves the attempt or the player clearly chose it.

### 2.4 Visibility and lore consistency are hard requirements

- hidden facts may never reach player-visible context or prose;
- NPC dialogue is limited by that NPC's knowledge, beliefs, memory, and permitted inference;
- omniscient narration may use only player-visible or explicitly revealable evidence;
- conflicting lore must remain conflicting unless an authoritative source resolves it;
- generated detail must not silently override world-pack canon.

### 2.5 The player should not see internal failure language

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
5. Grounding relies heavily on text-pattern checks rather than typed references to claims allowed by the resolved turn.
6. Grounded safe fallbacks can be ranked below older authoritative narration even when the older text answers the current input less directly.
7. Deterministic fallbacks can be generic, meta, repetitive, or inconsistent with the quality policy.
8. Import-order fixups and runtime monkey patches make actual narration behavior difficult to reason about and test.
9. Response-length rules and model settings are duplicated across prompt builders and runtime code.
10. Unsupported inputs are too likely to collapse into safe but inert responses instead of becoming useful gameplay.
11. Generated world details do not yet have explicit turn, scene, and persistent lifetimes.
12. Token streaming can expose prose before complete grounding and quality validation.

## 4. Target architecture

A thin canonical `RpgResponseGenerator` must own the flow early in the implementation. It may initially delegate to legacy components, but all subsequent work plugs into this interface rather than integrating separately with both narration paths.

```text
Player input
    -> RpgResponseGenerator.generate(ResponseRequest)
         -> current-turn intent and affordance hypotheses
         -> deterministic mechanic resolver, when supported
         -> recovery coordinator, when unresolved or incomplete
              -> local state and scene retrieval
              -> NPC persona, knowledge, relationship, and memory retrieval
              -> journal, campaign history, lorebook, and world-pack retrieval
              -> bounded Hermes research, when justified
              -> recovery plan and forward-motion proposals
         -> typed NarrationContext compiler
         -> candidate generation as SemanticResponsePlan objects
         -> hard eligibility gates
              -> hard-state claims valid
              -> hidden-information policy valid
              -> speaker and knowledge scope valid
              -> proposal permissions valid
              -> player agency preserved
         -> ranking among eligible candidates
              -> current-turn relevance
              -> forward motion
              -> specificity
              -> naturalness
              -> repetition and style
         -> render proposed visible response
         -> evaluate final visible quality
         -> deterministic repair, or one bounded provider rewrite
         -> revalidate all claims, visibility, speaker scope, proposals, and agency
         -> rerender after successful repair or rewrite
         -> final quality check
         -> publish approved text by sentence or audio chunk
         -> persistence, telemetry, and replay metadata
```

Only deterministic resolvers and proposal-acceptance policies may produce authoritative state deltas.

A beautiful but ineligible candidate must always lose to an awkward eligible candidate. Grounding, visibility, speaker validity, proposal permissions, and player agency are gates, not weighted style scores.

## 5. Core contracts

### 5.1 `ResponseRequest`

The stable entry contract for `RpgResponseGenerator`.

Required fields:

- schema version and turn ID;
- raw player input;
- current authoritative turn result, when already resolved;
- session, world, scene, player, party, and speaker identifiers;
- current runtime mode and delivery capabilities;
- provider and latency policy;
- feature flags for shadowing and staged rollout.

### 5.2 `NarrationContext`

One compact, versioned context assembled for candidate generation.

Required fields:

- response mode;
- raw player input;
- interpreted intent hypotheses and confidence;
- must-answer question or requested outcome;
- resolved mechanic result;
- visible state facts;
- current scene and present entities;
- active speaker card;
- relevant NPC knowledge, personality, relationship, and memory;
- relevant journal, quest, lore, and campaign-history evidence;
- approved turn- or scene-scoped soft truth;
- allowed claims and forbidden claims;
- continuity constraints;
- agency and reversibility constraints;
- tone and style profile;
- response word budget;
- latency and provider profile.

The prompt must be current-turn-first. Large raw state objects should not be passed when a typed compact card is sufficient.

### 5.3 `ClaimLedger`

A machine-checkable record derived from authoritative state and the resolved turn.

It explicitly describes:

- allowed speakers;
- speaker knowledge scopes;
- allowed location statements and whether movement occurred;
- currency and inventory deltas;
- service-payment results;
- combat participants, damage, defeat, loot, and XP;
- quest and objective changes;
- relationship and faction deltas;
- facts newly discovered this turn;
- facts known only to an NPC;
- facts hidden from the player;
- proposals approved for a specific lifetime;
- claims that are prohibited.

The ledger defines what may be claimed. It does not by itself prove which claims arbitrary prose contains.

### 5.4 `SemanticResponsePlan`

The required intermediate representation between candidate generation and prose rendering.

Suggested shape:

```json
{
  "mode": "dialogue",
  "sections": [
    {
      "type": "npc_dialogue",
      "speaker_id": "npc_bran",
      "claim_refs": [
        "service.room_available",
        "service.room_price"
      ],
      "soft_truth_refs": [],
      "text": "Five silver for the night."
    }
  ],
  "forward_strategy": "answer_directly",
  "agency_effect": "offer_only",
  "proposal_refs": []
}
```

Rules:

- every factual section references typed ledger or soft-truth entries;
- atmospheric prose may omit claim references only when it carries no hard-state or hidden-lore claim;
- dialogue sections must identify a valid speaker;
- proposal sections must identify lifetime, risk, and acceptance status;
- the renderer consumes approved semantic sections rather than independently concatenating prose fields;
- prose-level regex and semantic claim extraction remain defense-in-depth checks.

### 5.5 `RecoveryPlan`

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
  "agency_effect": "offer_only",
  "reversibility": "fully_reversible",
  "proposals": [],
  "must_not_claim": []
}
```

### 5.6 `ResponseCandidate`

Each candidate carries structured metadata rather than only prose:

- `SemanticResponsePlan`;
- source: provider, deterministic, recovery, or Hermes-assisted;
- response mode;
- hard-gate decisions and rejection reasons;
- current-turn relevance score;
- forward-motion score;
- specificity score;
- naturalness score;
- repetition and style issues;
- latency and provider metadata;
- proposal references;
- repair and revalidation history.

Grounding and speaker validity are not ranking scores. They are eligibility decisions.

### 5.7 `RenderedResponse`

The renderer assembles only fields appropriate for the response mode. It must not blindly concatenate every available field.

Required metadata:

- final text;
- approved semantic section IDs;
- resolved claim references;
- truth classes and lifetimes used;
- selected response mode and budget;
- repair and rewrite history;
- validated delivery unit boundaries;
- final quality report.

## 6. Hard eligibility gates and ranking

### 6.1 Hard eligibility gates

A candidate is ineligible when any of these fail:

- hard-state claims match the `ClaimLedger`;
- player-visible prose contains no hidden information;
- all speakers are present or otherwise valid for the mode;
- each speaker remains within permitted knowledge and belief scope;
- proposal types, risk levels, lifetimes, and acceptance status are valid;
- player agency is preserved;
- irreversible consequences are authorized by intent or mechanics;
- semantic sections have valid claim references;
- no direct LLM or Hermes mutation path exists.

Ineligible provider candidates may be repaired only when the violation is mechanically removable without changing intended meaning. Otherwise they are rejected.

### 6.2 Ranking among eligible candidates

Eligible candidates are ranked by:

1. current-turn relevance and directness;
2. useful forward motion;
3. specificity supported by evidence;
4. continuity with the current scene and recent turns;
5. naturalness and character voice;
6. concise contract coverage;
7. low repetition and low style debt;
8. latency and provider cost as tie breakers.

A grounded safe fallback must outrank stale prior narration that does not answer the current input.

## 7. Final quality and revalidation cycle

The exact cycle is:

```text
generate candidates
    -> validate semantic plans and hard gates
    -> select highest-ranked eligible candidate
    -> render proposed visible response
    -> evaluate final visible quality
    -> deterministic repair when possible
       or one bounded provider rewrite when required
    -> re-extract and revalidate claims, visibility, speaker scope, proposals, and agency
    -> rerender
    -> final quality check
    -> publish
```

Rules:

- quality evaluation inspects the text the player will actually see;
- deterministic repairs may remove labels, duplicate sentences, repeated summaries, and banned meta language;
- deterministic repairs may not add facts;
- a provider rewrite must pass the complete eligibility gate again;
- a failed rewrite does not replace the previously eligible candidate;
- at most one provider rewrite is allowed on the blocking path;
- final output contains no internal system terminology.

## 8. Response modes and default budgets

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

## 9. Unknown-input recovery policy

When a normal resolver cannot directly execute the player's request, the game attempts the following in order:

1. Resolve the underlying goal through an existing mechanic.
2. Answer socially through an NPC's knowledge, belief, memory, or uncertainty.
3. Retrieve relevant facts from visible state, journal, campaign history, lorebook, and world packs.
4. Ask Hermes to research or synthesize proposals when local retrieval remains insufficient and the turn warrants added latency.
5. Convert the input into a supported investigation, social action, inspection, substitution, travel lead, or proposed world action.
6. Ask an in-world clarification when interpretation confidence is too low for safe action.
7. Return an in-world failure that creates a consequence, alternative, or next step without inventing success.

The final response should normally leave the player with at least one of:

- an answer;
- an NPC reaction;
- a discovered clue already approved by the simulation;
- a grounded lead offered for consideration;
- a meaningful choice;
- a resolved consequence;
- a valid alternative action;
- an explicit uncertainty worth investigating.

Forward motion does not require automatic state progression. Offering a viable path is sufficient when the player has not chosen it.

## 10. Narrative affordance families

The recovery classifier maps unusual input into broad affordances rather than exact command syntax.

| Player input class | Recovery affordance |
|---|---|
| unknown person, place, item, faction, or event | knowledge check, lore search, rumor, clarification, or lead |
| unsupported object use | inspect, improvise, substitute, craft, or ask for help |
| unsupported spell or power | arcana attempt, ritual research, analogous skill check, or consequential failure |
| unknown travel destination | memory/map search, ask directions, offer a lead, or reject as unverified |
| invented prior history | memory search, treat as an unverified player claim, or invite clarification in-world |
| invented NPC | search known entities, interpret as a description, or create a turn-scoped lead proposal |
| impossible technology | translate the underlying goal into a world-appropriate method |
| unusual social action | persuasion, deception, intimidation, insight, performance, etiquette, or relationship check |
| broad world question | retrieve lore and answer from the current speaker's perspective |
| request beyond current mechanics | simulate the nearest safe abstraction or offer supported alternatives |

Low-confidence hypotheses must prefer clarification, inspection, or alternatives over imposed actions.

## 11. Hermes role and safety boundary

Hermes acts as a bounded investigator and proposal generator, not as the authoritative game master.

Hermes may:

- search relevant campaign and lore sources;
- reconcile multiple pieces of visible evidence;
- identify related NPCs, locations, factions, quests, and events;
- suggest interpretations and forward strategies;
- generate proposed lore additions, rumors, clues, or quest seeds;
- rank possible response plans and explain missing information;
- return structured evidence, inference, uncertainty, and proposal objects.

Hermes may not:

- mutate RPG state;
- mark quests complete;
- grant inventory, currency, XP, skills, or relationships;
- move the player;
- create confirmed locations, people, or events without simulation acceptance;
- execute tools or external actions on behalf of the RPG recovery path;
- expose hidden world facts to the player unless retrieval policy marks them visible;
- accept a path on the player's behalf.

The existing proposal-only Hermes pattern should be reused with RPG-specific schemas, compact evidence, bounded timeouts, cancellation, explicit provenance, and a local-recovery fallback.

Hermes is invoked only after local retrieval and confidence checks. Its unavailability must never prevent a valid in-world response.

## 12. Truth classes, lifetimes, and promotion

### 12.1 Truth classes

Every non-authoritative fact used during recovery has one class:

- `confirmed_fact` — already authoritative and player-visible;
- `retrieved_lore` — authoritative lore available to this speaker or player;
- `npc_belief` — a character's belief, which may be wrong;
- `rumor` — attributed and unconfirmed;
- `inference` — reasoned from evidence but not confirmed;
- `generated_proposal` — candidate world addition awaiting acceptance;
- `unverified_player_claim` — asserted by the player but not established;
- `hidden_fact` — authoritative but unavailable to the player and prohibited from narration.

### 12.2 Lifetimes

Generated details are ephemeral by default:

- `turn_scoped` — description, speculation, or suggestion used only in the current response;
- `scene_scoped` — temporary object, rumor, conversational reference, or working hypothesis available until scene exit or expiry;
- `persistent` — explicit simulation event stored in save/load and replay state.

Promotion rules:

- turn-scoped content may be used without persistence when eligible;
- scene-scoped content requires a deterministic scene proposal policy;
- persistence requires player interaction, repeated relevance, explicit world-director acceptance, or an existing mechanic;
- high-risk content always requires an existing deterministic resolver;
- persistence never occurs merely because generated prose sounded plausible.

### 12.3 Proposal controls

- per-turn, per-scene, and per-campaign proposal budgets;
- deduplication by normalized entity, relation, and source evidence;
- expiry and garbage collection for scene-scoped details;
- promotion history and provenance;
- deterministic acceptance reason and event ID;
- save/load idempotency;
- rejection does not erase safe turn-scoped inference.

## 13. Validated streaming contract

Complete token streaming conflicts with post-generation grounding. Initial implementation must not expose unvalidated tokens.

Required policy:

1. Generate a complete short candidate or complete semantic section.
2. Run hard eligibility gates.
3. Render and run the quality/revalidation cycle.
4. Split the approved response into sentence or audio-phrase delivery units.
5. Stream only approved units.
6. Preserve cancellation and interruption semantics.

No text or audio chunk becomes player-visible before its containing approved unit has passed validation.

Future incremental validation may validate one semantic section at a time, but it must preserve the same claim-reference and visibility guarantees.

## 14. Implementation phases

Each phase lands as a narrow, auditable PR with deterministic tests and a roadmap status update.

### Phase 0 — Labeled baseline corpus and metrics

Goal: Measure current behavior with reliable expectations before changing routing or prose.

Work:

- create human-authored fixtures covering supported actions, unknown lore, invented entities, unsupported spells, impossible technology, ambiguous social actions, contradictory player claims, failed purchases, invalid travel, combat edge cases, and agency-sensitive recovery;
- label expected affordance families, allowed truth classes, forbidden claims, acceptable forward outcomes, and whether clarification is required;
- create a deterministic stub-provider corpus for CI;
- create a separate opt-in live-model benchmark for prose and latency evaluation;
- maintain a hidden holdout set not used to tune prompts or deterministic policies;
- capture current final responses, candidate source, grounding decision, latency, repetition, and fallback reason;
- define metrics:
  - generic fallback rate;
  - labeled outcome compliance;
  - current-turn answer rate;
  - forward-motion rate;
  - agency-violation rate;
  - unsupported hard-state claim rate;
  - hidden-information leakage rate;
  - repeated-content rate;
  - stale-response selection rate;
  - local-retrieval hit rate;
  - Hermes invocation, success, timeout, and usefulness rates;
  - p50 and p95 blocking latency by response mode.

Acceptance:

- no runtime behavior changes;
- fixtures and labels are versioned;
- deterministic CI metrics do not depend on live-model wording;
- reports distinguish final visible text from intermediate candidates;
- live-model results are informational unless a stable target environment is explicitly designated.

### Phase 1 — Core contracts, thin orchestrator, response modes, and renderer

Goal: Establish canonical ownership before adding more subsystems.

Work:

- create `ResponseRequest`, `SemanticResponsePlan`, `ResponseCandidate`, and `RenderedResponse` contracts;
- introduce a thin `RpgResponseGenerator.generate()` entry point;
- initially delegate candidate generation to legacy implementations behind adapters;
- add typed response modes and one field-aware renderer;
- prevent automatic concatenation of narration, result, action, and dialogue when they repeat the same event;
- keep authoritative deltas available to UI and reports without forcing them into prose;
- route both runtime and world-scene entry points through the orchestrator in shadow or compatibility mode.

Acceptance:

- one service owns final visible assembly;
- no response repeats the same resolved action in multiple labeled sections unless the mode explicitly requires it;
- existing authoritative state and turn contracts are unchanged;
- snapshot tests cover every response mode;
- subsequent phases integrate only through the canonical orchestrator.

### Phase 2 — Hard eligibility gates, ranking, quality, repair, and revalidation

Goal: Make safety non-negotiable and evaluate the actual visible result.

Work:

- implement hard gates for state claims, visibility, speaker scope, proposal permissions, and player agency;
- rank only eligible candidates;
- ensure grounded safe candidates outrank stale prior narration;
- render the selected semantic plan;
- run repetition, low-value phrase, opening-pattern, overlap, and style checks on final visible text;
- add deterministic repairs for removable labels, duplicate sentences, repeated action summaries, and banned meta language;
- allow at most one bounded provider rewrite;
- re-extract and revalidate all claims after repair or rewrite;
- retain the last eligible candidate when a rewrite fails.

Acceptance:

- no weighted prose score can override a failed hard gate;
- quality reports describe the final visible response;
- rewrite-introduced unsupported facts are rejected;
- final output contains no internal system terminology.

### Phase 3 — Compact `NarrationContext`, `ClaimLedger`, and semantic claim references

Goal: Reduce prompt overload and make factual validation explicit.

Work:

- create the versioned context compiler;
- derive a typed `ClaimLedger` from the resolved turn and visible state;
- require `SemanticResponsePlan` sections to reference ledger or soft-truth entries;
- include only relevant scene, entity, memory, quest, lore, and continuity cards;
- make the player's latest statement or question and must-answer objective first-class;
- replace repeated special-case prompt prose with typed constraints;
- centralize response budgets and tone/style profiles;
- retain regex, named-fact checks, and semantic claim extraction as defense in depth;
- record context omissions and truncation decisions in developer traces.

Acceptance:

- both narration paths consume the same context contract through the orchestrator;
- prompt size decreases materially on the baseline corpus;
- each factual semantic section has valid claim references;
- hidden information cannot enter player-visible context;
- grounding cannot be silently disabled for production RPG responses.

### Phase 4 — Intent hypotheses, local retrieval, and narrative affordances

Goal: Interpret unusual input using available world knowledge before using Hermes.

Retrieval order:

1. resolved current-turn facts;
2. current scene and visible entities;
3. active speaker biography, knowledge boundaries, relationships, and memory;
4. party knowledge and recent dialogue;
5. journal, quests, clues, rumors, and chronicle;
6. campaign history and discovered world events;
7. structured lorebook and world-pack entries;
8. approved turn-, scene-, or persistent proposals.

Work:

- add broad intent and affordance hypotheses with confidence and evidence requirements;
- distinguish unsupported mechanics, unknown lore, ambiguous references, player claims, impossible actions, and social improvisation;
- introduce evidence records with source, visibility, confidence, timestamp, and entity IDs;
- add aliases and fuzzy reference resolution;
- prevent hidden-event leakage;
- limit NPC answers to NPC knowledge and beliefs;
- cache stable lore retrieval by world-pack/version and entity ID;
- produce explicit partial and conflicting evidence results;
- route low-confidence cases toward clarification or reversible options.

Acceptance:

- every baseline unsupported scenario receives a typed recovery classification;
- retrieval is deterministic for the same state and query;
- hidden facts never reach narrator context;
- classifier and retriever cannot mutate state;
- local retrieval latency is reported separately.

### Phase 5 — Forward-motion strategies and mode-specific deterministic fallbacks

Goal: Make useful, agency-preserving progression available even when models fail.

Work:

- require a `forward_strategy`, `agency_effect`, and `reversibility` decision for unresolved turns;
- implement strategies such as:
  - answer with bounded uncertainty;
  - ask an in-world clarification;
  - offer a knowledgeable NPC or source;
  - reveal an already-approved clue;
  - offer an investigation without accepting it;
  - propose a valid substitute action;
  - translate an impossible method into an in-world equivalent;
  - resolve a mechanic-backed social consequence;
  - expose a meaningful failure and alternative;
  - offer a small set of grounded choices;
- integrate loop detection so repeated no-progress recovery changes strategy;
- coordinate with the world director, journal, and rumor-to-lead pipeline;
- replace one-size-fits-all fallbacks with mode-specific templates;
- populate templates only from authoritative facts, visible evidence, NPC stance, and selected strategy;
- ensure deterministic variation by seed without changing facts.

Acceptance:

- at least 95% of labeled unsupported-input fixtures produce an allowed answer, reaction, lead, choice, consequence, clarification, or valid alternative;
- generic inert fallback rate is below 1% on deterministic fixtures;
- agency-violation rate is zero;
- repeated recovery attempts do not loop on the same suggestion;
- every fallback addresses the current player input and passes the same hard gates and quality checks as provider prose.

### Phase 6 — RPG Hermes proposal-only recovery

Goal: Use Hermes only when local evidence cannot produce a satisfying forward path.

Work:

- add an RPG-specific proposal-only Hermes request and result schema;
- send compact visible evidence and the unresolved question, not the entire raw save state;
- require structured evidence, inference, uncertainty, forward strategies, and proposals;
- prohibit execution, direct state mutation, hidden-fact exposure, and player-choice acceptance;
- use bounded timeout, cancellation, retry, and circuit-breaker policies;
- cache safe research results by campaign/lore version and normalized query;
- fall back to local recovery without blocking indefinitely;
- record why Hermes was or was not invoked.

Acceptance:

- Hermes unavailability never prevents a valid in-world response;
- all Hermes-derived facts retain provenance, visibility, truth class, and lifetime;
- no Hermes result can directly create a state delta;
- normal supported turns do not incur Hermes latency;
- malformed or conflicting Hermes results fail closed to local recovery.

### Phase 7 — Ephemeral soft truth and bounded proposal promotion

Goal: Allow careful improvisation without accumulating generated clutter.

Work:

- implement turn-, scene-, and persistent lifetimes;
- add proposal types for rumors, investigative targets, ambient objects, NPC references, location stubs, quest seeds, and lore annotations;
- define risk tiers:
  - low risk: reversible turn- or scene-scoped detail;
  - medium risk: rumor, lead, stub, or future hook;
  - high risk: progression, reward, location move, combat result, canonical identity, or irreversible relationship effect;
- create deterministic acceptance policies using player interaction, repeated relevance, director approval, world rules, seed, duplication checks, visibility, and consistency;
- add proposal budgets, expiry, garbage collection, deduplication, and promotion history;
- record persistent promotions as explicit simulation events;
- keep rejected proposals only as non-persistent inference when safe.

Acceptance:

- ephemeral content is the default;
- accepted proposals replay identically;
- high-risk proposals always require an existing deterministic resolver;
- every persisted addition has source, seed, acceptance reason, lifetime history, and event ID;
- save/load preserves accepted proposals without duplication;
- 1000-turn runs do not show unbounded generated-world clutter.

### Phase 8 — Pipeline migration and fixup removal

Goal: Make the canonical dependency graph authoritative and understandable.

Work:

- migrate provider generation, parsing, grounding, retrieval, Hermes, ranking, quality, rendering, and profiles behind `RpgResponseGenerator`;
- select one provider-generation implementation and adapt the other path as a compatibility wrapper;
- remove star-import facades, import-order behavior, monkey patches, and fixup modules;
- preserve existing public turn APIs during migration;
- add source guards preventing new bypass paths;
- compare legacy and canonical outputs in shadow mode before deletion.

Acceptance:

- one orchestration service owns final candidate selection, validation, rendering, and publishing;
- imports no longer alter runtime behavior by side effect;
- old and new paths produce equivalent authoritative deltas;
- compatibility wrappers have explicit deletion checkpoints;
- no direct narration bypass can publish unvalidated text.

### Phase 9 — Authoritative profiles, validated streaming, and performance

Goal: Improve prose and responsiveness without making every unusual turn expensive.

Work:

- make the prompt-profile registry authoritative for provider, model, temperature, token budget, timeout, retries, blocking/deferred behavior, and delivery mode;
- use deterministic or lightweight local classification for intent and affordance routing;
- reserve stronger prose models for high-value responses;
- invoke Hermes only after local retrieval and confidence checks;
- cache stable entity cards, lore evidence, and research results;
- generate and validate complete short candidates before player-visible delivery;
- stream only approved sentence or audio-phrase units;
- preserve interruption, cancellation, and delivery reconciliation;
- record time spent in resolver, retrieval, Hermes, generation, validation, repair, rendering, and first approved delivery.

Acceptance:

- known utility and mechanic actions avoid heavy generation;
- normal supported turns do not incur Hermes latency;
- no unvalidated token or audio chunk becomes player-visible;
- recovery timeout has a strict upper bound and useful local fallback;
- deterministic 20-turn benchmarks show no normal-turn regression beyond the agreed budget;
- the program continues toward sub-5-second human-equivalent blocking turns.

### Phase 10 — Observability, regression, autoplay, and staged rollout

Goal: Prove that fluidity improved without weakening truth, lore consistency, or agency.

Developer report fields:

- raw player input;
- interpreted intent hypotheses and selected affordance;
- resolver result;
- retrieval sources and visibility decisions;
- Hermes request decision and status;
- recovery plan, agency effect, reversibility, and proposals;
- claim ledger;
- semantic response plan;
- hard-gate decisions and rejection reasons;
- ranking scores among eligible candidates;
- final quality issues and repair actions;
- selected response mode and budget;
- truth classes and lifetimes used;
- latency by stage;
- final visible response.

Tests:

- unit tests for every contract and policy;
- golden tests for response modes and deterministic fallback rendering;
- adversarial hard-state and hidden-information tests;
- speaker-knowledge boundary tests;
- player-agency and reversibility tests;
- unsupported-input recovery fixtures;
- Hermes unavailable, timeout, malformed response, conflicting evidence, and cancellation tests;
- rewrite revalidation tests;
- validated-streaming tests proving no unapproved unit is delivered;
- proposal expiry, garbage collection, save/load, and replay tests;
- 100-turn campaigns emphasizing dialogue, lore questions, unusual actions, investigation, combat, economy, travel, and companions;
- 1000-turn endurance runs for loop detection, memory pressure, proposal clutter, duplication, and latency drift.

Release gates:

- zero unsupported hard-state claims in deterministic coverage;
- zero direct LLM or Hermes state mutation paths;
- zero hidden-fact leakage;
- zero player-agency violations in labeled deterministic fixtures;
- at least 95% allowed forward-outcome compliance for unsupported-input fixtures;
- less than 1% generic inert fallback rate;
- no repeated-action duplication in final rendering;
- no unvalidated streaming exposure;
- replay hash stability for identical seeds and accepted proposals;
- bounded persistent proposal growth in endurance runs;
- normal-turn p95 latency does not regress beyond the agreed budget;
- RPG Phase 0 architecture compliance and RPG deterministic PR gates pass on the exact PR head SHA.

Staged rollout:

1. shadow mode records new classifications, semantic plans, hard gates, scores, and recovery plans without changing visible text;
2. renderer-only mode enables canonical rendering while keeping existing candidate generation;
3. eligibility-and-quality mode enables hard gates, ranking, repair, and revalidation;
4. compact-context mode enables `NarrationContext`, `ClaimLedger`, and semantic claim references;
5. local-recovery mode enables affordances and lore retrieval;
6. Hermes-recovery mode enables bounded agent research;
7. ephemeral-proposal mode enables turn- and scene-scoped details;
8. persistent-promotion mode enables bounded deterministic promotion;
9. validated-streaming mode publishes only approved delivery units;
10. canonical pipeline becomes default;
11. compatibility wrappers, old fallbacks, and fixup modules are deleted.

Every stage requires a feature flag, comparison report, and rollback path. Legacy deletion occurs only after production and autoplay evidence meets release gates.

## 15. Recommended PR sequence

| PR | Slice | Depends on |
|---:|---|---|
| 1 | labeled baseline corpus, stub-provider CI metrics, live benchmark harness, and holdout policy | none |
| 2 | core contracts, thin `RpgResponseGenerator`, response modes, and canonical renderer | PR 1 |
| 3 | hard eligibility gates, eligible-candidate ranking, final quality cycle, and rewrite revalidation | PR 2 |
| 4 | compact `NarrationContext`, typed `ClaimLedger`, and `SemanticResponsePlan` claim references | PR 2-3 |
| 5 | intent hypotheses, local evidence retrieval, speaker-knowledge boundaries, and affordance recovery | PR 4 |
| 6 | player-agency policy, forward-motion strategies, loop breaking, and deterministic fallback library | PR 5 |
| 7 | RPG proposal-only Hermes adapter with bounded failure behavior | PR 5-6 |
| 8 | truth classes, lifetimes, ephemeral details, proposal budgets, expiry, and promotion schemas | PR 4, PR 6-7 |
| 9 | deterministic proposal acceptance, replay events, deduplication, and garbage collection | PR 8 |
| 10 | migrate both narration paths behind the canonical orchestrator | PR 3-9 |
| 11 | remove fixups, monkey patches, star-import ownership, and narration bypasses | PR 10 |
| 12 | authoritative prompt/model profiles and validated sentence/audio-unit streaming | PR 10 |
| 13 | performance, caching, latency budgets, and first-approved-delivery telemetry | PR 12 |
| 14 | developer trace and player-facing state-change presentation | PR 10-13 |
| 15 | 100-turn/1000-turn gates, shadow comparisons, staged default rollout, and legacy deletion | PR 11-14 |

## 16. Suggested module boundaries

Names may be adjusted to match repository conventions, but responsibilities should remain explicit.

```text
src/app/rpg/response_generation/
    contracts.py
    orchestration.py
    context_compiler.py
    claim_ledger.py
    semantic_plan.py
    eligibility.py
    candidate_ranker.py
    quality_gate.py
    renderer.py
    intent_affordance.py
    retrieval.py
    recovery.py
    hermes_adapter.py
    truth_lifetime.py
    proposal_policy.py
    fallback_library.py
    profiles.py
    validated_delivery.py
    telemetry.py
```

Existing modules under `src/app/rpg/narration`, `src/app/rpg/ai`, `src/app/rpg/narration_quality`, and `src/app/rpg/session` should migrate behind these boundaries rather than being duplicated again.

## 17. Completion definition

This roadmap is complete when:

- the RPG has one canonical response-generation pipeline owned by `RpgResponseGenerator`;
- the player receives a direct, natural, mode-appropriate response to the latest input;
- unsupported input is normally transformed into grounded gameplay or an agency-preserving option rather than generic prose;
- lore and memory are searched before deeper agent research;
- Hermes can research and propose but cannot mutate state, expose hidden lore, or choose for the player;
- hard eligibility gates cannot be traded against prose quality;
- factual semantic sections reference typed allowed claims;
- provider rewrites are revalidated before publication;
- soft truth is typed, attributed, lifetime-bounded, and persistent only after deterministic promotion;
- generated world details are ephemeral by default and long campaigns do not accumulate uncontrolled clutter;
- deterministic fallbacks remain specific and forward-moving even with every model unavailable;
- no unvalidated text or audio unit is delivered to the player;
- prompt/model profiles and response budgets are enforced centrally;
- monkey patches and duplicate narrator ownership are removed;
- replay, save/load, CI, labeled fixtures, hidden holdouts, 100-turn, and 1000-turn evidence demonstrate state integrity, lore consistency, player agency, and fluid progression.

## 18. Status log

- 2026-07-10: Roadmap created from the RPG response-generation architecture review and the decision to prioritize graceful improvisation, lore retrieval, bounded Hermes-assisted recovery, and deterministic state authority.
- 2026-07-10: Roadmap revised after review to replace "flow over correctness" language with constrained forward motion; make truth, visibility, speaker scope, proposal permissions, and player agency hard eligibility gates; add `SemanticResponsePlan` claim references; revalidate provider rewrites; introduce `RpgResponseGenerator` in the first implementation slice; make generated details ephemeral by default; define validated sentence/audio-unit streaming; and require labeled deterministic metrics plus a separate live-model benchmark and hidden holdout set.
