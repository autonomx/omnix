# Omnix Audiobook — Final Implementation Roadmap

**Status:** Final architecture baseline  
**Branch:** `agent/audiobook-roadmap-v1`  
**Base:** `main` at `a30ea226d4ec92d37d9cf0b00985f0933e5f2c0c`  
**Primary route:** `/audiobook`  
**Reference project:** https://github.com/Finrandojin/alexandria-audiobook (design/code donor only; not a runtime dependency)  
**Source-fidelity reference PR:** https://github.com/Finrandojin/alexandria-audiobook/pull/82

## 1. Executive decision

Omnix should implement Audiobook as a first-class native module rather than embedding Alexandria or running Alexandria as a second application.

Alexandria is a strong design and implementation reference for book ingestion, speaker annotation, voice casting, batching, selective regeneration, pause/timeline handling, and audiobook export. Omnix already owns the platform boundaries Alexandria would otherwise duplicate: provider selection, Qwen3-TTS, reusable voice profiles, jobs, assets, PostgreSQL persistence, eventing, model residency, the React application, and diagnostics.

The architecture therefore adopts Alexandria selectively while enforcing stronger Omnix invariants:

1. The original uploaded book is immutable.
2. Deterministic extraction creates a versioned canonical book revision.
3. Canonical chapter text is losslessly tiled by immutable spans.
4. LLMs classify and annotate spans; they never author or replace source prose.
5. Speaker identity is ID-based. Fuzzy matching may suggest an alias but must never silently merge speakers.
6. Long-running rendering uses PostgreSQL-backed leased workers, not `voice_inline.py`.
7. Individual renders are immutable and content-addressed by deterministic render keys.
8. Rendering is scheduled in resumable chapter/shard jobs rather than one platform Job per text span.
9. Realtime TTS always has higher priority than audiobook batch rendering.
10. Pronunciation/normalization is a separate auditable speech overlay and never mutates source text.
11. Chapter/master processing is separated from per-span generation.
12. Every export is reproducible from a frozen render/export manifest.

Audiobook should improve the common Omnix audio architecture rather than introduce a second bespoke TTS stack.

---

## 2. Goals

### V1 goals

V1 must support:

- PDF, DRM-free EPUB, DOCX, HTML, TXT, and Markdown ingestion.
- Immutable source asset retention and hashing.
- Deterministic canonical extraction with chapter structure.
- Exact canonical-text reconstruction from spans.
- Speaker/role/delivery annotation without source rewriting.
- Stable narrator and character identities.
- Existing Omnix voice-profile assignment.
- Human review of ambiguous/conflicting annotations.
- A pronunciation and text-normalization overlay.
- Durable asynchronous GPU TTS execution.
- Offline batch generation where the active provider supports it.
- Resumable chapter/shard rendering after process or machine interruption.
- Deterministic render caching and selective invalidation.
- Individual span preview/regeneration.
- Chapter assembly and mastering.
- M4B, FLAC, WAV, and MP3 export.
- Chapter metadata, cover art, author/title/language metadata, and timestamps.
- Integrity, provenance, and generation reports.
- A native React workspace at `/audiobook`.

### Explicit V1 non-goals

Do not block V1 on:

- Automatic VoiceDesign persona generation.
- LoRA voice training.
- Background music or ambience generation.
- DAW/Audacity multitrack export.
- DRM removal or DRM circumvention.
- Automatic fuzzy identity merging.
- Arbitrary source rewriting for dramatic adaptation.
- Migrating all existing Voice Studio and Podcast jobs to the new worker path before Audiobook works.

These can follow once the source-analysis/render pipeline is trustworthy.

---

## 3. Existing Omnix foundation to reuse

Current `main` already provides the important platform primitives:

- PostgreSQL-backed job authority with claims, leases, attempts, retries, progress, events, cancellation, and durable state.
- PostgreSQL-backed asset metadata plus `LocalBlobStore` for binary content.
- Qwen3-TTS provider and dedicated TTS service.
- Existing voice profiles and voice cloning.
- Multi-speaker Voice Studio and Podcast concepts.
- Provider registry/capability infrastructure.
- Model residency and worker/resource-class concepts.
- React feature workspaces, Jobs, Assets, Reports, diagnostics, and settings.

### Important architectural constraint

`src/app/jobs/voice_inline.py` currently marks Voice Studio jobs for inline execution and runs synthesis synchronously from job creation. Audiobook must not use this execution path.

Audiobook is the forcing function for a proper leased asynchronous GPU-TTS worker path.

---

## 4. Source fidelity contract

The fidelity boundary is the canonical extracted book, not the raw EPUB ZIP/XML byte stream.

### Required identity chain

    original source asset
            |
            v
    original_asset_hash
            |
            v
    deterministic extractor + extractor_version
            |
            v
    AudiobookSourceRevision
            |
            v
    canonical UTF-8 chapter text + chapter hashes
            |
            v
    immutable AudiobookSpan records

The original uploaded asset remains untouched.

Each canonical source revision records at minimum:

- original source asset ID and SHA-256
- source format
- extractor implementation/version
- extraction settings
- canonical revision ID
- ordered chapter IDs
- canonical chapter hashes
- extraction warnings
- metadata extraction provenance

### Hard invariant

For every chapter:

    concat(span.source_text in ordinal order) == canonical_chapter_text

Preserve all meaningful whitespace and paragraph boundaries required by the canonical representation.

The system must fail validation rather than silently accept gaps, overlaps, reordering, or duplicated canonical text.

### LLM isolation rule

An LLM response must never contain authoritative book prose.

The authoritative text for an annotation is always recovered by `span_id` / canonical offsets from Omnix persistence.

Malformed, truncated, refused, or unavailable LLM output may reduce annotation quality; it must never reduce source coverage.

---

## 5. Proposed domain model

Keep conceptual separation strong while avoiding unnecessary V1 schema explosion.

### Core V1 entities

#### AudiobookProject

Owns the audiobook workspace.

