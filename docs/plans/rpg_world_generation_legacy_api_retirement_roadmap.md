# RPG World Generation Legacy API Retirement and Trusted Authorship Roadmap

Status: planned

Parent roadmap: `docs/plans/rpg_world_scenario_map_roadmap.md`

## Objective

Retire the obsolete Adventure Builder world-generation workflow and make the durable World Library and World Forge pipeline the only production path for generated world lore.

The migration must preserve unrelated Adventure Builder setup, validation, preview, simulation, and launch functionality while establishing a stronger invariant:

> No player-facing lore may contain prose invented by application code. Every lore-bearing string must have trusted authorship provenance—normally LLM-authored, human-authored, or human-edited LLM content—while deterministic code may validate, organize, index, and render structured data.

This is deliberately narrower than banning all deterministic user-visible text. Page titles, field labels, status messages, validation findings, dates, prices, badges, tables, filters, relationship graphs, and deterministic formatting of structured facts remain allowed. Deterministic code must not invent narrative explanation, atmosphere, history, implications, motives, rumours, hooks, or descriptive lore prose.

## Architectural decision

The production world-generation authority is the durable World Forge pipeline:

- `POST /api/rpg/worlds/{world_id}/generation`
- `POST /api/rpg/world-generation/{run_id}/retry-failed`
- `POST /api/rpg/world-generation/{run_id}/continue`
- `GET /api/rpg/world-generation/{run_id}`
- `POST /api/rpg/world-generation/{run_id}/publish`
- `POST /api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/regenerate`
- `POST /api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/regenerate-dossier`
- `POST /api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/regenerate-dossier-preview`

The legacy generated-package workflow is not a second production generator and must not remain as a fallback when World Forge is unavailable.

Production construction must explicitly inject an approved provider-backed generator. Deterministic generators remain supported only when explicitly injected by tests, fixtures, migration checks, load tests, or offline developer tooling, and they must be structurally unable to produce publishable production lore.

## Lore and deterministic presentation boundary

### Deterministic code may produce

- stable IDs and references;
- hashes, fingerprints, revisions, and dependency metadata;
- schemas, validation findings, statuses, and error messages;
- mechanical and simulation values;
- fact-table labels and deterministic rendering of structured values;
- navigation labels, section headings, badges, filters, and relationship graphs;
- indexes, lookup records, and non-semantic formatting;
- structural transformations that preserve all prose-bearing string values.

### Trusted authored content is required for

- entity and canon names when names are generated rather than manually supplied;
- summaries, descriptions, dossier paragraphs, quotations, and readable documents;
- historical narrative, cultural explanation, atmosphere, and consequences;
- motives, goals, pressures, beliefs, relationships, and implications expressed as prose;
- rumours, hooks, quests, encounters, opening threads, and scenario narration;
- optional narrative explanations attached to structured facts.

A machine-readable fact such as `room_price = 5 silver` may be rendered deterministically as a fact-table row. A sentence such as “Bran keeps the price low to attract desperate travellers” is lore-bearing prose and requires trusted authorship.

## Authorship classes

Every lore-bearing field must resolve to one of these authorship classes:

- `llm_authored`;
- `human_authored`;
- `human_edited_llm`;
- `machine_structured`;
- `legacy_unknown`;
- `deterministic_fixture`;
- `deterministic_fallback`.

Publication policy:

- player-facing lore may use `llm_authored`, `human_authored`, or `human_edited_llm`;
- structured facts, mechanical values, UI metadata, and deterministic presentation may use `machine_structured`;
- `legacy_unknown`, `deterministic_fixture`, and `deterministic_fallback` cannot be published as player-facing lore;
- accepting, reviewing, or manually promoting a candidate must never silently change its authorship class.

## Field-level authorship policy

Topic-level `source="ai"` is too coarse because one topic may contain LLM-authored dossiers, human-edited summaries, machine-structured facts, mechanical values, and UI metadata.

World profile schemas must classify fields using an authorship policy equivalent to:

- `llm_required` — production AI generation must trace to an approved LLM artifact;
- `authored_required` — trusted LLM or human authorship is required;
- `machine_allowed` — deterministic structured values or rendering are permitted;
- `structural_only` — IDs, references, hashes, and schema metadata only.

