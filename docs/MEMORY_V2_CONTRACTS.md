# Omnix Memory v2 Contract Specification

Status: **Contract baseline for architecture-frozen Memory v2**  
Architecture: `docs/MEMORY_V2_ARCHITECTURE.md`

This document defines the semantic meaning of the initial `app.assistant_memory_v2`
contracts. It is intentionally implementation-neutral. Persistence schemas, VoiceMem
ports, vector stores, graph traversal engines, and live-runtime integration must conform
to these contracts rather than redefine them.

## Contract principles

1. Evidence and derived belief are different data classes.
2. Ownership and visibility are different dimensions.
3. Retrieval is read-only.
4. Every derived belief is evidence-addressable.
5. All durable transformation windows are attributable and replayable.
6. Search indexes are projections, not authorities.
7. Cross-space access is authorization, not copied memory.
8. Authority cutover is an epoch transition gated by explicit readiness.

## `MemorySpaceKey`

```text
principal_id
owner_type = system | character
owner_id
```

`MemorySpaceKey` identifies one persistent memory owner/brain. Workspace, project, and
session identifiers are intentionally absent.

Rules:

- System memory uses owner ID `system-assistant`.
- Character memory may not use `system-assistant`.
- The same character ID under different principals is a different memory space.
- A character has one graph per principal, not one graph per project/workspace/session.

## `VisibilityScope`

```text
kind = global | workspace | project | session
scope_id
```

Visibility scope is evaluated inside a `MemorySpaceKey`. It determines whether a graph
assertion/episode is visible to a particular interaction; it does not change ownership.

## `ObservationProvenance`

Provenance records where evidence came from independently of its natural-language
payload.

Core fields:

```text
source_type
source_id
trust_level
session_id?
turn_id?
message_id?
provider_id?
model_id?
```

The source type is validated against observation event type. For example, a `user_said`
event cannot claim assistant provenance, and an `assistant_generated` event cannot claim
user provenance.

## `Observation`

An observation is an append-only evidence event.

```text
observation_id
authority_sequence
idempotency_key
space
visibility_scope
event_type
occurred_at
recorded_at
payload
provenance
correlation_id?
schema_version
content_digest
```

### Required semantics

- `authority_sequence` is the monotonic watermark used for catch-up/cutover.
- `idempotency_key` prevents retry from creating duplicate durable evidence.
- `content_digest` is required so persisted evidence can be integrity-checked.
- `schema_version` makes replay across contract evolution explicit.
- assistant output observations require `correlation_id` so generated, delivered, and
  experienced forms of one output can be related.

### Event types

```text
user_said
assistant_generated
assistant_delivered
assistant_experienced
external_observed
system_event
imported_legacy_memory
acoustic_observation
```

`assistant_generated` is never a substitute for `assistant_experienced`.

Example:

```text
correlation_id = output:42

assistant_generated
    "Sentence one. Sentence two. Sentence three."

assistant_experienced
    "Sentence one. Sen"
    rendered_samples = ...
```

If playback was interrupted, future memory formation uses the experienced boundary when
reasoning about shared conversation history.

## `ObservationDisposition`

Observations are immutable to inference/consolidation, but privacy/governance actions can
revoke or purge evidence.

```text
observation_id
state = active | revoked | purged
authority_sequence
changed_at
reason?
actor_id
```

A disposition is separate from the original observation. Purging evidence requires
dependent invalidation/recomputation of graph assertions that depend exclusively on that
evidence.

## `GraphEntityRef` and `GraphValue`

Graph assertions use structured subject/object terms rather than only natural-language
records.

```text
GraphEntityRef
    entity_id
    entity_type

GraphValue
    kind = entity | literal
    entity? / literal?
```

Exactly one object representation is valid.

## `GraphAssertion`

`GraphAssertion` is the fundamental derived belief contract.

```text
assertion_id
space
visibility_scopes[]
subject
predicate
object
domain
assertion_type
confidence
valid_from?
valid_until?
evidence_observation_ids[]
evidence_assertion_ids[]
derivation_version
supersedes[]
contradicted_by[]
status
revision
```

Rules:

- Every assertion has evidence: observation IDs, assertion IDs, or both.
- `valid_until` cannot precede `valid_from`.
- Supersession changes current belief state without deleting historical evidence.
- `derivation_version` identifies the consolidator/rule/model family that created the
  conclusion.

Domains are semantic memory domains, not visibility scopes. Project-specific knowledge,
for example, is typically a fact/goal/open-loop with project visibility rather than a
special physical project brain.

## `Episode`

An episode groups one or more authoritative observations into a derived experience.

```text
episode_id
space
visibility_scopes[]
title
summary
started_at
ended_at?
participant_entity_ids[]
observation_ids[]
generated_assertion_ids[]
importance
derivation_version
revision
```

An episode must be backed by at least one observation.

## `RelationshipMetric` and `RelationshipState`

Numeric relationship metrics are internal latent state. The prompt-facing representation
is a separate interpretation.