Suggested fields:

- `project_id`
- title
- author
- language
- cover asset ID
- current source revision ID
- current project state
- settings revision
- created/updated timestamps

#### AudiobookSourceRevision

Immutable result of one deterministic extraction configuration.

- `source_revision_id`
- `project_id`
- original asset ID/hash
- extractor version
- extraction settings hash
- canonical revision hash
- metadata JSON
- warnings JSON
- created timestamp

#### AudiobookChapter

- `chapter_id`
- source revision ID
- ordinal
- title
- canonical text storage reference
- canonical text hash
- structural metadata

#### AudiobookSpan

Immutable text partition.

- `span_id`
- chapter ID
- ordinal
- canonical start/end offsets
- exact source text or canonical storage reference
- source span hash
- structural kind
- tokenizer/detector provenance

Annotations must never mutate these fields.

#### AudiobookSpeaker

Stable identity.

- `speaker_id` UUID
- project ID
- canonical name
- display name
- speaker kind, e.g. narrator/character/unknown
- status

Names are presentation metadata, not identity keys.

#### AudiobookSpeakerAlias

- alias
- `speaker_id`
- provenance
- proposed/confirmed status
- confirmed_by_user
- created timestamp

Fuzzy or semantic matching may create proposed aliases only.

#### AudiobookCasting

Versioned mapping between a speaker and an Omnix voice/profile.

- casting revision
- speaker ID
- voice asset/profile ID
- voice revision/reference hash
- style defaults
- language overrides
- user confirmation/provenance

#### AudiobookAnnotation

Interpretation of a source span.

- annotation revision
- span ID
- role: narration/dialogue/heading/etc.
- selected speaker ID or unresolved candidate
- delivery instruction
- classifier/model provenance
- deterministic evidence JSON
- retry/disagreement JSON
- review status

#### AudiobookReviewIssue

Tracks actionable uncertainty rather than relying on raw model confidence.

Example states/reasons:

- `CONFIDENT`
- `AMBIGUOUS`
- `CONFLICT`
- `UNSUPPORTED_SPEAKER`
- `ATTRIBUTION_CONTRADICTION`
- `STRUCTURE_UNCERTAIN`
- `FALLBACK_NARRATOR`
- `USER_RESOLVED`

#### AudiobookRender

Immutable span-level generated audio.

- render ID
- span ID
- annotation revision
- casting revision
- speech-plan revision/hash
- render key
- model/provider identity and revision
- generation settings
- seed
- immutable audio asset ID
- duration/sample rate
- quality/diagnostic metadata
- status

#### AudiobookRenderBatch

Checkpoint/progress record for a scheduled render shard.

- batch ID
- chapter ID
- job ID
- shard ordinal/range
- desired render keys
- completed render keys
- failure/retry state
- timestamps

#### AudiobookExport

- export ID
- project/revision IDs
- format
- manifest hash
- immutable output asset ID
- chapter map
- metadata
- encoder settings
- created timestamp

### Structured JSON embedded initially

The following do not require separate V1 tables unless querying/version behavior demands it:

- annotation evidence
- pronunciation/speech plan
- export manifest
- integrity report

They must still be versioned and hashed.

---

## 6. Project state machine

The project has an explicit state machine independent of individual job state:

    IMPORTED
      -> EXTRACTED
      -> ANALYZING
      -> REVIEW_REQUIRED
      -> READY_TO_RENDER
      -> RENDERING
      -> RENDERED
      -> MASTERING
      -> READY_TO_EXPORT
      -> EXPORTED

Allow transitions back to earlier effective states when a dependency changes.

Examples:

- changing cover art: invalidate export only
- changing chapter metadata: invalidate affected export/master metadata only
- changing a speaker alias: invalidate dependent interpretation/casting decisions as required
- changing a character voice: invalidate only renders using that speaker/casting revision
- changing pronunciation rules: invalidate only renders whose speech plan changes
- changing model/generation parameters: create new render keys
- changing canonical extraction: invalidate every downstream object tied to the old source revision

Do not implement this as ad hoc `status = pending` mutation. Dependency revisions must make invalidation deterministic and auditable.

---

## 7. Ingestion and canonical extraction

### Supported V1 inputs

- EPUB
- TXT
- Markdown

Reject unsupported/DRM-protected content clearly. Do not implement circumvention.

### EPUB rules

- retain original EPUB as immutable asset
- parse ordered spine/chapter content deterministically
- exclude non-reading structural content such as script/style/title boilerplate when appropriate
- preserve meaningful paragraph boundaries
- preserve source ordering
- preserve extracted metadata and cover separately
- record extraction warnings rather than silently discarding uncertain content

### Canonical representation

Canonical chapter text should be UTF-8 with explicit, documented normalization rules.

Any normalization that changes representation must be:

- deterministic
- versioned
- tested
- included in the source-revision hash

Do not mix TTS pronunciation normalization into canonical extraction.

---

## 8. Span detection and language support

Span creation is deterministic and source-preserving.

Define a pluggable detector contract, conceptually:

    SpanDetector
      - EnglishQuoteDetector
      - FrenchGuillemetDetector
      - CjkDialogueDetector
      - EmDashDialogueDetector
      - PlainNarrativeDetector

V1 can implement a smaller subset, but the API must not bake English-only quotation rules into the audiobook domain model.

Unsupported structures must degrade safely:

- keep 100% source coverage
- assign narration/fallback state
- create review issues when appropriate
- never discard text

The tokenizer/detector must be property-tested for:

- apostrophes versus quotation marks
- nested quotations
- single-quote conventions
- guillemets
- em-dash dialogue
- CJK quotation marks
- malformed/unbalanced punctuation
- chapter seams and paragraph seams

---

## 9. LLM annotation architecture

### Core rule

LLM = classifier/interpreter, never prose generator.

The model receives immutable span IDs and contextual text and returns labels such as:

    {
      "span_id": "...",
      "speaker": "...candidate...",
      "role": "dialogue",
      "delivery": "quiet, worried"
    }