The publication validator must recursively inspect the serialized topic against this policy and report the exact blocked field path.

## Trusted server-owned generation artifacts

Candidate-supplied provenance flags are assertions, not proof. Fields such as `used_llm=true`, `provider`, `model`, or `provider_authored_presentation=true` must not be trusted unless they resolve to a server-owned generation artifact.

Each successful provider response must create an immutable artifact containing at least:

- `generation_artifact_id`;
- `generation_run_id` and topic or entity job identity;
- approved provider and model identity;
- prompt and generator versions;
- raw provider response hash;
- parsed payload hash;
- timestamps and attempt number;
- authorship class;
- recorded structural transformations;
- source JSON pointers for extracted fields.

An origin ledger must map every lore-bearing field to:

- the serialized field path;
- authorship class;
- generation artifact ID or human edit event ID;
- source JSON pointer;
- exact content hash;
- parent origin when the field was human-edited or repaired.

Acceptance and publication must look up the artifact server-side, verify hashes, verify that recorded transformations are permitted, and reject forged, missing, mixed, or unknown origin.

## Legacy API removal scope

Remove or temporarily return `410 Gone` from these Adventure Builder generation endpoints:

- `POST /api/rpg/adventure/generate_world`
- `POST /api/rpg/adventure/generate-world`
- `POST /api/rpg/adventure/regenerate_section`
- `POST /api/rpg/adventure/regenerate_entity`
- `POST /api/rpg/adventure/apply_generated_package`
- `POST /api/rpg/adventure/fill_npc`

Retire the corresponding service and creator paths after all internal callers are removed:

- legacy world proposal generation in `adventure_world_service.py`;
- deterministic proposal fallback in `llm_world_generator.py`;
- deterministic NPC enrichment fallback;
- generated-package merge code that accepts client-supplied generated lore;
- tests and fixtures that treat deterministic fallback prose as a successful production result.

## Explicitly preserved scope

Do not remove unrelated Adventure Builder capabilities solely because they share the same router. Preserve and review independently:

- adventure templates;
- setup validation;
- adventure preview;
- simulation inspection and stepping;
- world comparison;
- launching or applying manually authored setup data where still required by the current campaign flow.

The `LegacyRpgCreateCampaignWizard` component name is not evidence of legacy world generation. It may continue to serve as a player and gameplay setup form while published worlds and scenarios come from the World Library.

## Replacement mapping

| Legacy operation | Durable replacement |
| --- | --- |
| Generate complete world package | Start a full World Forge generation run for the World Project |
| Regenerate one section | Start a selected-topic generation run with an explicit regeneration strategy |
| Regenerate one entity | Use the entity regeneration endpoint in the World Authoring API |
| Regenerate only rich lore | Preview or regenerate the entity dossier |
| Apply generated package | Persist validated provider results through server-owned artifacts, review the durable run, and publish it |
| Retry after provider failure | Retry failed topics or continue the durable run |
| Repair weak generated lore | Run bounded targeted LLM repair against explicit allowed paths |
| Inspect generation state | Read the durable generation run, candidate lineage, validation findings, and origin ledger |

## Phase 11.1 — Caller inventory and deprecation guard

Status: planned

Priority: P0

Work:

- search backend, web UI, tests, scripts, and documentation for all legacy endpoint and service references;
- identify any external or manual callers that are not visible in repository code;
- add structured deprecation logging to every legacy generation route;
- change legacy routes to return `410 Gone` with the supported World Forge replacement endpoints;
- ensure no route silently redirects to a different semantic operation;
- add telemetry or test assertions proving current UI generation uses only World Library and World Authoring clients.

Exit condition:

Every known caller is migrated or explicitly retired, and any unknown caller receives an actionable failure instead of deterministic generated lore.

## Phase 11.2 — Close deterministic production leaks

Status: planned

Priority: P0

Work:

