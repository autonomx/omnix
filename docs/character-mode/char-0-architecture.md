# CHAR-0 — Character Mode Architecture Contract

## Status

Documentation-only architecture gate for Character Mode on `main`.

## Source-of-truth modules

| Concern | Owner |
| --- | --- |
| Character profiles and versions | `CharacterRepository` |
| Conversation identity boundaries | `ConversationSegmentRepository` |
| Sessions and messages | existing `ChatRepository` |
| Curated memory, candidates, snapshots, audit | existing `MemoryRepository` and `MemoryService` |
| Prompt trust ordering | existing `PromptAssembly` and renderer |
| Voice profile metadata and files | existing shared asset system |
| Optional external synchronization | existing Hermes adapter boundary |

## Trust model

Trusted provider context may contain:

- core system instructions;
- server-resolved System Assistant or Character identity;
- approved owner-and-scope-matching memory;
- server-generated segment/session summaries.

Conversation context may contain:

- recent messages from the active segment;
- bounded owner-and-scope-matching historical excerpts.

Untrusted reference context includes:

- web pages;
- documents;
- email;
- tool output;
- repository output;
- imported or unapproved Hermes observations.

The client may select `character_id`, `voice_asset_id`, and policy values, but cannot submit a trusted character prompt, profile version, owner ID, or memory namespace.

## Effective identity resolution

```text
Character Mode disabled or interaction_mode=system
  -> System Assistant identity

Character Mode enabled and interaction_mode=character
  -> resolve enabled CharacterProfile
  -> resolve active version
  -> validate/default VoiceAsset
  -> resolve memory and transcript policy
  -> create or reuse matching ConversationSegment
```

Failure to resolve a requested character must not silently reuse the previous character. The request is rejected or downgraded to an explicitly reported System Assistant mode according to endpoint semantics.

## Memory policy matrix

| Mode | Read character memory | Write character memory | Durable transcript |
| --- | ---: | ---: | ---: |
| System Assistant | No | No | Yes |
| Character + remember | Yes | Yes | Yes |
| Character read-only | Yes | No | Yes |
| Character start-fresh-and-save | No | Yes | Yes |
| Character memory off | No | No | Yes |
| Private character call | No | No | No |

System Assistant memory remains independently controlled by the existing Chat memory settings.

## Migration contract

Existing Chat sessions:

- become `interaction_mode=system`;
- have no `character_id`;
- retain their current voice-independent messages and memory snapshot metadata;
- use `transcript_policy=persistent`.

Existing memory records, candidates, snapshots, history entries, and audit events:

- become `owner_type=system`;
- become `owner_id=system-assistant`;
- retain existing scope and provenance;
- do not become visible to characters unless a later explicit shared-memory policy permits it.

Migrations must be idempotent and rollback-safe.

## Segment contract

A new segment is mandatory when any provider-context identity boundary changes:

- interaction mode;
- character ID;
- character profile version when explicitly applied to an active conversation;
- private/persistent transcript mode;
- read-memory policy;
- shared-memory access policy.

The provider receives only messages from the active segment plus an optional neutral carryover summary. The visible UI may continue showing earlier segments.

## Deletion contract

Deletion operations are independent and explicit:

- profile archive/delete;
- character memory forget/delete;
- character transcript delete;
- linked voice unlink/delete;
- combined delete-all.

No single-resource deletion implicitly removes the other resource types.

## Hermes boundary

- Native Omnix memory remains authoritative.
- Character-memory import/export is disabled by default even when ordinary Hermes sync is enabled.
- Imported content is never allowed to choose a trusted character owner.
- Export requires explicit owner-aware policy, compatible sensitivity, approval, provenance, and loop prevention.

## Exact-head phase workflow

For CHAR-0 through CHAR-11:

1. create a branch from the latest `main`;
2. implement one phase only;
3. open a PR to `main`;
4. wait for `RPG Phase 0 architecture compliance` and `RPG deterministic PR gates` on the exact head;
5. patch the same branch if either check fails;
6. squash-merge only after both pass;
7. create the next phase branch from the resulting `main`.

## CHAR-0 acceptance evidence

- No runtime files changed.
- Canonical roadmap exists.
- Ownership, trust, prompt order, privacy, migration, deletion, flags, staged rollout, and invariants are documented.