Omnix reattaches authoritative source text by ID.

### Context

Each request may include:

- local preceding/following spans
- current chapter title/context
- established speaker roster
- aliases confirmed by user
- recent character usage
- deterministic attribution evidence

Keep the context bounded and reproducible.

### Speaker creation and matching

- Exact known identity references may resolve automatically.
- A new observed label may create a proposed speaker.
- Similarity matching can suggest aliases.
- No fuzzy similarity threshold may silently merge two speaker IDs.
- Relationship-like labels such as "NITA'S DAD" must not collapse into "NITA".

### Attribution evidence

Borrow the useful detection idea from Alexandria PR #82:

- inspect nearby deterministic attribution phrases where supported
- detect contradictions between assigned speaker and explicit local attribution
- targeted retry or review on contradiction
- never silently repair identity from one heuristic

### Review strategy

Do not use a generic whole-book second LLM review as the default.

Use targeted retries for:

- conflicting evidence
- unsupported speakers
- inconsistent identity
- malformed output
- ambiguous dialogue
- user-requested reanalysis

Prefer a larger local context window for targeted retry.

### Confidence

Do not treat a raw LLM self-score as a calibrated probability.

Review priority should combine:

- classifier output
- deterministic attribution evidence
- structural dialogue evidence
- roster support
- cross-chunk consistency
- disagreement across retries/models
- fallback conditions

Expose underlying reasons in the UI.

---

## 10. Pronunciation and speech-plan layer

Source text and TTS input are separate truths.

Example:

    source_text:
      "Dr. Smith paid $4.95."

    tts_input:
      "Doctor Smith paid four dollars and ninety-five cents."

The canonical source remains unchanged.

A versioned speech plan may contain:

- pronunciation dictionary substitutions
- names and fictional terminology
- acronym handling
- date/number/currency normalization
- Roman numerals
- language-switch hints
- optional phoneme/IPA hints where supported
- user overrides
- normalization implementation/version

### Required auditability

For each rendered span, Omnix must be able to show:

- exact source text
- transformed TTS input text
- transformations applied
- transformation revision/hash

A speech-plan change participates in cache invalidation.

---

## 11. TTS provider capability expansion

Do not model audiobook rendering as only a boolean `offline_batch` option.

Expand provider capabilities to support concepts such as:

- `REAL_TIME`
- `STREAMING`
- `VOICE_CLONING`
- `MULTILINGUAL`
- `OFFLINE_BATCH`
- `CUSTOM_VOICE`
- `VOICE_DESIGN`
- `LORA_VOICE`

Add an actual provider-level batch contract where supported, conceptually:

    generate(...)
    generate_stream(...)
    generate_batch(...)

### Alexandria donor ideas to benchmark/adapt

- sort batches by text length
- sub-batch highly different lengths
- VRAM-aware batch sizing
- reusable voice-clone prompt caching
- model warmup
- optional codec compilation
- reproducible seeds
- model unload/switch policy

Do not assume Alexandria throughput numbers transfer directly to Omnix's FasterQwen implementation.

### Required RTX 4090 benchmark shapes

Benchmark at least:

1. short homogeneous dialogue
2. long narrator passages
3. mixed-length, mixed-speaker turns

Capture:

- real-time factor
- items/batch
- free/peak VRAM
- warmup/compile cost
- failure rate
- audio consistency
- throughput versus batch length distribution

Use measured data to choose default batching policy.

---

## 12. Asynchronous GPU-TTS worker path

Audiobook must not execute via `voice_inline.py`.

### Required worker behavior

- claim PostgreSQL job by resource class
- hold/renew lease
- mark running
- report durable progress
- checkpoint completed render keys
- honor cancellation
- fail with retryability classification
- release/expire cleanly on process death
- resume from persisted work after reclaim

### Resource classes / priority

At minimum establish:

    gpu:tts:realtime    HIGH
    gpu:tts:preview     MEDIUM
    gpu:tts:offline     LOW

Audiobook uses offline class for bulk rendering and preview class for explicit user previews.

### Cooperative GPU scheduling

Do not attempt CUDA-kernel preemption.

Offline rendering yields between batches:

1. finish current batch atomically
2. persist render outputs/checkpoint
3. check for higher-priority realtime/preview work
4. stop claiming offline batches while priority work is pending
5. resume afterward

Integrate with model residency rather than loading an independent Alexandria TTS server/model copy.

---

## 13. Job topology and durable sharding

Do not create one platform Job per span.

Use coarse durable orchestration jobs plus persistent span render records.

Suggested job types:

- `audiobook.ingest`
- `audiobook.analyze`
- `audiobook.render-chapter` or `audiobook.render-shard`
- `audiobook.assemble-chapter`
- `audiobook.master`
- `audiobook.export`

A render chapter job may internally use shards:

    Chapter 12
      shard 001: spans 0-39
      shard 002: spans 40-79
      shard 003: spans 80-121

Each generated render is persisted immediately or at a bounded transactional checkpoint.

On retry/reclaim:

- recompute desired render keys
- query completed immutable renders
- skip valid cache hits
- synthesize only missing keys

A process killed after 83/121 spans must restart near span 84 rather than replay the whole chapter.

---

## 14. Deterministic render identity

Every render must have an explicit deterministic key.

Conceptually:

    render_key = SHA256(
        source_span_hash
      + annotation_revision
      + speaker_id
      + casting_revision
      + voice_revision
      + reference_audio_hash
      + provider_id
      + model_id
      + model_revision
      + language
      + delivery_instruction
      + speech_plan_hash
      + generation_parameters
      + seed
    )

Canonical serialization rules must be defined so the same logical request produces the same key.

### Cache rule

If a valid immutable render already exists for `render_key`, do not synthesize it again.

### Asset rule

Never repeatedly overwrite a fixed asset such as:

    audio:chapter-3-span-142

