# Omnix Memory v2 Architecture — Frozen Contract Baseline

Status: **ARCHITECTURE FROZEN FOR CONTRACT DESIGN**  
Date: 2026-09-13  
Implementation lineage: **VoiceMem-derived, Omnix-native**

This document freezes the architectural authority model for Omnix Memory v2 before
implementation begins. Memory v2 is inspired by VoiceMem's streaming retrieval,
semantic fact graph, evidence-backed relationship/personality memory, compact Top-K
context, and audio-native affect. It is not a downstream fork contract and does not
adopt upstream VoiceMem APIs as permanent Omnix APIs.

The existing `app.assistant_memory` subsystem remains the runtime authority until a
later, explicit cutover epoch. The `app.assistant_memory_v2` package introduced with
this document contains contracts only.

## 1. Authority model

Memory v2 has three distinct authority layers:

```text
Authoritative conversation/event feed
                 |
                 v
      Immutable Observation Log
       authoritative evidence
                 |
          replay/consolidate
                 v
        Derived Memory Graph
   authoritative current belief state
                 |
          rebuild/project
                 v
       Retrieval/Search Indexes
     disposable acceleration state
```

### Invariants

1. **The Observation Log is the ultimate evidence source of truth.**
2. **The Memory Graph is the authoritative current belief state.**
3. **Vector/search indexes are never authoritative.** They are rebuildable projections.
4. The graph must be rebuildable from observations.
5. Indexes must be rebuildable from the graph.
6. Full replay of observations must be sufficient to rebuild graph + indexes.
7. A consolidator failure may corrupt derived state but must not rewrite evidence history.
8. Observation mutation is forbidden to inference/consolidation logic.
9. Explicit governance/privacy operations may revoke or purge observations and must
   invalidate/recompute dependent derived state.

“Immutable” therefore means append-only and immutable to inference, not exempt from
user-authorized privacy deletion.

## 2. One canonical subsystem

The target end state is **one Memory v2 authority**, not permanent synchronization
between legacy Omnix memory and VoiceMem.

```text
Legacy v1 memory                 Memory v2
----------------                 ---------
temporary authority   ---->      canonical authority
read/write                         observation log
                                   memory graph
                                   unified retrieval
```

There is no permanent dual-write design. Shadow ingestion is allowed only as a
migration mechanism before the authority epoch changes.

## 3. Memory ownership and visibility

A character has one persistent brain per principal/profile. Workspace, project, and
session are visibility constraints inside that brain, not separate physical brains.

```text
MemorySpaceKey
    principal_id
    owner_type      # system | character
    owner_id        # system-assistant | sofia | maya | ...

VisibilityScope
    global
    workspace
    project
    session
```

Example:

```text
profile:alice / character:sofia
    global memories
    workspace-visible memories
    project-visible memories
    session-local memories

profile:alice / character:maya
    separate graph

profile:bob / character:sofia
    separate graph
```

This preserves current Omnix's distinction between owner identity and visibility scope
and prevents workspace/project fragmentation of a character's lifetime memory.

## 4. Observation vs memory

An observation records **what happened**. Memory records **what the system currently
believes or retains because of what happened**.

Example:

```text
obs-101
    user said: "Skyrim is my favorite game."
    occurred_at: Jan 12

obs-244
    user said: "Cyberpunk is probably my favorite now."
    occurred_at: Mar 8

Derived graph
    User --favorite_game--> Skyrim
        valid Jan 12 -> Mar 8
        evidence [obs-101]
        status superseded

    User --favorite_game--> Cyberpunk
        valid Mar 8 ->
        confidence .88
        evidence [obs-244]
        supersedes previous assertion
```

No historical evidence is deleted merely because the current belief changes.

## 5. Evidence-addressable graph assertions

Every graph assertion must identify evidence. Bare LLM conclusions are invalid.

```text
GraphAssertion
    assertion_id
    subject
    predicate
    object
    confidence
    valid_from
    valid_until
    evidence_observation_ids[]
    evidence_assertion_ids[]
    derivation_version
    supersedes[]
    contradicted_by[]
    status
```

This applies to facts, preferences, temporal state, traits, and relationship conclusions.
A future consolidator must be able to re-evaluate a claim from its evidence.

## 6. Character profile is not learned memory

```text
CharacterProfile
    core identity
    personality prompt
    speaking style
    governed voice
    identity policy

Character Memory v2
    experiences
    beliefs about the user
    preferences learned from interaction
    relationship state
    episodic memories
    affect history
    adaptations
```

Long-term interaction can evolve relationship/adaptation state without silently
rewriting the character's governed identity.

## 7. Relationship state

Relationship metrics such as familiarity, rapport, trust, and playfulness are internal
latent state. Prompt-facing context should normally use an interpretation with evidence,
not raw pseudo-precise numbers.

```text
internal
    familiarity=.87
    rapport=.81

prompt-facing
    "The relationship is highly familiar; the user responds well to playful,
     technical discussion."
```

Metrics and interpretations must remain evidence-addressable.

## 8. Affect

Affect is an observation with source, time, and confidence — not an unqualified timeless
fact about the user's current state.

