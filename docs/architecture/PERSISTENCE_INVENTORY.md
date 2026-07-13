# Omnix Persistence Inventory

**Baseline commit:** `6041c287adcc4b4c513beff9e747849d25f56b5d`  
**Target:** PostgreSQL is the sole authoritative structured-data database; local BlobStore owns large artifacts; Redis remains optional and reconstructible.

This inventory records known mutable stores before the PostgreSQL migration. Phase-specific importers must update this document when additional legacy stores are found.

## Classification

- **Authoritative:** currently determines application truth and must migrate to PostgreSQL.
- **Derived/cache:** can be reconstructed and should not be migrated unless useful.
- **Artifact:** binary or large immutable content retained in BlobStore with PostgreSQL metadata.
- **Secret:** must move behind `SecretStore`, not a normal plaintext domain column.
- **Disposable:** temporary execution data that may be deleted safely.

## SQLite-backed runtime stores

| Current owner/path | Current authority | Target | Migration phase |
|---|---|---|---|
| `src/app/chat/repository.py` | Chat sessions and messages | PostgreSQL chat tables with granular append/update operations | 4 |
| `src/app/chat/sqlite_schema.py` | Chat schema | PostgreSQL migrations | 4 |
| `src/app/chat/history_search.py` | Chat search/index state | PostgreSQL indexed queries or derived search projection | 4/7 |
| `src/app/chat/compaction.py` | Chat compaction state | PostgreSQL summaries and retention metadata | 4 |
| `src/app/assistant_memory/repository.py` | Memory records, candidates, snapshots, events | PostgreSQL memory tables | 4 |
| `src/app/assistant_memory/schema.py` | Memory schema | PostgreSQL migrations | 4 |
| `src/app/assistant_memory/owner_repository.py` | Memory owner bindings | PostgreSQL tenant ownership | 4 |
| `src/app/characters/repository.py` | Character profiles, versions, segments | PostgreSQL character tables | 4 |
| `src/app/characters/avatar_repository.py` | Avatar metadata | PostgreSQL asset/character metadata plus BlobStore | 3/4 |
| `src/app/characters/avatar_generation_repository.py` | Avatar generation state | PostgreSQL jobs/assets | 3/5 |
| `src/app/characters/avatar_viseme_generation.py` | Viseme generation state | PostgreSQL jobs/assets | 3/5 |
| `src/app/jobs/store.py` | Durable jobs and events | PostgreSQL job ledger | 5 |
| `src/app/jobs/residency.py` | Residency records/projections | PostgreSQL worker/resource projection; later Redis cache if measured | 5/7 |
| `src/app/jobs/rpg_foreground_submission_store.py` | RPG submission ownership and replay result | PostgreSQL submission/turn transaction | 5/6 |
| `src/app/providers/cache_status.py` | Provider cache status | Derived PostgreSQL or in-memory diagnostics projection | 7 |
| `src/app/research/cache.py` | Research cache | Derived cache or PostgreSQL research records where durable | 7 |
| `src/app/rpg/narrative/narrative_persistence.py` | Narrative persistence | PostgreSQL campaign/turn or artifact metadata | 6/7 |
| `src/app/gateway/live_job_events.py` | SQLite error compatibility and event recovery | PostgreSQL outbox/event delivery | 5/7 |

## JSON, JSONL, and manifest authorities

| Current owner/path | Current authority | Target | Migration phase |
|---|---|---|---|
| `src/app/rpg/session/durable_store.py` | Full RPG session snapshots under `resources/data/rpg_sessions` | `rpg_campaigns.state_jsonb` plus snapshots | 6 |
| `src/app/rpg/session/interaction_event_store.py` | Checksummed recent interaction JSONL | PostgreSQL turn/interaction ledger | 6 |
| `src/app/assets/store.py` | Shared asset manifest | PostgreSQL asset metadata | 3 |
| Image asset manifests | Image metadata and file references | PostgreSQL asset metadata | 3 |
| Voice clone manifests | Voice metadata and sample references | PostgreSQL character/asset metadata | 3/4 |
| Prompt stores and prompt templates | User/application prompt metadata | PostgreSQL configuration/template tables | 7 |
| Provider configuration files | Provider settings and model selections | PostgreSQL non-secret configuration; SecretStore references | 3/7 |
| Application settings files | Mutable user/workspace settings | PostgreSQL settings tables | 7 |
| Reports and export manifests | Report metadata | PostgreSQL metadata plus BlobStore content | 3/7 |
| Local acceptance JSON reports | Verification evidence only | Artifact/report storage; never runtime authority | retain as artifact |

## Blob and filesystem artifacts

These remain on local storage initially, accessed through `BlobStore` and indexed in PostgreSQL:

- generated images and portraits;
- TTS and podcast audio;
- STT source audio and transcripts where stored as files;
- voice-clone samples and derived voice assets;
- video and animation outputs;
- large reports and export archives;
- model files and model caches;
- RPG export packages and optional large snapshots.

PostgreSQL metadata must include owner/workspace, MIME type, byte size, checksum, storage provider/key, lifecycle state, creation source, and related job.

## Secrets

Secret material must not be imported into ordinary domain tables:

- provider API keys;
- OAuth client secrets and refresh/access tokens;
- external service credentials;
- database administrative credentials;
- signing keys.

PostgreSQL may store a secret reference, owner, provider, timestamps, and non-sensitive status. Secret bytes remain behind `SecretStore`.

## Derived or disposable data

Do not migrate these merely to preserve their current representation:

- Python bytecode and build output;
- frontend build caches;
- Hugging Face/model download caches;
- transient uploaded chunks;
- temporary generation files before BlobStore finalize;
- expired OAuth state;
- reconstructible provider/model status caches;
- transient SSE/WebSocket subscriber state;
- test databases and fixtures;
- failed migration staging databases after reports are retained.

## Authoritative service owners

| Domain | Owning service boundary | Transaction requirements |
|---|---|---|
| Identity/tenancy | persistence identity service | memberships, roles, and audit records share one Unit of Work |
| Chat | chat service | session revision, appended messages, memory linkage, and outbox may commit together |
| Characters | character service | active profile revision and immutable version insert are atomic |
| Memory | memory service | record/candidate/snapshot lifecycle and event insert are atomic |
| Assets | asset service | metadata commit occurs only after blob finalize; orphan cleanup is explicit |
| Jobs | job service | claim/lease/attempt/event transitions are guarded and atomic |
| RPG | campaign/turn service | submission, turn, state revision/hash, job update, interaction, and outbox are atomic |
| Configuration | settings/provider service | secrets represented only by SecretStore references |

## Baseline measurement procedure

The repository cannot know operator data volume. Before cutover, run the Phase 8 preflight to record:

- every legacy database path and byte size;
- table row counts;
- JSON/JSONL file counts and total bytes;
- artifact counts and total bytes by MIME family;
- invalid/corrupt records;
- duplicate IDs and broken references;
- current RPG foreground median and p95 latency from the local live-smoke harness.

The generated report must contain counts, hashes, paths, and timings without copying prompts, memories, transcripts, secrets, or campaign content.

## Completion rule

Phase 9 is complete only when normal Omnix startup opens no SQLite database, writes no authoritative JSON/JSONL/manifest state, and PostgreSQL plus BlobStore can restore all supported local data from a documented backup.
