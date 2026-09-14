# Omnix Memory v2 Architecture Revision 1 — Correctness Convergence

Status: **FROZEN ADDENDUM FOR PR #1529 CONVERGENCE**  
Date: 2026-09-14  
Applies to: `docs/MEMORY_V2_ARCHITECTURE.md` and `docs/MEMORY_V2_CONTRACTS.md`

This addendum does not replace the Memory v2 authority hierarchy. It tightens lifecycle,
governance, replay, federation, and production-processing semantics discovered while
integrating Phases 1–16.

## 1. Canonical authority chain

The long-term authority chain is:

```text
AuthoritativeEventSequence
          |
          v
ObservationWatermark + GovernanceRevision
          |
          v
ConsolidationDecisionSet
          |
          v
DerivedMemoryRevision
          |
          v
SearchProjectionRevision
          |
          v
FederationRevisionDigest
          |
          v
RetrievalResult
```

The Observation Log remains the ultimate evidence authority. `DerivedMemoryRevision`
replaces the ambiguous interpretation of a graph-only consolidation watermark as the
canonical revision of all derived memory.

A derived revision covers one coherent state transition across:

- graph assertions;
- episodes;
- relationship state;
- affect state;
- derived policy envelopes;
- the consolidation receipt.

## 2. Inference is outside authority transactions

Semantic/model inference MUST NOT execute while authority, observation, graph, derived,
or governance rows are locked.

The required protocol is optimistic:

```text
read observation window
read governance revision
read previous derived revision
        |
        v
semantic / model processing OUTSIDE transaction
        |
        v
BEGIN
lock canonical state
verify observation watermark unchanged
verify governance revision unchanged
verify previous derived revision unchanged
validate the proposed derived plan and policy envelopes
persist the complete derived revision atomically
COMMIT
```

If any source revision changed, the plan is stale and MUST be discarded/recomputed.

## 3. Derived policy envelope

Every prompt-eligible derived item has a deterministic policy envelope independent of
model output:

```text
DerivedPolicyEnvelope
    sensitivity
    effective_visibility[]
    trust_class
    source_observation_ids[]
    source_assertion_ids[]
    source_governance_revision
    policy_version
    policy_digest
```

Policy propagation is monotonic:

1. A derived item may never be less sensitive than its evidence.
2. A derived item may never be visible to a context that cannot see every backing item.
3. A derived item may never be assigned a stronger trust class than its evidence and
   derivation path permit.
4. Model/provider output cannot choose or weaken this envelope.

`effective_visibility` is conjunctive. A retrieval context must satisfy every scope in
the envelope. This safely represents mixed global/project/session evidence without
inventing project ancestry inside `MemorySpaceKey`.

## 4. Governance revision

Each `MemorySpaceKey` has a monotonic `governance_revision`. Any revoke, purge, restore,
or other evidence-governance mutation increments it.

A semantic plan computed against governance revision N is stale if revision N+1 exists,
even when the observation watermark did not change.

Purging evidence MUST invalidate dependent derived state and redact any replay artifact
that contains semantic content derived from the purged evidence. Content digests and
minimal audit tombstones may remain, but purged semantic payloads may not survive as an
undeletable replay copy.

## 5. Exact replay vs re-derivation audit

Nondeterministic semantic extraction makes two operations distinct.

### Exact replay

Recovery uses the authoritative observations plus the committed, content-addressed
`ConsolidationDecisionSet`. It MUST reproduce the committed derived revision without
calling the original model again.

### Re-derivation audit

Evaluation reruns the current extraction/consolidation implementation from authoritative
evidence and compares the candidate result to the committed revision. It may differ and
must never silently replace exact replay semantics.

A decision set records at minimum:

```text
source observation range
previous derived revision
source governance revision
normalized semantic proposals
deterministic policy decisions
provider/model/consolidator/schema identity
decision digest
```

## 6. Federated revision provenance

A federated retrieval result MUST identify the versions of every memory space and grant
that contributed candidates.

```text
RetrievalSourceRevision
    source_space
    observation_watermark
    governance_revision
    derived_revision
    index_revision
    grant_revision
```

The ordered source revisions are hashed into a `federation_revision_digest`.
Speculative cache promotion must validate that digest (or equivalent fresh source
revisions), not merely the local graph revision.

`MemoryGrant.max_sensitivity` is a hard authorization boundary evaluated against the
derived policy envelope.

## 7. Search projection is useful state, not ceremonial state

If search projection freshness remains a cutover/production invariant, normal retrieval
must use the projection for candidate generation when it is fresh. Canonical derived
state is then batch-hydrated and policy/evidence/temporal rules are applied before prompt
selection.

When the index is absent or stale, retrieval may use a bounded deterministic fallback,
but must expose that degraded path in diagnostics.

## 8. Production convergence loop

Post-cutover operation is a durable convergence pipeline:

```text
append authoritative observation
        |
        +-- COMMIT evidence
        |
        +-- coalesce derive-through-watermark job
                    |
                    v
             worker computes plan
                    |
                    v
        optimistic atomic derived commit
                    |
                    +-- coalesce search-projection job
```

Workers require durable retries, bounded attempts/backoff, poison diagnostics, crash
recovery, and idempotent/coalescing work claims.

First-class health metrics include:

- observation -> derived lag;
- governance -> derived lag;
- derived -> search projection lag;
- failed/retried derivations;
- stale-plan conflicts;
- replay divergence;
- projection rebuild failures.

## 9. Cutover readiness revision

A production-ready space must satisfy all previous gates plus:

```text
authoritative_event_watermark == observation_watermark
derived.source_observation_watermark == observation_watermark
derived.source_governance_revision == governance_revision
search.index_derived_revision == derived_revision
exact_replay_validation == PASS
shadow_retrieval_quality == PASS
```

Graph revision remains useful internal versioning but is no longer sufficient to claim
that all derived memory domains are caught up.

## 10. Public roadmap

Phases 0–16 remain implementation history and acceptance evidence. The conceptual roadmap
is now seven milestones:

A. Evidence Authority  
B. Atomic Derived Memory  
C. Retrieval Intelligence  
D. Authorization + Live Voice  
E. Evaluation + Migration  
F. Authority Cutover  
G. Production Operations

This addendum is the required architecture revision for the convergence work. It narrows
and strengthens the original frozen architecture; it does not weaken Observation Log
authority, ownership isolation, grant authorization, or transactional cutover semantics.
