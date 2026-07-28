# Trusted LLM-Authored World Forge Lore — Implementation Record

Status: implemented on `agent/roadmap-remove-legacy-world-generation-api`  
Roadmap source: `rpg_world_generation_legacy_api_retirement_roadmap.md`

## Production invariant

No user-facing lore string may be stored as ready canon, published in a world revision, certified in a release, or loaded into a campaign unless its exact value resolves to one of:

- an immutable server-owned LLM generation artifact containing provider, model, response hash, parsed authored-string hashes, and transformation lineage;
- a server-owned human authoring or human-edit event; or
- an explicitly machine-structured field whose schema permits non-narrative values.

Topic-level labels such as `source="ai"`, `used_llm=true`, or `provider_authored_presentation=true` are not authorship proof.

## Completed work

### 1. Legacy generation retirement

The Adventure Builder no longer registers the legacy world-package endpoints:

- `generate_world` / `generate-world`
- `regenerate_section`
- `regenerate_entity`
- `apply_generated_package`
- `fill_npc`

The legacy bootstrap generator, parser, and package merger were deleted. Inspection, validation, preview, manually authored setup, simulation, and adventure start remain available.

### 2. Fail-closed provider routing

Durable World Forge runs require a concrete provider and model before job creation. Missing or unresolved configuration raises a route error; it never selects deterministic prose.

Deterministic generation remains available only as an explicit fixture contract. The exemption requires both:

1. a durable route recorded as `deterministic`, `offline`, `reference-safe`, or `test`; and
2. an actual supplied `DeterministicWorldForgeGenerator` found in the server wrapper chain.

The server then emits a signed fixture marker. Production routing cannot create this marker or publish the fixture outside the explicit contract.

### 3. Field-level authorship policy

Profile-driven topic schemas now expose authorship policy metadata:

- `llm_required`
- `authored_required`
- `machine_allowed`
- `structural_only`

IDs, references, schema metadata, validation, hashes, and mechanical values remain deterministic. Names, summaries, dossier prose, documents, story threads, fact explanations, history, motives, pressures, hooks, quests, encounters, and opening prose require authored origins.

### 4. Immutable generation artifacts and origin ledgers

Each provider candidate receives an immutable server-owned generation artifact containing:

- generation run, job, topic, provider, and model;
- generator and prompt versions;
- raw provider response hash or response-set hash;
- exact JSON-pointer and content-hash pairs for authored strings;
- structural recovery transformations;
- attempt and parent artifact lineage.

The origin ledger is recursive and exact. A changed string invalidates its prior origin. Targeted regeneration supports multiple artifacts in one topic: unchanged fields retain their prior artifact, newly generated fields point to the new artifact, and human edits point to a human event while retaining the parent origin.

### 5. Recovery without application-authored lore

Structured recovery may only unwrap containers, normalize aliases, repair authoritative IDs, or request the same model to restructure its own candidate. Deterministic normalization records a mechanical proof that the lore-string multiset did not change.

Generation performs one initial provider attempt plus at most two narrowly scoped LLM repairs. Repair requests include allowed and immutable paths. If no safe repair request can be derived, a structurally usable provider candidate is retained as `needs_review`; application prose is never inserted.

### 6. Machine facts and rich presentation

The production structured-fact compiler emits only canonical machine fields:

- subject
- predicate
- object
- value type
- semantic role
- references
- authority and visibility

It does not synthesize lore sentences or explanations. A compact JSON lookup is attached for runtime and dependency use. Optional `content` or `expanded_description` remains authored prose.

Presentation accepts the trusted machine-fact v2 contract while preserving the original source metadata. Publication validates existing structured facts semantically and idempotently instead of recompiling prose.

### 7. Dossier generation

Missing dossiers project to a generation-required shell with no fallback paragraphs. Live provider output must satisfy the dossier schema and quality requirements or remain blocked/reviewable.

Deterministic dossier enrichment and deterministic fact prose exist only in explicit fixture modules, carry blocked fixture provenance, and cannot pass production publication validation.

### 8. Persistence and editorial lineage

The trusted topic repository is the common persistence boundary:

- ready AI topics require valid authored origins and artifacts;
- manual topic/entity/dossier edits receive human event origins;
- targeted entity and dossier regeneration stores changed paths as AI-authored, not manual;
- restore preserves the historical content ledger exactly;
- stale dependency propagation remains deterministic and separate from lore authorship.

### 9. Publication, revisions, releases, and launch

Publication recursively validates every lore string and reports exact blocked JSON paths and reason codes. A ready flag or AI source label cannot bypass it.

Direct immutable revision publishing is allowed only for manual worlds in production. Provider-backed, hybrid, and imported/generated worlds must use the guarded generation compiler. Manual and imported revision authorship is stored in revision provenance so canon remains byte-for-byte stable.

Release creation, scenario compatibility, campaign binding, release-definition loading, and published-resource loading all require a trusted revision/release authorship chain.

### 10. Existing-world audit and remediation

World Library now exposes:

- `GET /api/rpg/worlds/{world_id}/authorship-audit`
- `POST /api/rpg/worlds/{world_id}/authorship-audit/remediate`

The audit classifies current topics and entities as:

- `verified_authored`
- `mixed_origin`
- `deterministic_lore`
- `legacy_unknown`
- `missing_lore`

Remediation marks only blocked current drafts stale and can queue forced topic regeneration. Immutable revisions and releases are counted and never mutated.

## Regression coverage

Coverage includes:

- forged provenance rejection;
- exact string/hash/artifact round trips;
- missing provider/model failures;
- provider failure without deterministic fallback;
- machine fact classification;
- no generated fact prose in production;
- generation-required dossier shells;
- deterministic marker rejection;
- structural repair no-new-prose proof;
- human edit lineage;
- multi-artifact targeted regeneration;
- uncovered application text rejection;
- revision and release trust chains;
- legacy route retirement;
- deterministic fixture isolation;
- audit classification and remediation boundaries.

## Operational notes

- Existing unknown or deterministic drafts are not silently grandfathered. They remain visible for audit and review but cannot publish until regenerated or explicitly human-authored.
- Existing immutable history is preserved. New launch and release operations validate the stored authorship chain.
- Structured facts remain usable by simulation and retrieval without requiring narrative text.
- Deterministic fixtures remain useful for unit, integration, endurance, and architecture tests without weakening production policy.