- delete or isolate the legacy deterministic world proposal generator from production dependency graphs;
- remove deterministic NPC biography, personality, history, rumour, and lore enrichment fallbacks;
- remove deterministic dossier padding from provider-backed production paths;
- make entity and section regeneration fail closed when an approved LLM provider is unavailable;
- require an explicit generator dependency in `ReferenceSafeWorldForgeGenerator` and equivalent production constructors;
- retain deterministic generators only behind explicit test-mode boundaries where their output cannot be published or displayed as production lore;
- reject candidates whose trusted artifact identifies deterministic generation, fallback generation, test mode, or offline fixture generation.

Exit condition:

A missing provider dependency or provider failure produces a visible failed or retryable generation state and never produces a ready world, accepted entity, complete dossier, or user-visible fallback story text.

## Phase 11.3 — Remove arbitrary generated-package trust

Status: planned

Priority: P0

Work:

- remove `apply_generated_package` and its merge service, or during migration require a server-issued candidate or artifact ID instead of a client-provided package;
- prevent clients from submitting provenance fields and having arbitrary content relabelled as AI generated;
- require generated content to enter storage through a durable generation job, server-owned artifact, schema validation, authorship validation, review, and publication;
- preserve manual editing as an explicitly human-authored or human-edited source with separate immutable history;
- never convert a topic or entity to `source="ai"` merely because a user clicked Accept.

Exit condition:

All AI-generated world content has a durable run, immutable provider artifact, field-level origin records, validation result, and review or publication event. Forged client provenance cannot pass acceptance.

## Phase 11.4 — Field-level authorship and publication enforcement

Status: planned

Priority: P0

Work:

- add one shared `validate_publishable_authorship` boundary used by generation completion, candidate acceptance, topic saving, release creation, launch certification, and publication;
- add field-level authorship policy to every World Forge schema;
- recursively validate every lore-bearing field rather than trusting topic-level `source`;
- require approved provider identity, model, successful response artifact, content hash, source pointer, and permitted transformation history for LLM-authored fields;
- permit deterministic rendering only for `machine_allowed` or `structural_only` fields;
- permit manual prose only with explicit `human_authored` or `human_edited_llm` origin history;
- reject mixed-origin dossiers when any lore-bearing field has untrusted, unknown, fixture, fallback, or missing origin;
- report exact blocked paths with actionable regeneration or manual-authorship guidance.

Known markers remain useful for migration detection but are not sufficient proof:

- `deterministic_fallback`;
- `deterministic_profile_fixture_v1`;
- `deterministic_world_forge_v1`;
- `quality_enriched=true` when enrichment is code-authored prose;
- `generated_from_legacy=true` for projected user-facing lore;
- `presentation_derived_from_structured_facts=true`;
- `used_llm=false`;
- missing provider or model for content labelled as AI generated.

Exit condition:

No topic, entity, or individual lore string can become release-visible unless its exact content hash resolves to an allowed server-owned artifact or human edit event under the field’s authorship policy.

## Phase 11.5 — Structural repair must remain non-authoring

Status: planned

Priority: P0

Work:

- define approved structural transformations such as Markdown-fence removal, JSON extraction, schema-key normalization, ID normalization, collection reordering, singleton-to-list conversion, and reference correction through an approved alias map;
- record every transformation in the generation artifact;
- extract prose-bearing string leaves before and after structural repair;
- prove that structural repair did not add, complete, summarize, expand, or semantically alter lore-bearing strings;
- route missing prose, incomplete sentences, absent summaries, and absent descriptions to targeted LLM repair rather than structural repair.

Exit condition:

Every structural transformation is auditable and mechanically proven non-authoring. A structural repair that adds or changes a lore-bearing string fails validation.

## Phase 11.6 — Bounded targeted LLM repair

Status: planned

Priority: P0

Repairable quality failures should normally launch a narrowly scoped LLM regeneration request rather than deterministic padding or immediate human review.

Independent validation gates:

- authorship;
- schema;
- grounding;
- richness;
- repetition and distinctiveness;
- publication readiness.

Required flow:

