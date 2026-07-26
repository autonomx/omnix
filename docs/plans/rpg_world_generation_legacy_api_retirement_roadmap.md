# RPG World Generation Legacy API Retirement Roadmap

Status: planned

Parent roadmap: `docs/plans/rpg_world_scenario_map_roadmap.md`

## Objective

Retire the obsolete Adventure Builder world-generation workflow and make the durable World Library and World Forge pipeline the only production path for generated world lore. The migration must preserve unrelated Adventure Builder setup, validation, preview, simulation, and launch functionality while removing any production path that can return deterministic fallback prose as generated lore.

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
| Apply generated package | Persist validated topic results through the durable run and publish the reviewed run |
| Retry after provider failure | Retry failed topics or continue the durable run |
| Inspect generation state | Read the durable generation run and topic lineage |

## Phase 11.1 — Caller inventory and deprecation guard

Status: planned

Work:

- search backend, web UI, tests, scripts, and documentation for all legacy endpoint and service references;
- identify any external or manual callers that are not visible in repository code;
- add structured deprecation logging to every legacy generation route;
- change legacy routes to return `410 Gone` with the supported World Forge replacement endpoints;
- ensure no route silently redirects to a different semantic operation;
- add telemetry or test assertions proving current UI generation uses only World Library and World Authoring clients.

Exit condition:

Every known caller is migrated or explicitly retired, and any unknown caller receives an actionable failure instead of deterministic generated lore.

## Phase 11.2 — Remove deterministic production fallback generation

Status: planned

Work:

- delete or isolate the legacy deterministic world proposal generator from production dependency graphs;
- remove deterministic NPC biography, personality, history, rumor, and lore enrichment fallbacks;
- fail closed when an LLM provider is unavailable or generation fails;
- retain deterministic generators only behind explicit test-mode boundaries where their output cannot be published or displayed as production lore;
- reject generated packages whose provenance records `used_llm=false`, a deterministic generator, or fallback generation.

Exit condition:

A provider failure produces a visible failed or retryable generation state and never produces a ready world, accepted entity, or user-visible fallback story text.

## Phase 11.3 — Remove generated-package application path

Status: planned

Work:

- remove `apply_generated_package` and its merge service;
- prevent clients from submitting an arbitrary generated package and having it relabelled as authoritative generated content;
- require generated content to enter storage through a durable generation run, schema validation, provenance validation, review, and publication;
- preserve manual editing as an explicitly manual source with separate provenance.

Exit condition:

All AI-generated world content has a durable run, topic lineage, provider/model provenance, validation result, and review or publication event.

## Phase 11.4 — Publication provenance enforcement

Status: planned

Work:

- add one shared `validate_llm_authored_topic` boundary used by generation completion, acceptance, topic saving, release creation, and publication;
- require approved LLM generator identity, provider, model, successful response metadata, and provider-authored presentation markers for user-facing lore;
- block publication when provenance includes deterministic fallback, legacy projection, deterministic dossier enrichment, structured-fact presentation synthesis, or `used_llm=false`;
- report blocked topic and entity IDs with actionable regeneration guidance;
- ensure manual prose remains publishable only when explicitly marked as manually authored rather than AI generated.

Minimum blocked markers:

- `deterministic_fallback`;
- `deterministic_profile_fixture_v1`;
- `deterministic_world_forge_v1`;
- `quality_enriched=true` when enrichment is code-authored prose;
- `generated_from_legacy=true` for projected user-facing lore;
- `presentation_derived_from_structured_facts=true`;
- `used_llm=false`;
- missing provider or model for content labelled as AI generated.

Exit condition:

No topic or entity can become release-visible AI lore unless its displayed prose traces to a successful approved LLM response.

## Phase 11.5 — Data audit and regeneration

Status: planned

Work:

- scan current draft worlds, revisions, releases, topics, entities, dossiers, and facts for blocked provenance markers;
- distinguish immutable historical records from current draft content;
- mark affected current drafts as `needs_review` or stale;
- regenerate affected lore through World Forge without mutating immutable historical releases;
- prevent launch certification for a new release containing blocked generated prose;
- produce an audit report with world, topic, entity, source marker, and remediation status.

Exit condition:

All current publishable drafts pass the LLM-authored provenance gate, while historical immutable releases remain auditable and unchanged.

## Phase 11.6 — Final deletion and compatibility cleanup

Status: planned

Work:

- remove the deprecated route handlers after the `410 Gone` compatibility window;
- remove unused service methods, imports, creator modules, merge utilities, request/response contracts, tests, fixtures, and documentation;
- remove duplicated route aliases such as both `generate_world` and `generate-world`;
- verify application startup no longer imports or registers the retired generator;
- update architecture documentation to state that World Forge is the sole production world-generation path.

Exit condition:

The legacy endpoints return `404` because they no longer exist, no production module imports the legacy generator or merge path, and all supported generation operations are covered by durable World Forge APIs.

## Required tests

- current web generation UI never calls `/api/rpg/adventure/*` generation endpoints;
- each deprecated endpoint returns `410 Gone` during the compatibility phase;
- final route registration contains none of the retired paths;
- provider failure cannot create ready or publishable lore;
- deterministic generators cannot be selected outside explicit test mode;
- deterministic or legacy provenance cannot pass acceptance, release, or publication guards;
- entity and dossier regeneration preserve canonical IDs and structured authority while replacing only LLM-authored presentation;
- manual edits retain manual provenance and are never relabelled as AI generated;
- retry and continuation preserve completed durable topics and do not invoke the legacy generator;
- published scenario launch continues to use immutable World Releases without invoking generation.

## Release invariants

- World Forge is the only production world-generation pipeline.
- No legacy Adventure Builder generation endpoint remains callable after final deletion.
- No provider failure is converted into deterministic user-facing lore.
- No generated package supplied by a client can bypass durable generation and publication validation.
- Deterministic code may create IDs, hashes, schemas, mechanical values, indexes, and validation findings, but not user-facing lore prose labelled as generated.
- Every displayed AI-authored lore field has provider and model provenance traceable to a successful generation response.
- Existing immutable releases and campaign bindings are never silently rewritten during migration.

## Roadmap completion criteria

This roadmap item is complete when the legacy generated-package API and implementation are deleted, all current callers use durable World Forge operations, publication fails closed on non-LLM prose, affected drafts are audited or regenerated, and tests prove there is no remaining production route from provider failure to deterministic user-facing lore.
