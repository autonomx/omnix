# Omnix Chat Memory Roadmap

Status: canonical implementation roadmap

Target branch: `rpg`

## Objective

Upgrade Omnix Chat from session-only transcript persistence to a controlled, persistent memory system with durable user preferences, workspace/project continuity, frozen per-session snapshots, bounded historical recall, long-session compaction, and an optional Hermes adapter.

The system must remain local-first, deterministic at its policy boundaries, inspectable by the user, safe to disable, and fully usable when Hermes is unavailable.

## Current-state audit

The repository already contains frontend memory value objects and view-model actions for scopes, categories, pinning, approval, editing, forgetting, and moving scope. These contracts are not backed by an authoritative memory service.

The live Chat Memory page is presently informational. It does not expose real persisted memory state.

Chat sessions are currently persisted through the JSON-backed Chat store, and provider requests are assembled from the complete prior session transcript. This creates unbounded prompt growth and no cross-session curated memory.

`AssistantContextService` is the existing orchestration seam for web and desktop context, but approved memory must not enter its generic untrusted `context_items` representation. A typed prompt-assembly layer is required first.

## Ownership boundaries

- `ChatRepository` owns sessions and messages.
- `MemoryRepository` owns approved memory, pending candidates, snapshots, revocations, and memory audit events.
- `MemoryService` owns scope policy, selection, approval, editing, forgetting, and snapshot lifecycle.
- `PromptAssemblyService` owns the exact provider prompt structure for streaming and non-streaming paths.
- `HistorySearchService` owns bounded cross-session retrieval.
- Hermes uses an adapter and never becomes the canonical owner of normal Chat memory.

## Trust-separated prompt assembly

All provider requests must be rendered from one typed structure:

```text
PromptAssembly
- system_instructions
- assistant_identity
- approved_memory
- session_summary
- recent_messages
- retrieved_history
- external_context
- current_user_message
- diagnostics
```

Trust classes:

1. Trusted system context: system instructions, assistant identity, approved user memory, approved workspace/project memory.
2. Conversation context: current-session summary, recent turns, bounded retrieved historical excerpts.
3. Untrusted reference context: webpages, desktop observations, documents, email, tool output, repository output, and unapproved Hermes observations.

Approved memory must never be appended to the latest user message or rendered with the same wording used for untrusted external context.

## Authoritative scope identity

Every session resolves a backend-owned scope:

```text
ChatScope
- profile_id
- workspace_id
- project_id
- session_id
```

Rules:

- The server derives or validates scope identity.
- Arbitrary client-provided project identifiers are not trusted.
- Existing sessions migrate to a named default workspace and no project scope unless safely derived.
- Scope filtering occurs before ranking, relevance scoring, or token-budget selection.
- Session memory never crosses session boundaries.
- Project memory never crosses project boundaries.

## Canonical persistence model

Pending candidates and approved memory are separate representations.

```text
memory_candidates
- id
- source_session_id
- source_message_id
- candidate_fingerprint
- proposed_scope
- proposed_category
- proposed_content
- confidence
- extraction_metadata
- status: pending | rejected | accepted
- created_at
- resolved_at
```

Approval creates a distinct `memory_records` row:

```text
memory_records
- id
- scope
- scope_id
- category
- source
- content
- normalized_content
- confidence
- pinned
- trust_level
- provenance_type
- provenance_id
- status: active | superseded | archived
- revision
- created_at
- updated_at
- expires_at
```

## Snapshot semantics

A session snapshot is frozen for additions, ordinary edits, ranking changes, confidence changes, and newly approved memory. It is not immune to forget, revocation, expiration, lost scope access, or security invalidation.

```text
memory_snapshots
- id
- session_id
- revision
- created_at
- refreshed_at
- token_estimate

memory_snapshot_items
- snapshot_id
- memory_record_id
- record_revision
- frozen_content
- revoked_at
```

A true forget operation must remove active content, purge search indexes, purge or irreversibly redact frozen snapshot copies, preserve only non-sensitive audit metadata, and prevent future prompt rendering.

## Feature flags