1. Store the initial candidate without overwriting the previously accepted topic.
2. Run all gates and return structured issues with gate, code, entity ID, exact field path, expected value, actual value, and repairability.
3. Classify each failure as structurally repairable, targeted-LLM repairable, full-regeneration required, human-review required, or fatal/untrusted.
4. Group repairable issues by entity and field.
5. Build a repair request containing validated facts, relevant dependencies, exact failed requirements, `allowed_paths`, and `immutable_paths`.
6. Instruct the model to preserve all established IDs, names, references, relationships, and mechanical values outside the allowed paths.
7. Diff the repaired candidate against its parent and reject changes outside `allowed_paths`.
8. Merge permitted changes into a new immutable candidate with parent lineage.
9. Re-run every validation gate against the complete topic.
10. Permit at most two targeted repair attempts before transitioning to `needs_review` or `failed_generation`.

Failure-specific policy:

- untrusted authorship: discard the affected prose and regenerate presentation fields from validated facts without treating the original text as trusted context;
- structural-only failure: apply proven non-authoring repair;
- missing content: use targeted LLM repair;
- grounding contradiction: provide authoritative facts and repair only contradictory prose;
- richness failure: request missing substance, relationships, consequences, or specificity rather than merely requesting more words;
- repetition failure: provide nearby entities and require distinct roles, histories, motives, pressures, and sensory details;
- broad integrity failure: regenerate the whole topic when failures affect a substantial portion of entities or the topic’s central premise.

State model:

`generating -> validating -> targeted_repair -> validating -> ready_for_review | needs_review | failed_generation`

A candidate becomes `needs_review` when its authorship is trusted and content is usable but automated quality requirements remain unresolved. A candidate becomes `failed_generation` when authorship is missing or untrusted, parsing requires invented content, repairs make uncontrolled changes, contradictions are severe, or retry limits are exhausted without a safely usable result.

Exit condition:

Repairable failures produce bounded, path-restricted, lineage-preserving LLM repairs. No deterministic filler is introduced, no accepted topic is invisibly mutated, and out-of-scope model changes are rejected.

## Phase 11.7 — Separate canon facts from authored presentation

Status: planned

Priority: P1

Work:

- make the canon layer store machine-readable `subject`, `predicate`, `object`, references, authority, and source fields without synthesizing narrative `content` or `expanded_description`;
- permit deterministic fact-table rendering of structured values;
- store optional narrative fact explanations separately in the presentation layer with trusted authorship origin;
- prevent canon lookup or read-time adapters from silently promoting compiled strings into lore;
- keep structured mechanical facts stable while allowing their authored explanation to regenerate independently.

Exit condition:

Machine facts remain deterministic and authoritative, while every narrative explanation is separately authored, separately versioned, and separately attributable.

## Phase 11.8 — Data audit and targeted regeneration

Status: planned

Priority: P1

Work:

- scan current draft worlds, revisions, releases, topics, entities, dossiers, facts, and origin records;
- classify each entity as `verified_authored`, `mixed_origin`, `deterministic_lore`, `legacy_unknown`, or `missing_lore`;
- distinguish immutable historical records from current draft content;
- mark affected current drafts as `needs_review` or stale;
- queue mixed, deterministic, unknown, and missing lore for targeted regeneration through World Forge;
- keep the last verified authored version visible when available; otherwise show a generation-required state instead of generic filler;
- prevent launch certification for a new release containing blocked lore;
- produce an audit report with world, topic, entity, exact field path, source classification, artifact status, and remediation status.

Exit condition:

All current publishable drafts pass field-level authorship validation, while historical immutable releases remain auditable and unchanged.

## Phase 11.9 — Final deletion and compatibility cleanup

Status: planned

Priority: P1

Work:

- remove deprecated route handlers after the `410 Gone` compatibility window;
- remove unused service methods, imports, creator modules, merge utilities, request/response contracts, tests, fixtures, and documentation;
- remove duplicated route aliases such as both `generate_world` and `generate-world`;
- verify application startup no longer imports or registers the retired generator;
- update architecture documentation to state that World Forge is the sole production world-generation path;
- retain deterministic test generators only through explicit test injection.

Exit condition:

The legacy endpoints return `404` because they no longer exist, no production module imports the legacy generator or merge path, and all supported generation operations are covered by durable World Forge APIs and trusted authorship validation.