Current asset upsert compatibility updates metadata/revision for an existing asset ID without replacing the underlying blob. Audiobook must therefore create immutable/versioned audio asset IDs keyed by the render identity or render record.

Metadata and blob content must never become mismatched.

---

## 15. Dependency invalidation matrix

Implement and test explicit invalidation behavior.

| Change | Re-analyze | Re-render | Re-master | Re-export |
|---|---:|---:|---:|---:|
| Cover image | No | No | No | Yes |
| Book title/author metadata | No | No | No | Yes |
| Canonical source revision | Yes | Yes | Yes | Yes |
| Span speaker annotation | Affected spans | Affected spans | Affected chapters | Yes |
| Confirmed alias | Affected interpretation | If casting changes | Affected chapters | Yes |
| Voice/casting revision | No | Affected speaker spans | Affected chapters | Yes |
| Delivery instruction | No | Affected spans | Affected chapters | Yes |
| Pronunciation/speech plan | No | Affected spans | Affected chapters | Yes |
| TTS model/settings/seed | No | Affected key space | Affected chapters | Yes |
| Pause policy | No | No | Affected chapters | Yes |
| Mastering settings | No | No | Yes | Yes |
| Export metadata/codec | No | No | No | Yes |

Invalidation creates new derived revisions. It does not destroy old immutable render evidence.

---

## 16. Audio assembly and mastering

### Intermediate format

Prefer lossless intermediate audio:

- WAV/PCM or FLAC per render
- no lossy encode per span

### Pause policy

Do not music-style crossfade every spoken segment.

Assemble spoken audio using explicit pause rules, for example:

- same-speaker continuation pause
- speaker-change pause
- paragraph pause
- chapter/title pause
- per-span override

Keep timing policy versioned and part of chapter assembly identity.

### Loudness

Do not independently peak-normalize every sentence.

Pipeline:

    immutable rendered speech
       + pause/timeline assembly
       + chapter-level loudness processing
       + optional final-book mastering
       + final encode

Store mastering settings and measurements in metadata.

---

## 17. Export and reproducibility

### V1 formats

- M4B
- FLAC
- WAV
- MP3

### M4B requirements

Support from day one:

- title
- author
- cover
- language
- narrator/cast metadata where practical
- ordered chapter titles
- chapter timestamps
- encoder settings
- source/render provenance

### Frozen export manifest

Every export must reference an immutable manifest containing at minimum:

- project ID
- source revision ID/hash
- annotation revision(s)
- casting revision(s)
- ordered chapter revisions
- ordered render IDs/render keys
- pause/assembly revision
- mastering revision
- export metadata
- encoder/version/settings

Six months later Omnix should be able to explain exactly which inputs generated a given M4B.

---

## 18. Native Audiobook workspace — approved UI direction

Create a first-class `/audiobook` workspace that visually belongs to Omnix and follows the approved Audiobook mockup direction.

This is **not** a request to clone Alexandria's UI. Alexandria is a workflow/reference donor. The Omnix implementation must use the existing Omnix application shell, Aurora/Liquid Glass visual language, shared components, spacing, typography, provider controls, Jobs/Assets infrastructure, and responsive behavior.

### 18.1 Codex implementation references in current Omnix

The closest existing visual/layout reference is Storyteller:

- `src/apps/web/src/features/storyteller/StorytellerWorkspace.tsx`
- `src/apps/web/src/features/storyteller/StorytellerWorkspace.css`
- `src/apps/web/src/features/storyteller/StorytellerSidebar.css`
- `src/apps/web/src/features/storyteller/StoryMode.css`

Audiobook should reuse the same overall three-column desktop grammar instead of inventing a second shell:

    [ sticky library ] [ flexible primary stage / editor ] [ sticky chapter outline ]

Current Storyteller uses approximately:

    grid-template-columns: 14.5rem minmax(0, 1fr) 15.25rem

Audiobook may widen the center/right production area when useful, but should preserve the same responsive design vocabulary and shared app-shell behavior.

Codex must also integrate the module through the existing module registry and workspace router rather than hard-coding a standalone page:

- `src/apps/web/src/app/modules.ts`
  - add `audiobook` to `OmnixModuleId`
  - add `/audiobook` to `OmnixModuleRoute`
  - add the Audiobook module definition
- `src/apps/web/src/features/ModuleWorkspace.tsx`
  - import and route to `AudiobookWorkspace`
  - register capability labels
- `src/apps/web/src/main.tsx`
  - import Audiobook workspace styles only as needed by the current app pattern
- implementation target:
  - `src/apps/web/src/features/audiobook/AudiobookWorkspace.tsx`
  - colocated components/hooks/types/tests/styles under `features/audiobook/`

Do not fork the entire Storyteller component. Reuse shared primitives and extract common presentational primitives only when that improves both modules without coupling their domain state.

### 18.2 Top navigation and app-shell behavior

Audiobook is a top-level creative workspace.

The desktop creative navigation should include an `Audiobook` item alongside the existing major workspaces, visually consistent with:

    Chat | RPG | Storyteller | Audiobook | Podcast | Voice Studio | Image Generation | Trading

Exact ordering may follow the current central navigation constraints, but Audiobook must be directly discoverable rather than hidden under Storyteller or Voice Studio.

When active:

- the Audiobook navigation item uses the current active cyan/purple Aurora treatment
- the right-side workspace badge reads `AUDIOBOOK`
- `LOCAL-FIRST` and global appearance/provider controls remain in the shared shell
- do not duplicate global provider/model controls inside the Audiobook header unless a project-level override is genuinely required

### 18.3 Approved desktop information architecture