```text
OMNIX_CHAT_MEMORY_ENABLED=0
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=0
OMNIX_CHAT_HISTORY_RECALL_ENABLED=0
OMNIX_CHAT_SQLITE_STORE_ENABLED=0
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

Disabling a feature must not destroy stored memory or migrated history.

## Implementation phases

### MEM-0 — Architecture audit and canonical roadmap

- Record current-state gaps and authoritative ownership.
- Define prompt trust classes, scope identity, pending-candidate representation, snapshot revocation, migrations, rollout, and rollback.
- Inventory placeholder memory claims in the UI.

Acceptance: documentation only; no runtime behavior changes.

### MEM-1 — Contracts, scope identity, and policy

- Add typed memory, candidate, snapshot, provenance, trust, revision, and sensitivity models.
- Extend Chat contracts with validated profile/workspace/project scope and memory metadata.
- Add pure policy helpers for visibility, prompt eligibility, trust transitions, expiration, scope moves, forgetting, and sensitive-content restrictions.

Acceptance: scope cannot be forged by a request; pending candidates are never prompt eligible; external content cannot elevate its own trust.

### MEM-2 — Prompt assembly and token budgeting

- Add one typed prompt assembly path for streaming and non-streaming Chat.
- Separate approved memory, summaries, recent turns, retrieved history, external context, and current user input.
- Add stable ordering, deterministic budgets, and serialized diagnostics.

Acceptance: identical inputs create identical serialized assemblies; memory-disabled provider request and persistence behavior remain compatible with the current path.

### MEM-3 — SQLite memory repository and service

- Add transactional SQLite storage for records, candidates, snapshots, snapshot items, events, and schema version.
- Add optimistic revisions, deterministic queries, bounded pagination, idempotent initialization, forget propagation, and audit events.
- Add canonical memory service operations.

Acceptance: restart-safe, conflict-safe, and deterministic; forgotten content is removed from every active selection path.

### MEM-4 — ChatRepository and SQLite Chat migration

- Introduce a Chat repository abstraction and SQLite implementation.
- Add idempotent JSON import with source hashes, checkpoints, verification, quarantine/reporting for malformed rows, and temporary rollback preservation.
- Test crashes before, during, and after import and assistant completion.

Acceptance: all readable existing sessions survive; repeated or interrupted import does not duplicate or corrupt data.

### MEM-5 — Snapshot lifecycle and safety invalidation

- Create and restore session snapshots.
- Add explicit refresh.
- Add revocation and forget overlays.
- Define concurrency for forget, refresh, approval, and active generation.

Acceptance: new approvals do not silently change active sessions; forget overrides frozen snapshots.

### MEM-6 — Read-only memory injection

- Resolve the current snapshot and add approved memory to typed prompt assembly.
- Integrate both normal and assistant-context Chat routes.
- Persist selected IDs and diagnostics.
- Keep writes disabled.

Acceptance: only approved matching-scope records are rendered; memory-disabled mode preserves prior provider payload and persisted-message behavior.

### MEM-7 — Management API and functional UI

- Add list/create/read/edit/forget/pin/unpin/move operations.
- Add candidate list/approve/reject operations.
- Replace the placeholder Memory screen with backend-derived active snapshot, saved memory, pending candidates, provenance, filters, and controls.

Acceptance: every UI claim comes from backend state; destructive operations are confirmed; mutations use expected revisions.

### MEM-8 — Explicit memory commands

- Support explicit remember, update, forget, list, refresh, and memory-disabled session intents.
- Use deterministic intent resolution first.
- Keep ambiguous operations non-mutating.

Acceptance: direct user saves create approved user records; ordinary uses of the word “remember” do not mutate state.

### MEM-9 — Durable pending suggestions

- Add durable jobs such as `assistant.memory.suggest`, `assistant.memory.import`, `assistant.memory.consolidate`, and `assistant.history.compact`.
- Add candidate fingerprints and idempotency constraints.
- Apply deterministic eligibility and security filtering before model extraction.

Acceptance: retries and worker resumes do not duplicate candidates; extraction failure does not affect Chat completion.

### MEM-10 — Consolidation, contradiction, capacity, and trust

- Add duplicate detection, supersession, contradiction detection, expiration, scope and token budgets, sensitivity screening, trust transitions, and consolidation candidates.

Acceptance: contradictory active records are surfaced; superseded records are excluded; pinned records cannot bypass hard budgets.

### MEM-11 — FTS5 historical retrieval

- Add Chat message FTS indexing, bounded search, scope filters, provenance, startup capability detection, and degraded status.
- Keep curated memory independent from history recall.

Acceptance: no cross-scope leakage; deleted sessions disappear from retrieval; unavailable FTS does not fail normal Chat.

### MEM-12 — Long-session compaction

- Add versioned session summaries and recent-turn retention.
- Add durable compaction jobs and bounded retrieval of older relevant turns.
- Keep summaries contextual and never automatically promote them to approved memory.

Acceptance: very long sessions stay within configured budgets and preserve recent turns verbatim.

### MEM-13 — Hermes adapter

- Import Hermes-compatible observations as pending candidates.
- Export only approved compatible Omnix records when enabled.
- Preserve provenance, detect conflicts, prevent loops, and exclude scratchpad/tool output.

Acceptance: Hermes offline or disabled never affects normal Chat; re-imports are idempotent.

### MEM-14 — Settings, privacy, and diagnostics

- Add global and per-session controls for curated memory, history recall, automatic candidates, approval policy, Hermes sync, budgets, and retention.
- Add compact diagnostics without exposing sensitive content.

Acceptance: enforcement is server-side and memory/history can be independently disabled.

### MEM-15 — Adversarial and release gate

Cover at minimum:

1. Cross-project and cross-session isolation.
2. Pending/rejected candidate exclusion.
3. Forget propagation into frozen snapshots and indexes.
4. Web/email/tool/Hermes prompt-injection resistance.
5. Duplicate retry protection.
6. Contradiction and capacity behavior.
7. Stale-revision conflicts.
8. Restart-safe JSON migration.
9. SQLite partial-write and active-generation failure behavior.
10. FTS deletion and degraded-mode behavior.
11. Streaming/non-streaming serialized prompt parity.
12. Memory-disabled compatibility.
13. Long-session budget enforcement.
14. Existing session compatibility.
15. Voice/text snapshot parity.
16. Hermes-offline independence.
17. Simultaneous sends and edits.
18. Forget/refresh during active generation.

Acceptance: required GitHub Actions checks pass on the exact release head; rollout and rollback evidence is documented.

## Required verification per phase

Every implementation PR must use GitHub Actions as the source of truth and pass the required checks on the exact PR head before merge:

- RPG Phase 0 architecture compliance
- RPG deterministic PR gates

Where applicable, coverage must include Python unit tests, gateway route tests, OpenAPI regression tests, frontend typecheck and unit tests, migration/restart behavior, prompt parity, and deterministic RPG smoke coverage.

No verification result may be claimed unless it actually ran.

## Definition of done

The roadmap is complete when new chats can use approved personal and project memory; scope is server-authoritative; users can inspect and control saved records; inferred memory remains pending until approved; active sessions use stable but safely revocable snapshots; historical conversations are retrieved through bounded FTS; long sessions no longer send the full transcript indefinitely; streaming, non-streaming, voice, and text use one prompt assembly; Hermes shares only approved compatible memory; normal Chat works with Hermes offline; and all capabilities have tested rollback controls.
