# Omnix Character Mode Roadmap

Status: repository implementation complete through CHAR-11; production rollout remains disabled by default

Target branch: `main`

Release baseline after CHAR-11: `cc42b5d18c02886ef3d51996f345cb74aea07058`

Canonical completion evidence: `docs/character-mode/character-mode-release-evidence.md`

Staged deployment and rollback guide: `docs/character-mode/character-mode-rollout.md`

Repository completion records merged implementation, tests, and exact-head gates. It does not claim that Character Mode or its high-risk capabilities are enabled in a production deployment.

## Objective

Add persistent, user-controlled AI characters to Omnix Chat without coupling identity to a cloned voice and without creating a second memory engine.

A character combines a server-owned profile, a default voice association, a versioned identity/personality prompt, speech-delivery preferences, and an isolated owner namespace inside the existing Omnix memory stack.

The user-facing modes are:

- **System Assistant** — the selected voice is a renderer; normal assistant identity and normal assistant memory apply.
- **Character Mode** — a selected character supplies identity, personality, greeting, speech style, and isolated character memory.
- **Character Mode with memory disabled** — character identity and voice apply, but no character memory is read or written.
- **Private character call** — no character memory is read or written and the transcript is not retained after the call.

## Non-negotiable boundaries

1. A voice asset is not a character.
2. Selecting a voice never activates a character by itself.
3. The browser may select IDs and policies, but it may not provide trusted character prompts or memory namespaces.
4. The existing Omnix memory service remains authoritative; Hermes stays optional and non-authoritative.
5. Character isolation is enforced before scope filtering, ranking, history retrieval, compaction, or token budgeting.
6. Switching identity creates a new logical conversation segment.
7. Memory read, memory write, and transcript retention are distinct policies.
8. Existing Chat sessions and memory records migrate to System Assistant ownership without content loss.
9. Feature flags must allow staged rollout and non-destructive rollback.
10. Streaming and non-streaming generation must use the same canonical prompt assembly.

## Existing foundation

Character Mode builds on:

- `src/app/chat/prompt_assembly.py` and `prompt_rendering.py` for trust-separated prompt construction.
- `src/app/assistant_memory` for curated memory, pending candidates, snapshots, history recall, compaction, privacy, and Hermes adaptation.
- `src/app/assets` for voice-profile assets.
- `src/app/chat` and `src/app/gateway` for session persistence and typed APIs.
- `src/apps/web/src/features/chatbot` for Chat, live voice, personality, voice selection, and memory management.

No separate character-memory database or transcript replay mechanism should be introduced.

## Canonical concepts

### VoiceAsset

Represents how speech sounds.

Required relationship rule:

```text
CharacterProfile.default_voice_asset_id -> VoiceAsset.id
```

The association is optional and replaceable. Voice deletion must not delete the character or its memory.

### CharacterProfile

Represents who is speaking.

```text
id
display_name
description
personality_prompt
default_greeting
default_voice_asset_id
speech_style_json
identity_policy_json
shared_memory_policy_json
active_version
enabled
created_at
updated_at
```

### CharacterProfileVersion

Provides reproducible identity configuration.

```text
character_id
version
personality_prompt
default_greeting
speech_style_json
identity_policy_json
created_at
```

### ConversationSegment

Represents a continuous provider-context identity boundary.

```text
id
session_id
interaction_mode: system | character
character_id: nullable
profile_version: nullable
started_at
ended_at
carryover_summary: nullable
```

### Memory ownership

Preserve the existing scope dimension:

```text
scope: global | workspace | project | session
scope_id: existing backend-resolved scope ID
```

Add a separate owner dimension:

```text
owner_type: system | character
owner_id: system-assistant | <character-id>
```

Examples:

```text
system / system-assistant / global
character / maya / global
character / maya / workspace
character / maya / session
```

Owner filtering occurs before existing scope policy.

## Session policy

Chat sessions gain:

```text
interaction_mode: system | character
character_id: nullable
voice_asset_id: nullable
read_memory: boolean
write_memory: boolean
shared_memory_access: none | read_only
transcript_policy: persistent | temporary | none
active_segment_id: nullable
character_profile_version: nullable
effective_identity_hash: nullable
```

Existing sessions migrate to:

```text
interaction_mode = system
character_id = null
read_memory = existing memory_enabled
write_memory = existing memory_enabled
shared_memory_access = none
transcript_policy = persistent
```

## Prompt composition

The server resolves the effective identity and memory selection. The browser never submits a trusted personality prompt for an existing character.

Canonical order:

```text
1. Core application/system instructions
2. System Assistant identity or versioned CharacterProfile identity
3. Approved owner-matching memory
4. Frozen session/segment summary
5. Recent messages from the active segment
6. Bounded owner-and-scope-matching historical excerpts
7. Untrusted external context
8. Current user message
```

Character memories are rendered as approved background context, never as instructions that can override core rules.

## Privacy and retention policies

The backend models three independent controls:

```text
read_memory: true | false
write_memory: true | false
transcript_policy: persistent | temporary | none
```

Initial UI may expose a combined `Remember conversations` toggle while preserving the independent server contract.

Private call semantics:

- no curated-memory read;
- no history recall;
- no memory candidate extraction;
- no approved-memory write;
- no durable transcript or derived summary after the call ends;
- content-free operational diagnostics may remain.

## Identity switching

Changing any of the following closes the active segment and creates a new one:

- System Assistant -> Character Mode;
- Character Mode -> System Assistant;
- one character -> another character;
- persistent mode -> private mode;
- a memory-policy change that alters provider context.

A neutral carryover summary may be created only when the user chooses to continue the topic. It must exclude character style instructions and private character memories.

## Feature flags