The approved visual direction is:

    +----------------------------------------------------------------------------------+
    | Omnix shared app shell / top navigation                                          |
    +--------------------+--------------------------------------+----------------------+
    | LIBRARY            | AUDIOBOOK PROJECT                    | OUTLINE              |
    |                    |                                      |                      |
    | Projects           | cover  title / metadata / stats      | Chapter 1            |
    | Books              | [Save project] [Export M4B]          |   Scene/Span groups  |
    | Characters         |                                      | Chapter 2            |
    | Voices             | Cast & voice tools                   | ...                  |
    | Pronunciations     | Render & delivery tools              | [Add chapter]*       |
    | Exports            |                                      |                      |
    |                    | [Book & Review] [Production]         |                      |
    | RECENT BOOKS       |                                      |                      |
    | project cards      | manuscript / review editor           |                      |
    |                    |          + status / casting / render |                      |
    |                    |          + export                    |                      |
    +--------------------+--------------------------------------+----------------------+

`Add chapter` is only enabled for source types/workflows where authoring chapter structure is valid. For immutable imported EPUB structure, chapter edits must create a new canonical/project revision rather than silently mutating the imported source truth.

### 18.4 Left library rail

The left rail is the project/library navigation surface, visually derived from Storyteller's current sticky library.

Primary entries:

- **Projects** — audiobook project list
- **Books** — imported source books/source revisions
- **Characters** — canonical speaker roster across the active project
- **Voices** — reusable Omnix voice profiles/casting
- **Pronunciations** — project/user pronunciation dictionary
- **Exports** — completed export history and manifests

Below the primary navigation:

- **Drafts / incomplete projects**
- **Recent books**
- compact cover thumbnail
- project/book title
- last edited/rendered time
- progress or issue badge where useful

Requirements:

- sticky on desktop
- independently scrollable
- keyboard navigable
- selected item remains obvious in both dark and light themes
- no browser-local authority for project state; project list and progress come from backend persistence

### 18.5 Project header

The main-stage header should match the approved mockup concept:

- book cover thumbnail
- eyebrow: `AUDIOBOOK PROJECT`
- title
- short project/subtitle line
- genre/style tags when available
- project statistics
- primary actions

Recommended statistics:

- canonical word count
- chapter count
- speaker count
- estimated/actual runtime
- unresolved review issue count when non-zero

Primary actions:

- `Save project` when there are editable project settings awaiting persistence
- `Export M4B` as the prominent final-output action when the project is exportable
- if export is not ready, the action should communicate why rather than silently fail

Project readiness is derived from durable backend state.

### 18.6 Tool summary bars

Immediately beneath the project header, show two compact expandable summary bars consistent with the mockup.

#### Cast & voice tools

Summary text:

    Narrator, voices, aliases, pronunciations, auditions

Opening this surface should expose:

- narrator assignment
- canonical speaker roster
- aliases/proposed aliases
- voice assignment
- voice revision
- sample/audition playback
- default delivery style
- pronunciation entries scoped to a character/name where useful

#### Render & delivery tools

Summary text:

    Batch rendering, chapter mastering, export manifests

Opening this surface should expose:

- rendering provider/model
- batch capability/status
- pause policy
- mastering settings
- output format defaults
- retry/cache policy diagnostics
- export manifest/provenance summary

Use progressive disclosure. The default workspace should not become a wall of advanced settings.

### 18.7 Primary mode switch

The mockup's two large mode cards become the main workspace mode switch.

#### Book & Review Mode

Purpose:

- read the canonical manuscript
- inspect speaker annotations
- resolve review issues
- inspect effective TTS input
- audition/regenerate individual spans

#### Production Mode

Purpose:

- render audio
- monitor shards/batches
- inspect cache hits/failures
- assemble/master chapters
- manage final exports

The active mode gets the current Omnix cyan/purple selected treatment.

Mode switching must not create separate project state. It is two views of the same persisted project/revisions/jobs.

### 18.8 Book & Review Mode — manuscript editor

The manuscript/review surface is the center of the Audiobook UX.

Header example:

    CHAPTER 1  •  12 MIN READ
    The Lantern at Hollow Bay

Render canonical book text with speaker/role annotations as overlays, not by rewriting the source.

Recommended visual treatment:

- narration paragraphs: neutral manuscript typography
- dialogue: speaker-colored badge preceding or adjacent to the dialogue span
- narrator badge: purple/neutral
- each canonical speaker gets a stable project color token
- ambiguous/conflicted span: warning border/badge
- fallback narrator: visible but non-alarming informational treatment
- currently playing/render-preview span: clear focus/playback indication

Selecting a span opens contextual controls without changing the canonical source:

- speaker identity
- role
- delivery instruction
- exact source text, read-only
- effective TTS text
- pronunciation transformations
- evidence/review reason
- voice assignment
- preview
- regenerate
- accept/revert annotation
- mark resolved

Never use a rich-text editor that permits accidental mutation of imported canonical prose.

If V1 allows user-authored corrections to book text, they must explicitly create a new source/project revision and must not overwrite the existing canonical revision.

### 18.9 Right outline rail

The right rail remains sticky and chapter-oriented.

Display:

- ordered chapters
- optional scene/section/span-group children
- issue count per chapter
- render state per chapter
- active chapter/section

Selecting an outline item scrolls/navigates the main manuscript.

Useful compact chapter states:

- not analyzed
- review required
- ready
- rendering
- partially rendered
- rendered
- mastered
- export-ready
- failed

Do not derive these only from frontend state.

### 18.10 Project Status card

In Book & Review Mode, the secondary information column should include a compact **Project Status** card.

Recommended fields:

- canonical source: `Up to date` / stale / changed
- review issues: count
- cache hits: percentage or count
- rendered coverage
- estimated runtime
- integrity result

Each status should link to the relevant detail/review surface when actionable.

### 18.11 Voice Casting card

Show the active cast compactly:

    Narrator        Alloy    [play] [...]
    Evelyn Hart    Nova     [play] [...]
    Stationmaster  Onyx     [play] [...]
    Child          Lumen    [play] [...]

The displayed names are UI labels. The application must operate on immutable `speaker_id` and versioned casting IDs internally.

Actions:

- manage voices
- audition
- replace casting
- inspect voice provenance/revision
- locate all spans using speaker