## Phase 11.10 — Generation economics and on-demand richness

Status: planned

Priority: P2

Work:

- preserve full dossiers for featured entities;
- use medium dossiers for supporting entities;
- use rich summaries with on-demand dossier expansion for minor entities;
- generate entity dossiers as independently versioned jobs where practical;
- regenerate only stale or dependency-affected entities;
- track provider cost, token usage, repair attempts, and accepted-output yield per entity tier.

Exit condition:

Rich lore remains available without requiring oversized one-shot topic responses or unnecessary regeneration of unaffected entities.

## Required tests

### Legacy route and production-boundary tests

- current web generation UI never calls `/api/rpg/adventure/*` generation endpoints;
- each deprecated endpoint returns `410 Gone` during the compatibility phase;
- final route registration contains none of the retired paths;
- provider failure cannot create ready or publishable lore;
- production construction without an explicit approved generator fails immediately;
- deterministic generators cannot be selected outside explicit test mode;
- published scenario launch continues to use immutable World Releases without invoking generation.

### Trusted origin tests

- forged provenance: a client submits `used_llm=true` without a valid server artifact and acceptance fails;
- round trip: every published lore string resolves to an exact generation artifact or human edit event and source JSON pointer;
- hash verification: modified content cannot reuse the origin record of a different string;
- origin relabelling: manual acceptance cannot change authorship class;
- external package: arbitrary client packages not issued by the current server-side run are rejected;
- production fixture: any deterministic, test, fixture, or offline artifact is rejected for publishable lore regardless of its supplied flags.

### Field-policy and mixed-origin tests

- one deterministic paragraph inside an otherwise LLM-authored dossier blocks publication and reports its exact path;
- deterministic fact-table formatting is allowed while deterministic dossier prose is rejected;
- manual edits retain human provenance and are never relabelled as AI generated;
- projected legacy entities remain visibly incomplete and cannot acquire a complete dossier status;
- machine-structured facts can publish without an LLM explanation when the schema permits them.

### Repair and validation tests

- structural repair may rearrange fields but may not add or alter prose-bearing string leaves;
- targeted repair may modify only declared `allowed_paths`;
- out-of-scope changes such as renaming an entity or altering another entity cause repair rejection;
- repaired candidates preserve parent lineage, artifact references, issue history, and cost metadata;
- targeted repair reruns authorship, schema, grounding, richness, and repetition gates across the full topic;
- retry budgets stop after the configured maximum and produce `needs_review` or `failed_generation` correctly;
- entity and dossier regeneration preserve canonical IDs, references, structured authority, and mechanical facts;
- retry and continuation preserve completed durable topics and never invoke the legacy generator.

## Release invariants

- World Forge is the only production world-generation pipeline.
- No legacy Adventure Builder generation endpoint remains callable after final deletion.
- No provider failure is converted into deterministic user-facing lore.
- No generated package supplied by a client can bypass durable generation and publication validation.
- No candidate-supplied provenance field is treated as proof without a server-owned artifact.
- Deterministic code may create IDs, hashes, schemas, mechanical values, indexes, validation findings, and structured rendering, but not lore prose.
- Every displayed lore-bearing string has a field-level origin that resolves to an approved LLM artifact or explicit human authorship event.
- Structural repair is non-authoring and mechanically proven not to add or alter lore prose.
- Weak but trusted LLM output is repaired through bounded targeted regeneration, never deterministic padding.
- Existing immutable releases and campaign bindings are never silently rewritten during migration.

## Roadmap completion criteria

This roadmap item is complete when:

- the legacy generated-package API and implementation are deleted;
- all current callers use durable World Forge operations;
- production generators require explicit approved provider injection;
- server-owned artifacts and field-level origin records establish trusted authorship;
- publication recursively enforces schema-specific authorship policy;
- targeted LLM repair replaces deterministic enrichment and respects strict field boundaries;
- deterministic facts remain separate from authored presentation;
- affected drafts are audited or regenerated;
- tests prove there is no remaining production route from provider failure, forged provenance, deterministic fixtures, legacy projection, or structural repair to untrusted player-facing lore.