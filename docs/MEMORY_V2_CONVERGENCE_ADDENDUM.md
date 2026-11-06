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

## 11. Conversation readings (2026-11-05)

Conversations now feed the derived state this architecture describes: each finished turn is
written to the owner's Observation Log (`user_said`, `assistant_generated`), and when the talk
has gone quiet for five minutes, or reached 40 unread user turns, a background job has the
model read that stretch of one chat (`assistant_memory/conversation_reading.py`). No part of
this is on the path of a reply.

**A reading is stored as an observation (`conversation_reading`), which bends section 4.** An
observation records what happened, and a reading records what a model concluded. It goes in the
log anyway because a governance rebuild replays the log and deletes what its plan leaves out, so
the alternative is calling the model again over the whole history on every forget. Instead the
planner (`v2/understanding.MemoryPlanner`, the one planner of a space) is deterministic and needs
no model, so a rebuild is exact and immediate. The bend is bounded: a reading carries
`assistant_inference` trust and cites the `user_said` observations it rests on.

A reading runs on a stronger model than a live call (`OMNIX_MEMORY_READING_MODEL`; Sonnet on the
Claude CLI), because nobody waits for it and Haiku took role-play literally.

What a reading may contain is decided by code, not the model: note aspects and moods are closed
lists, a note or connection must cite the user's own turns, and a connection must name something
the user said. Secrets and sensitive inferences are refused. Relationship scores stay out of the
prompt (section 7), and a mood is stated with its age and only for a week (section 8).

A reading also lists the person's reactions to replies, after VoiceMem's reaction attribution
(`rightbrain/brain.py`, `learn_from_reaction`): corrected, pushed back, brushed off, thanked,
approved or mood changed, with what in the reply caused it and the lasting pattern it shows. Code
keeps a reaction only when it is the person's turn answering a reply and its pattern is a short
phrase (VoiceMem's trait titles: no subject, no full stop). As there, a correction or pushback
means the reply did not help and thanks or approval that it did, whatever the model says. Each
pattern is a lesson; a reaction showing it again adds evidence instead of a second lesson, matched
by the known lesson's number the reader is shown (where VoiceMem compares embeddings) or by the
same words, and keeps the wording it was first seen with. Lessons are trait assertions
(`lesson_<aspect>`, revision = times seen); the six seen most reach every reply. Two parts of
VoiceMem are left out: the fixed word lists that force a reaction to count, since the whole stretch
is read by a stronger model, and reading each turn as it happens, which waits on a decision about
per-turn learning.

Three more come from VoiceMem. A reading lists triggers, what brings on a feeling and what it
concerns ("Stressed when deadlines move", about "manager"): VoiceMem's situation patterns anchored to
entities. The names must be the user's own words, a trigger seen again adds evidence as a lesson
does, and it reaches a reply only when the turn names what it concerns: the prompt skips triggers
that general retrieval returns, because retrieval falls back to every active item when no word
matches. A note the reader marks as turned around (not refined) keeps the note before it as a
superseded assertion, as VoiceMem keeps a contradicted state marked old; replies see it as "Changed
3 weeks ago; before that: ...", and it can be forgotten on its own. The person's own rewording
clears that history. Finally, every retrieved fact carries when it became known
(`RetrievalCandidate.learned_at`) and is rendered "noted 3 months ago". VoiceMem writes the date,
but our prompts state no date, so an age is what a reply can use.

VoiceMem models only the user. A reading here also notes the owner's own side, so that a
character can change too: its stance toward the person (one sentence spoken to it), what it
promised (resting on its own turns only; open until a later reading marks it kept or dropped) and
running jokes (at least two turns, or a known joke seen again). They are assertions on the owner as
subject (`own_stance`, `running_joke` in relationship, `promised` in open_loop) and reach every reply
from the understanding alone: the prompt skips their retrieval copies, and marks promises with their
own category, because a saved memory can be an `open_loop` too.

What helps, what puts the person off, and the lessons reach the prompt as guidance ("Works with
them: ...", "Puts them off: ..."), with a line telling the owner to act on them in its own voice.
Measured on the live model (Haiku 4.5) with Jinx's real memory, the same "build me something, don't
ask questions" opener: as plain notes about the person she used them to describe them and asked
about 8 questions (2 tries); without memory about 3.6 (7 tries); as guidance about 2.3 (7 tries).
So the reader writes what_helps and what_to_avoid as advice to the owner, and each reaction carries
advice (VoiceMem's `next_time`, which it dropped because nothing read it); a lesson reaches a reply
as its newest advice. A note on how the person talks that mentions transcription is dropped in code
as well as forbidden in the prompt: the model noted "transcription-style slips" despite the rule.
Only that aspect is checked, because speech-to-text can be a subject the person cares about.

Forgetting one item rewrites every reading that holds it and purges the originals, and
`_redact_decisions_after` clears later decision sets too, because a plan re-emits every reading. A
deleted chat (`chat.session.deleted`) purges its turns, its readings, and every later reading,
since those saw the earlier conclusions; the remaining turns are read again. A note the person
reworded is not overwritten by a later reading. Memories saved from a chat stay when it is deleted:
they are listed in the Memory tab and are forgotten there.