Changing casting must trigger the dependency invalidation rules defined elsewhere in this roadmap.

### 18.12 Render Progress card

The Production view should prominently expose durable render progress.

Example:

    Render progress
    83 / 121 render units complete

    Chapter 1  ████████████████████ 100%
    Chapter 2  ██████████████------  68%
    Chapter 3  ███-----------------  12%

Also expose:

- generated
- cache hit
- queued
- running
- retrying
- failed
- canceled

Primary action:

- `Open render queue`

This should navigate to Audiobook-specific render detail or the shared Jobs surface with an Audiobook filter; do not build a second unrelated job authority.

Progress is read from persisted render batches/renders/jobs and survives reload/reconnect.

### 18.13 Export card

Provide a compact export card in Production Mode.

Quick format choices:

- M4B
- FLAC
- WAV
- MP3

M4B should be the default/recommended audiobook format when its prerequisites are satisfied.

Include:

- `Advanced export settings`
- chapter/metadata readiness
- cover readiness
- final manifest status
- output history

Clicking export creates a durable backend export job and freezes the export manifest used by that job.

### 18.14 Empty, importing, analyzing, and error states

Codex must implement complete states rather than only the populated mockup.

#### Empty workspace

Show:

- import book CTA
- accepted formats
- create project flow
- link to existing voice profiles
- concise explanation of local-first processing

#### Importing/extracting

Show deterministic pipeline stages:

    Upload source
    Validate format
    Extract canonical chapters
    Build lossless spans
    Verify integrity

#### Analyzing

Show:

    Detect structure
    Classify narration/dialogue
    Build/propose speaker roster
    Check attribution conflicts
    Prepare review queue

#### Review required

Surface count and jump directly to unresolved issues.

#### Rendering

Show durable job progress and allow safe cancel/pause semantics supported by backend contracts.

#### Failure

Show:

- failed stage
- durable error code/message
- retryability
- affected chapter/shard
- retry action
- diagnostics link

Failure must never imply canonical-source loss.

### 18.15 Responsive behavior

Desktop is the primary production experience, but the workspace must degrade deliberately.

Suggested breakpoints:

- wide desktop: three columns
- medium/tablet: collapse right outline into drawer; keep library + stage
- narrow/mobile: stage-first; library and outline become drawers/sheets

Never make the manuscript/editor unusably narrow just to preserve all three rails.

Render progress, review queue, and export status must remain accessible on smaller screens.

### 18.16 Theme and accessibility requirements

The Audiobook workspace must work in all currently supported Omnix appearance modes.

Requirements:

- no dark-theme-only hardcoded text colors
- selected/inactive speaker badges maintain contrast
- review warnings are not color-only
- keyboard focus visible
- all icon-only actions have accessible names/tooltips
- progress bars expose textual percentages/status
- manuscript text remains readable at browser zoom
- sticky rails do not trap keyboard or screen-reader navigation
- playback controls expose state
- reduced-motion preference respected for animated progress/glow effects

Use current design tokens/primitives where they exist. Do not introduce a disconnected design system.

### 18.17 Frontend data/state contract

Use TanStack Query/current Omnix API patterns for server authority.

Frontend-local state may contain only ephemeral UI concerns such as:

- selected chapter/span
- open/closed drawer
- active workspace mode
- local filter/sort
- temporary form edits before save

Backend-authoritative state includes:

- project/source revisions
- canonical chapters/spans
- annotations
- speakers/aliases
- casting
- review decisions
- pronunciation/speech plans
- render records/batches
- job progress
- export manifests/assets

Do not use localStorage as authority for Audiobook projects, canonical text, render progress, or review completion.

### 18.18 UI component decomposition

A reasonable initial component tree:

    AudiobookWorkspace
      AudiobookLibraryRail
      AudiobookStage
        AudiobookProjectHeader
        AudiobookToolBars
        AudiobookModeSwitch
        BookReviewWorkspace
          AudiobookManuscript
          AudiobookSpan
          AudiobookProjectStatusCard
          AudiobookCastingCard
        ProductionWorkspace
          AudiobookRenderProgress
          AudiobookRenderQueue
          AudiobookMasteringCard
          AudiobookExportCard
      AudiobookOutlineRail
      AudiobookSpanInspector / drawer
      AudiobookReviewQueue / drawer
      AudiobookToolDrawer

Do not force this exact decomposition if current shared components make a cleaner implementation, but preserve the information architecture and responsibility boundaries.

### 18.19 UI acceptance criteria

Before calling the Audiobook UI complete:

1. `/audiobook` is registered as a real Omnix module and top-level workspace.
2. The populated desktop workspace matches the approved mockup's information hierarchy and Omnix visual language.
3. Left library and right outline are independently useful and sticky on desktop.
4. Book & Review and Production are first-class modes over one persisted project.
5. Canonical source is visibly read-only; annotations are overlays.
6. Review conflicts can be located and resolved without scanning the whole book.
7. Voice casting is inspectable and auditionable.
8. Render progress survives reload and accurately reflects backend persisted state.
9. Cache hits, retries, and failures are distinguishable.
10. Export creates a durable job and frozen manifest.
11. Empty/loading/analyzing/review/error states are implemented.
12. Responsive layouts remain usable.
13. Dark/light/Aurora modes remain readable.
14. Keyboard and accessible-name basics are covered by tests.
15. Frontend tests prove that project/render state is not browser-local authority.

---

## 19. API/service boundaries

Prefer domain services rather than placing audiobook logic directly in route handlers.

Suggested backend modules:

    app/audiobook/
      models.py
      repository.py
      service.py
      extraction.py
      spans/
      annotation.py
      speakers.py
      speech_plan.py
      render_keys.py
      render_service.py
      assembly.py
      export.py
      integrity.py
      routes.py

Worker-side execution should call the same domain services and repositories used by API orchestration.

The web application should live under a dedicated feature folder, conceptually:

    src/apps/web/src/features/audiobook/

