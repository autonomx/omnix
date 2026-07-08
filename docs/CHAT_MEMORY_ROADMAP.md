# Omnix Chat Memory Roadmap

Status: implementation and repository rollout gates complete through MEM-15 and Stage 6.

Target branch: `rpg`

Release baseline after Stage 6: `d4de5d1233db8d9cb382153a8683e3bff7bc2746`

## Release status

MEM-0 through MEM-15 are squash-merged into `rpg`. The six staged rollout gates are also merged. Every pull request passed both required GitHub Actions workflows on its exact head before merge:

- `RPG Phase 0 architecture compliance`
- `RPG deterministic PR gates`

Canonical exact-head, pull-request, workflow-run, and merge evidence is recorded in `docs/chat-memory/chat-memory-release-evidence.md`.

This is a repository release statement. Production feature-flag adoption remains an operational deployment decision. Hermes synchronization remains optional and should stay disabled unless a controlled pilot is intentionally adopted.

## Objective

Upgrade Omnix Chat from session-only transcript persistence to a controlled, persistent memory system with durable user preferences, workspace/project continuity, frozen per-session snapshots, bounded historical recall, long-session compaction, and an optional Hermes adapter.

The system remains local-first, deterministic at its policy boundaries, inspectable by the user, safe to disable, and fully usable when Hermes or FTS5 is unavailable.

## Ownership boundaries

- `ChatRepository` owns sessions and messages.
- `MemoryRepository` owns approved memory, pending candidates, snapshots, revocations, and memory audit events.
- `MemoryService` owns scope policy, selection, approval, editing, forgetting, and snapshot lifecycle.
- `PromptAssemblyService` owns the exact provider prompt structure for streaming and non-streaming paths.
- `HistorySearchService` owns bounded cross-session retrieval.
- Hermes uses an adapter and never becomes the canonical owner of normal Chat memory.

## Trust-separated prompt assembly

All provider requests are rendered from one typed structure:

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

1. Trusted system context: system instructions, assistant identity, approved user memory, and approved workspace/project memory.
2. Conversation context: current-session summary, recent turns, and bounded retrieved historical excerpts.
3. Untrusted reference context: webpages, desktop observations, documents, email, tool output, repository output, and unapproved Hermes observations.

Approved memory is never appended to the latest user message or rendered with the same wording used for untrusted external context.

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
- Scope filtering occurs before ranking, relevance scoring, or token-budget selection.
- Session memory never crosses session boundaries.
- Project memory never crosses project boundaries.
- Historical recall excludes the active session and applies profile, workspace, and project scope before ranking.

## Canonical persistence and trust model

Pending candidates and approved memory are separate representations. Assistant-suggested, imported, and Hermes-derived observations remain pending and non-prompt-eligible until explicitly approved. Approval creates a distinct active record with provenance and a user-approved trust level.

The memory repository provides:

- transactional SQLite persistence;
- optimistic record and snapshot revisions;
- candidate fingerprints and idempotency;
- deterministic scope-first queries;
- bounded pagination and token selection;
- audit events without sensitive diagnostic content;
- hard forget propagation.

## Snapshot semantics

A session snapshot is frozen for additions, ordinary edits, ranking changes, confidence changes, and newly approved memory. It is not immune to forget, revocation, expiration, lost scope access, or security invalidation.

A true forget operation removes active content, purges or irreversibly redacts frozen snapshot copies, excludes the record from future prompt assembly, and preserves only non-sensitive audit metadata.

Provider input is frozen when generation begins. Forget cannot retract bytes already sent to a provider, but every later provider assembly excludes the forgotten record.

## Feature flags