```text
AffectObservation
    source = acoustic | semantic | explicit | fused
    observed_at
    valence/arousal/distribution
    confidence
    source_observation_id
```

Historical affect must never be labeled as current without current-turn evidence.
This directly avoids stale-current-emotion behavior.

## 9. Experienced conversation semantics

Memory v2 distinguishes generated output from what was actually delivered/experienced.

```text
user_said
assistant_generated
assistant_delivered
assistant_experienced
```

If a voice response contains three generated sentences but playback is interrupted
halfway through sentence one, future memory must not behave as though the user heard
all three. The live voice runtime may produce the playback boundary, but Memory v2 owns
the semantic distinction.

## 10. Cross-space sharing uses grants, not copies

System Assistant memory is not copied into a character graph. Shared reads are federated
through explicit grants.

```text
MemoryGrant
    source_space
    target_space
    access = read
    allowed_domains[]
    max_sensitivity
    scope_constraints[]
```

Grants are authorization policy, not learned graph state, and consolidators/LLMs have no
authority to create or modify them implicitly.

## 11. Unified retrieval

VoiceMem-style semantic retrieval is combined with deterministic Omnix retrieval signals.
Cosine similarity does not replace temporal reasoning.

Candidate scoring retains inspectable components:

```text
semantic
+ graph
+ temporal
+ relationship
+ episodic
+ importance
+ confidence
+ recency
+ pinning
- stale/superseded penalty
```

The ranking policy may evolve. Individual score components and selection reasons remain
observable so a single opaque scalar does not become an unreviewable authority.

Current v1 temporal behavior worth porting includes timezone-aware routines, routine
exceptions, active windows, overdue/open loops, goals, validity intervals,
confidence/pinning, preload caching, and bounded retrieval deadlines.

## 12. Speculation authority

Partial STT may retrieve memory but can never mutate it.

```text
partial STT
    -> speculative retrieval
    -> READ ONLY

accepted authoritative final turn
    -> append Observation
    -> consolidate
    -> mutate derived graph
```

The retrieval contract intentionally has no mutation capability.

## 13. Consolidation receipts

Every consolidation window emits an attributable, replayable receipt containing:

- input observation watermark range;
- consolidator/schema/model/provider version identity;
- created/reinforced/superseded/retracted/conflicted assertions;
- episode creation;
- relationship/affect updates;
- resulting graph revision;
- idempotency key;
- timing.

This makes memory formation reviewable and replay-safe.

## 14. Watermarks and atomic authority cutover

Every authoritative event entering shadow v2 ingestion receives a monotonic authority
sequence and idempotency identity.

Before v2 authority is activated, all of the following must hold:

```text
observation_watermark == authoritative_event_watermark
consolidation_watermark == observation_watermark
index_graph_revision == graph_revision
graph_validation == PASS
shadow_retrieval_quality == PASS
indexes_caught_up == true
```

Only then can a transactional `MemoryAuthorityEpoch` move from v1 to v2. V1 becomes
read-only immediately. The epoch is an authority record, not a casual runtime feature
flag.

## 15. Initial storage strategy

Do not require a dedicated graph database for the first implementation. Use Omnix's
supported authoritative structured-data runtime and model the graph relationally first:

```text
observations
observation_dispositions
graph_nodes
graph_assertions
assertion_evidence
episodes
episode_members
relationship_state
affect_observations
memory_grants
consolidation_receipts
memory_authority_epochs
```

Vector/search storage is a rebuildable projection. If future graph traversal patterns
justify a graph database, it can be introduced without changing the evidence authority
model.

## 16. Contract-first implementation boundary

The frozen first contract surface is:

- `Observation`
- `ObservationProvenance`
- `ObservationDisposition`
- `MemorySpaceKey`
- `VisibilityScope`
- `GraphAssertion`
- `Episode`
- `RelationshipState`
- `AffectObservation`
- `MemoryGrant`
- `RetrievalQuery`
- `RetrievalCandidate`
- `RetrievalResult`
- `ConsolidationReceipt`
- `MemoryAuthorityEpoch`

These contracts live in `app.assistant_memory_v2` and must remain implementation-neutral.
VoiceMem capabilities are ported **into** these contracts later; upstream VoiceMem data
models and public APIs do not define Omnix's permanent interfaces.

## 17. Explicitly out of scope for the contract phase

This phase does **not**:

- enable Memory v2 at runtime;
- change current v1 read/write authority;
- add VoiceMem as a dependency;
- copy upstream VoiceMem implementation;
- create vector/graph storage;
- dual-write legacy memory in production;
- modify live voice retrieval;
- perform migration or cutover.

Those are subsequent implementation phases gated by these contracts and their invariant
tests.

## 18. Frozen architectural decision

The selected long-term design is:

```text
Omnix Memory v2
    = VoiceMem architectural ideas
    + Omnix authority/provenance semantics
    + immutable/replayable evidence
    + character-native ownership/relationships
    + deterministic temporal retrieval
    + explicit cross-space grants
    + atomic v1 -> v2 authority cutover
```

Changes to the authority hierarchy, evidence semantics, ownership key, grant model, or
cutover invariants require an explicit architecture revision rather than incidental
implementation drift.