Reuse existing Jobs/Assets/Provider UI components where possible.

---

## 20. Observability and diagnostics

Record enough evidence to diagnose a bad 15-hour render without replaying it blindly.

### Project metrics

- chapters/spans
- source coverage
- unresolved review issues
- speakers/cast coverage
- render count
- cache hit rate
- retry count
- failed render keys
- total rendered duration
- total generation wall time
- real-time factor
- peak VRAM
- mastering/export time

### Per-batch diagnostics

- provider/model/revision
- batch composition/length distribution
- batch size
- VRAM before/after/peak
- latency
- generated duration
- compile/warmup state
- failure category
- lease/job IDs
- render keys

### Integrity report

Produce an artifact/report containing:

- original source asset hash
- canonical revision hash
- per-chapter canonical hashes
- exact source-coverage result
- fallback/ambiguous annotation counts
- render/cache summary
- export manifest hash

---

## 21. Implementation phases

### Phase 0 — Contracts and schema foundation

Deliver:

- audiobook domain package skeleton
- DB migrations/repositories
- project state model
- source revision/chapter/span schema
- speaker/casting/annotation schema
- render/batch/export schema
- canonical hashing helpers
- deterministic render-key serializer
- dependency invalidation contract
- asset-ID/versioning conventions

Acceptance:

- repositories are PostgreSQL authoritative
- immutable entities cannot be silently overwritten
- render key stable across process runs
- invalidation matrix unit-tested

### Phase 1 — Canonical ingestion and integrity

Deliver:

- EPUB/TXT/MD ingestion
- immutable source asset
- deterministic extraction
- chapter detection
- canonical revision creation
- span detector interface
- initial English/plain detectors
- exact reconstruction validator
- integrity report

Acceptance:

- 100% canonical source reconstruction
- no dropped/reordered chapter text
- malformed source fails safely
- repeat extraction with same version/settings produces same hashes

### Phase 2 — Annotation, speaker identity, and review

Deliver:

- classifier-only LLM contract
- bounded context builder
- structured-output validation
- stable speaker UUIDs
- proposed versus confirmed aliases
- deterministic attribution checks
- targeted retry
- review status/evidence
- narrator fallback preserving all text

Acceptance:

- LLM cannot alter source text by construction
- malformed/refused/truncated output preserves 100% source coverage
- near-identical speaker names never auto-merge
- contradictions surface in review queue

### Phase 3 — Speech-plan / pronunciation layer

Deliver:

- normalization pipeline
- pronunciation dictionary
- user override mechanism
- speech-plan version/hash
- source-to-TTS diff/audit view
- render-key integration

Acceptance:

- source remains unchanged
- plan is deterministic
- changing pronunciation invalidates only affected renders

### Phase 4 — Proper asynchronous GPU TTS worker

Deliver:

- leased GPU-TTS worker
- `gpu:tts:realtime` / `preview` / `offline` resource policy
- lease renewal/progress/cancel/retry
- provider batch capability
- FasterQwen batch benchmark
- cooperative offline yielding
- model-residency integration

Acceptance:

- audiobook jobs never execute synchronously in `create_job()`
- worker death causes lease recovery
- realtime requests can take priority between offline batches
- no second independent TTS service/model stack

### Phase 5 — Durable rendering, cache, and resume

Deliver:

- chapter/shard planner
- immutable `AudiobookRender`
- immutable versioned audio asset IDs
- render-key lookup/cache
- atomic bounded checkpoints
- selective regeneration
- crash/restart recovery

Acceptance:

- kill worker mid-chapter and resume without rerendering completed keys
- same render key produces cache hit
- voice/model/pronunciation changes produce new keys
- stale asset metadata/blob mismatch is impossible

### Phase 6 — Assembly, mastering, and export

Deliver:

- pause/timeline engine
- chapter assembly
- chapter-level loudness
- optional final mastering
- M4B/FLAC/WAV/MP3
- cover/metadata/chapter markers
- frozen export manifest

Acceptance:

- chapter timestamps accurate
- lossless intermediate path
- export reproducible from manifest
- changing export-only metadata does not rerender TTS

### Phase 7 — Audiobook React workspace

Deliver:

- Book
- Script/Analysis
- Cast
- Review
- Production
- Editor
- Export

Acceptance:

- every long action represented by durable backend job/state
- reconnect/reload restores project state
- review reasons visible
- segment preview/regeneration works
- production progress reflects persisted work, not browser-local state

### Phase 8 — Hardening and production validation

Deliver:

- public-domain golden-book fixture
- long-book endurance test
- fault injection
- GPU contention tests
- multilingual detector fixtures
- migration/backup tests
- performance report
- operator documentation

Acceptance:

- all invariants below pass
- full golden audiobook completes after induced restarts
- realtime voice remains usable during offline production
- integrity/export reports generated

---

## 22. Mandatory test matrix

This feature requires property/invariant tests, not only happy-path API tests.

### Source integrity

- canonical chapter reconstruction exactly equals canonical text
- zero gaps/overlaps
- paragraph/chapter seam preservation
- duplicate/reordered span rejection
- deterministic source hashes

### Typography/language

- ASCII double quotes
- curly double quotes
- apostrophes
- single-quote dialogue
- nested quotes
- guillemets
- em-dash dialogue
- CJK quote marks
- malformed/unbalanced quote marks
- unsupported convention safe fallback

### Speaker identity

- same surname/different people
- near-identical names
- possessive relationships
- titles/honorifics
- age variants
- alias cycles
- proposed alias requires confirmation when non-exact

### LLM failure

- invalid JSON
- missing fields
- truncated output
- refusal
- timeout
- provider unavailable
- contradictory retry results

Every case must retain 100% canonical source coverage.

### Render/cache

- identical request = same render key
- any material voice/model/text-plan setting change = new key
- changing unrelated metadata does not change key
- cache hit skips TTS
- corrupted/missing blob does not count as valid cache hit
- immutable asset IDs prevent stale blob reuse