```text
OMNIX_CHAT_SQLITE_STORE_ENABLED=0
OMNIX_CHAT_MEMORY_ENABLED=0
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=0
OMNIX_CHAT_HISTORY_RECALL_ENABLED=0
OMNIX_CHAT_COMPACTION_ENABLED=0
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

Disabling a feature does not destroy stored memory, migrated history, summaries, or indexes. Destructive forget behavior is intentionally separate from feature rollback.

## Completed implementation phases

| Phase | Pull request | Completed capability |
|---|---:|---|
| MEM-0 | #1258 | Architecture audit, ownership, trust classes, scope model, rollout and rollback plan |
| MEM-1 | #1259 | Typed memory contracts, backend-owned scope identity, and policy helpers |
| MEM-2 | #1260 | Canonical trust-separated prompt assembly and deterministic budgets |
| MEM-3 | #1261 | SQLite memory repository, service operations, revisions, selection, and forget propagation |
| MEM-4 | #1262 | SQLite Chat repository and idempotent legacy JSON migration |
| MEM-5 | #1263 | Frozen snapshot lifecycle, explicit refresh, conflicts, and safety invalidation |
| MEM-6 | #1264 | Read-only approved-memory injection with streaming/non-streaming parity |
| MEM-7 | #1265 | Management API and functional Memory UI |
| MEM-8 | #1266 | Explicit remember, update, forget, list, refresh, and disable commands |
| MEM-9 | #1267 | Durable pending suggestion jobs and deterministic security filtering |
| MEM-10 | #1268 | Duplicate, contradiction, supersession, capacity, expiry, and trust policy |
| MEM-11 | #1269 | Scoped FTS5 historical retrieval and degraded-mode behavior |
| MEM-12 | #1270 | Durable long-session compaction with recent-turn retention and full-history fallback |
| MEM-13 | #1271 | Optional review-first Hermes import/export adapter |
| MEM-14 | #1272 | Persisted settings, server-side privacy enforcement, and content-free diagnostics |
| MEM-15 | #1273 | Adversarial release gate, mutation serialization, atomic JSON fallback writes, and release guidance |

## Completed staged rollout gates

| Stage | Pull request | Enabled boundary | Still disabled at that stage |
|---|---:|---|---|
| 1 | #1274 | SQLite Chat storage | Curated memory, suggestions, history, compaction, Hermes |
| 2 | #1275 | Explicit approved memory | Suggestions, history, compaction, Hermes |
| 3 | #1276 | Pending memory suggestions | History, compaction, Hermes |
| 4 | #1277 | Scoped historical recall | Compaction, Hermes |
| 5 | #1278 | Long-session compaction | Hermes |
| 6 | #1279 | Optional Hermes adapter | None in the controlled full-stack pilot |

Each stage includes a runbook, temporary-store preflight, unit coverage, rollback instructions, and exact-head merge evidence.

## Recommended operational posture

The fully verified native stack is Stages 1 through 5:

```text
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1
OMNIX_CHAT_HISTORY_RECALL_ENABLED=1
OMNIX_CHAT_COMPACTION_ENABLED=1
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

Enable Hermes only after backing up the selected Hermes memory directory, running `scripts/chat_memory_stage6_preflight.py`, and accepting the review-first import/export model.

## Safety and rollback guarantees

- Pending and rejected candidates never enter prompts.
- New approvals do not silently change an active frozen session snapshot.
- Forget overrides frozen snapshots for future prompt assembly.
- Historical retrieval is bounded, scope-first, excludes the active session, and degrades nonfatally when FTS5 is unavailable.
- Pending or failed compaction preserves the complete current-session transcript.
- Persisted summaries are contextual aids and never become approved curated memory automatically.
- Hermes imports remain pending until approval and Hermes-origin records are not exported back to Hermes.
- Missing or unwritable Hermes storage does not fail normal Chat.
- Disabling any feature retains native data.
- Do not alternate JSON and SQLite writers after new SQLite-only messages accumulate without first reconciling the stores.

## Verification contract

GitHub Actions is the source of truth. No verification result is claimed unless it actually ran. Every phase and rollout pull request passed the required checks on its exact head before squash merge with `expected_head_sha`.

Where applicable, coverage includes Python unit tests, gateway route tests, OpenAPI regression tests, frontend typecheck and unit tests, migration/restart behavior, prompt parity, deterministic RPG smoke coverage, adversarial scope and injection cases, concurrency, degraded modes, and rollback behavior.

## Definition of done

Complete.

New chats can use approved personal and project memory; scope is server-authoritative; users can inspect and control saved records; inferred memory remains pending until approved; active sessions use stable but safely revocable snapshots; historical conversations are retrieved through bounded FTS; long sessions use verified summaries plus recent turns; streaming, non-streaming, voice, and text use one prompt assembly; Hermes shares only approved compatible memory when explicitly enabled; normal Chat works with Hermes offline; and every capability has tested rollback controls.