```text
RelationshipMetric
    name
    value 0..1
    confidence 0..1
    evidence_observation_ids[]

RelationshipState
    relationship_id
    space
    subject
    counterpart
    metrics[]
    prompt_interpretation
    evidence_observation_ids[]
    derivation_version
    status
    revision
```

The LLM should normally see a grounded interpretation such as “highly familiar; playful
technical discussion works well,” not arbitrary precision such as `trust=.82`.

## `AffectObservation`

Affect is timestamped evidence, not timeless current state.

```text
affect_id
space
source_observation_id
source = explicit | semantic | acoustic | fused
observed_at
valence?
arousal?
emotion_distribution{}
confidence
model_version
```

At least one affect signal is required. Historical affect must retain its observation
time and source when retrieved.

## `MemoryGrant`

Cross-space memory access is federated read authorization.

```text
grant_id
source_space
target_space
access = read
allowed_domains[]
max_sensitivity
scope_constraints[]
created_by
created_at
revoked_at?
```

Rules:

- Grants are read-only in v2 baseline.
- Source and target must be distinct spaces.
- Source and target must belong to the same principal.
- Grants do not copy graph assertions between spaces.
- Grants are policy objects and are never created implicitly by consolidation/LLM output.

Cross-principal sharing requires a future, separate authorization design; it is not
accidentally enabled by the base grant contract.

## `RetrievalQuery`

Retrieval has no mutation capability.

```text
query_id
space
visible_scopes[]
text
authority = partial | final | system
as_of
top_k
token_budget
deadline_ms
domains[]
grant_ids[]
```

A partial-STT query and a final-turn query use the same read contract. The difference is
query authority/quality, not write permission.

The baseline deadline default is 50 ms to preserve existing Omnix temporal-retrieval
latency discipline. Implementations may return bounded/degraded results rather than
turning memory retrieval into unbounded response latency.

## `RetrievalScore`

Retrieval retains independent scoring components:

```text
semantic
graph
temporal
relationship
episodic
importance
confidence
recency
pinning
stale_penalty
composite
```

`composite` is a ranking output, not an opaque source of truth. Components and reasons
remain inspectable so policy can evolve and regressions can be diagnosed.

## `RetrievalCandidate` / `RetrievalResult`

A retrieval result identifies selected graph/episode/relationship items, evidence,
selection reasons, prompt eligibility, and the data-version state used for the result.

Key result watermarks:

```text
observation_watermark
graph_revision
index_graph_revision
```

This makes stale-index behavior observable rather than silent.

## `ConsolidationReceipt`

Every durable consolidation window emits a receipt.

```text
receipt_id
space
input_observation_from
input_observation_through
consolidator_version
schema_version
provider_id?
model_id?
created_assertion_ids[]
reinforced_assertion_ids[]
superseded_assertion_ids[]
retracted_assertion_ids[]
conflicted_assertion_ids[]
created_episode_ids[]
relationship_update_ids[]
affect_update_ids[]
resulting_graph_revision
idempotency_key
started_at
completed_at
```

Receipts provide replay attribution and permit diagnosis of which consolidator version
produced a bad graph state.

## `MemoryWatermarks`

```text
authoritative_event
observation
consolidation
graph_revision
index_graph_revision
```

These are explicit cutover/catch-up state, not inferred from wall-clock time.

## `CutoverReadiness`

`ready=true` is valid only when:

```text
observation == authoritative_event
consolidation == observation
index_graph_revision == graph_revision
graph_validation_passed
shadow_quality_passed
indexes_caught_up
```

The contract rejects a claimed ready state when any invariant is false.

## `MemoryAuthorityEpoch`

```text
epoch
authority = v1 | v2
activated_at
previous_epoch?
readiness?
activated_by
```

An epoch selecting v2 is invalid without a successful readiness receipt. This is intended
to be persisted/changed transactionally by the migration authority. It is not a casual
feature toggle.

## Contract versioning rules

- Additive optional fields may be introduced within a schema generation when replay
  semantics remain unchanged.
- Changes to ownership, evidence authority, assertion identity, grant authorization, or
  cutover semantics require an explicit architecture/contract revision.
- Persisted observation payloads carry schema versions and digests.
- Consolidation receipts carry consolidator and schema version identities.
- Implementations must not infer missing authority metadata from natural-language text.

## Implementation sequencing after contract approval

The next implementation phases should proceed in this order:

1. observation/event store + dispositions + watermarks;
2. relational graph store + evidence edges + replay validator;
3. deterministic consolidator interface and receipts;
4. episode/relationship/affect derivation;
5. unified retrieval with temporal scorer port;
6. VoiceMem-derived semantic extraction/graph enrichment adapters;
7. partial-STT speculative retrieval integration;
8. v1 shadow ingestion/import and quality comparison;
9. atomic `MemoryAuthorityEpoch` cutover.

No later phase should weaken the authority/evidence contracts to simplify an adapter.