### Recovery

- process death before first checkpoint
- death halfway through shard
- lease expiration
- retryable provider failure
- non-retryable bad input
- user cancellation
- application restart
- DB reconnect

Completed renders must not be regenerated unnecessarily.

### GPU priority

- offline batch active, realtime request arrives
- offline completes current batch then yields
- realtime completes
- offline resumes
- model switch/residency state remains coherent

### Audio

- mixed speaker pause behavior
- same speaker pause behavior
- chapter boundary timing
- no mandatory crossfade
- chapter loudness target
- lossless intermediate validation
- output duration/timestamps

### Export

- M4B chapter metadata
- cover/title/author/language
- manifest references exact render set
- export-only change avoids TTS
- reproducibility from frozen manifest

---

## 23. Golden public-domain validation

Maintain at least one public-domain whole-book fixture suitable for automated/endurance use.

Freeze:

- source hash
- extractor version
- canonical revision hash
- chapter count
- canonical coverage
- known typography cases

Do not freeze exact TTS waveforms as the only golden signal if GPU/library nondeterminism makes that brittle.

Instead validate:

- render identity
- completion
- structural timings within tolerance
- audio validity
- manifest correctness
- no missing spans
- restart behavior

---

## 24. Alexandria code-donor policy

**Reference repository (full URL): https://github.com/Finrandojin/alexandria-audiobook**

**Source-fidelity/speaker-attribution reference PR: https://github.com/Finrandojin/alexandria-audiobook/pull/82**

Codex should inspect the reference repository when implementing the donor areas below, while preserving Omnix's own architecture and contracts.

Alexandria is MIT licensed and may be used as a code/design donor.

Before directly copying substantial code:

- identify the source file/commit
- retain the required MIT copyright/license notice
- document adaptation in Omnix third-party notices as appropriate
- port logic behind Omnix provider/job/asset contracts rather than preserving Alexandria's app boundaries

High-value donor areas:

- chapter/book parsing techniques
- length-aware batch/sub-batch algorithms
- VRAM estimation ideas
- clone-prompt caching
- speaker alias UX concepts
- pause/timeline assembly
- selective regeneration concepts
- M4B chapter/export mechanics

Do not import as runtime dependencies:

- Alexandria FastAPI application
- Alexandria web UI
- JSON-file project authority
- its standalone task polling system
- independent TTS model manager/server
- prompt-driven source rewriting path

Use Alexandria PR #82 as a research reference for source-fidelity and speaker-attribution failure modes, not as an unquestioned implementation dependency.

---

## 25. Post-V1 roadmap

After V1 reliability is proven:

### V1.1 — Automatic cast/persona assistance

- persona suggestions
- automatic voice candidates
- VoiceDesign where supported
- audition grid
- user-confirmed casting

### V1.2 — Advanced voice production

- CustomVoice support
- LoRA voice support
- voice age/style variants
- reusable cast libraries
- richer delivery direction

### V1.3 — Production/export tooling

- Audacity/DAW stems
- per-speaker tracks
- chapter packages
- alternate editions
- advanced mastering presets
- pronunciation editor/library

### V1.4 — Shared audio architecture migration

Once the leased GPU-TTS path is stable:

- migrate long Voice Studio synthesis away from inline execution
- migrate Podcast bulk generation to the shared worker
- keep realtime/live voice on its optimized fast path
- consolidate provider capability and residency behavior

Audiobook should leave Omnix with a better shared audio execution architecture than it started with.

---

## 26. Definition of done for V1

V1 is production-ready only when all of the following are true:

1. A DRM-free public-domain EPUB can be imported and deterministically canonicalized.
2. Every canonical chapter reconstructs exactly from its spans.
3. LLM failure cannot remove or rewrite source text.
4. Speaker IDs remain stable and fuzzy matching never silently merges identities.
5. Review issues expose evidence rather than an unexplained model confidence number.
6. A user can assign existing Omnix voices to narrator and characters.
7. Pronunciation normalization is auditable and source-preserving.
8. Bulk rendering runs through leased asynchronous GPU workers, not `voice_inline.py`.
9. Offline audiobook work yields to realtime/preview TTS between batches.
10. Killing the worker/application mid-book resumes from durable checkpoints.
11. Completed matching render keys are not regenerated.
12. Changing one character voice invalidates only that character's dependent renders and downstream chapter/export artifacts.
13. Render audio assets are immutable/versioned and cannot suffer metadata/blob drift.
14. Chapters are assembled with explicit pause policy and chapter-level mastering.
15. M4B, FLAC, WAV, and MP3 exports work from a frozen manifest.
16. M4B includes chapter structure and core metadata.
17. The UI survives browser reload/reconnection without losing production state.
18. Integrity/provenance reports explain exactly what source, annotations, voices, models, renders, and export settings produced the final book.
19. Required unit/property/integration/endurance tests pass.
20. A complete golden-book render succeeds despite injected process restarts.

---

## 27. Final implementation sequence

The recommended coding order is:

    1. schema + immutable contracts
    2. canonical ingestion
    3. lossless spans + integrity
    4. classifier-only annotation
    5. speaker IDs + review evidence
    6. speech-plan/pronunciation layer
    7. leased asynchronous TTS worker
    8. provider offline-batch capability + benchmark
    9. deterministic render keys + immutable render assets
    10. chapter/shard resume
    11. assembly/mastering
    12. export manifests + M4B/FLAC/WAV/MP3
    13. native /audiobook workspace
    14. whole-book fault/endurance validation
    15. automatic persona/VoiceDesign enhancements
    16. migrate other long-form Omnix audio workflows onto the shared worker

This sequence deliberately solves correctness and recoverability before adding automatic casting sophistication.

The architectural north star remains:

    WHAT THE AUTHOR WROTE
             |
             v
    HOW OMNIX INTERPRETED IT
             |
             v
    HOW OMNIX PERFORMED IT

Those three layers must remain separately versioned, inspectable, and reproducible.