```text
OMNIX_CHARACTER_MODE_ENABLED=0
OMNIX_CHARACTER_MEMORY_ENABLED=0
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

Disabling flags must not destroy character profiles, memory, or transcripts.

## Ownership boundaries

- `CharacterRepository` owns profiles and versions.
- `ConversationSegmentRepository` owns identity/context boundaries.
- `ChatRepository` owns sessions and messages.
- `MemoryRepository` owns records, candidates, snapshots, revocations, and audit events.
- `MemoryService` owns character owner filtering plus existing scope policy.
- `PromptAssemblyService` owns trusted identity and prompt structure.
- `SharedAssetStore` owns voice-profile asset references.
- Hermes remains an adapter and never selects or creates a trusted character owner.

## Deletion semantics

The UI must offer independent actions:

- archive/delete character profile;
- delete character memory;
- delete linked voice asset;
- delete character transcripts;
- delete all related data.

Deleting a voice unlinks or replaces the default voice but preserves the character and memory.

Deleting a character does not delete a voice unless explicitly requested.

Forgetting memory must propagate through snapshots, summaries, FTS indexes, and future prompt selection.

## Implementation phases

### CHAR-0 — Canonical architecture and rollout contract

- Add this roadmap and architecture contract.
- Define models, boundaries, flags, migrations, prompt order, privacy, deletion, rollout, rollback, and test invariants.

Acceptance: documentation only; no runtime behavior changes.

### CHAR-1 — Server-owned interaction contracts

- Extend typed Chat contracts with interaction mode, character selection, voice selection, memory policies, transcript policy, and segment identity.
- Add a pure server-side interaction-context resolver.
- Add feature-flag parsing and neutral System Assistant identity.
- Preserve existing behavior while Character Mode is disabled.

Acceptance: the client cannot submit a trusted character prompt or namespace; existing sessions remain compatible.

### CHAR-2 — Character persistence and management API

- Add transactional SQLite character profile/version/segment repositories.
- Add create, read, list, update, enable/disable, version history, and archive APIs.
- Validate default voice references against shared voice-profile assets.

Acceptance: restart-safe, versioned, deterministic, and independent from voice deletion.

### CHAR-3 — Character Mode without memory

- Add Character Mode controls and identity badge in the shared React web app.
- Resolve character personality, greeting, default voice, and speech style server-side.
- Keep character-memory reads/writes disabled.

Acceptance: voice-only mode never activates a character; text and live voice use the same identity.

### CHAR-4 — Context segments and identity switching

- Persist conversation segments.
- Start a new segment for identity, privacy, or context-affecting memory-policy changes.
- Add optional neutral topic carryover.

Acceptance: old character style/private context never leaks into the new identity.

### CHAR-5 — Character memory ownership

- Add `owner_type` and `owner_id` to records, candidates, snapshots, audit events, history, compaction, and selection.
- Migrate existing memory to `system/system-assistant` ownership.

Acceptance: owner filtering precedes scope filtering and no cross-character/system leakage is possible.

### CHAR-6 — Character memory reads and writes

- Add independent read/write policies.
- Reuse approved memory, pending suggestions, explicit remember/forget, snapshots, and asynchronous extraction.

Acceptance: memory-off has zero character reads/writes; read-only and write-only policies behave independently.

### CHAR-7 — Shared System Assistant memory permissions

- Add `none | read_only` access to permitted normal assistant memory.
- Add category policy foundations and sensitivity restrictions.

Acceptance: characters never write global System Assistant memory by default.

### CHAR-8 — Live-call personality and speech behavior

- Apply profile greeting and speech-style metadata to live voice.
- Preload profile, voice, snapshot, and compact relationship context.
- Preserve first-token/first-audio latency instrumentation.

Acceptance: voice delivery and language identity remain separate; memory extraction never blocks first audio.

### CHAR-9 — Character and memory management UI

- Add profile editor, character list, memory view, pending suggestions, export, forget, reset, archive, and independent deletion choices.

Acceptance: every claim comes from backend state and destructive actions are explicit.

### CHAR-10 — Voice ownership, consent, and provenance

- Extend voice-profile metadata with source, ownership, consent, allowed uses, hashes, and deletion state.
- Enforce character identity disclosure policy.

Acceptance: restricted voices cannot be silently linked or used.

### CHAR-11 — Optional Hermes compatibility

- Keep character import/export disabled by default.
- Add explicit owner-aware, review-first compatibility with loop prevention and provenance.

Acceptance: ordinary Hermes sync never exports character memory; Hermes availability never affects native Character Mode.

## Required invariants

- Streaming and non-streaming paths serialize equivalent effective prompts.
- Voice selection alone never activates a character.
- Character Mode off performs no character-memory reads or writes.
- System Assistant cannot retrieve character relationship memory.
- One character cannot retrieve another character's memory or history.
- Read and write policies are independently enforceable.
- Private calls leave no durable transcript, summary, or derived memory.
- Identity switching creates a clean context boundary.
- Changing voice does not change character.
- Changing character does not reuse the previous character's segment context.
- Profile version and effective identity hash are persisted.
- Forget propagates through snapshots, summaries, and search indexes.
- Character memory does not enter Hermes without explicit owner-aware permission.
- Rollback leaves normal Chat and existing memory intact.

## Staged rollout

1. Character/profile schema and APIs with all character flags disabled.
2. Character Mode without memory.
3. Character-memory read-only pilot.
4. Explicit character-memory writes.
5. Pending suggestions, history recall, and compaction.
6. Shared-memory read-only permissions.
7. Optional controlled Hermes compatibility.

The repository implementation for all seven stages is complete. Operational adoption must still proceed stage by stage using `docs/character-mode/character-mode-rollout.md`; later flags must not be enabled merely because the code is merged.
