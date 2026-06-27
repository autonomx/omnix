# Storyteller Audio + Voice Cast Roadmap

## Goal

Make Storyteller audio generation reliable by moving voice assignment from post-hoc text parsing to a structured story-generation contract. Story generation should produce the visible prose plus durable metadata for cast members, narration blocks, dialogue blocks, speaker identity, and chapter order. Audio generation should consume that metadata directly so character voices are deterministic, editable, and reusable across full-story and chapter-level narration.

## Current state

- Storyteller can generate, save, and export story text.
- Storyteller has a working full-story audio panel that can queue Voice Studio TTS jobs, stream returned audio into a player, and enable download when playable output is available.
- The current Storyteller audio panel extracts text from the rendered manuscript and sends chapter-aware segments to Voice Studio.
- Voice Studio stores cloned voices as `voice_profile` assets and can synthesize speech from selected voice ids/storage paths.
- Character-to-voice mapping is not yet reliable because audio generation does not have authoritative dialogue speaker metadata.

## Guiding principle

The Storyteller runtime must not guess speakers from finished prose when it can know speakers at generation time.

The reliable source of truth should be:

```text
structured story blocks -> speakerId -> saved voice cast -> Voice Studio script segments
```

The LLM may propose cast and speaker metadata, but deterministic validation, saved character ids, and user-confirmed voice assignments control the final audio mapping.

## Target architecture

### Story document model

Add a structured story document beside the rendered manuscript text.

```ts
type StoryDocument = {
  id: string;
  title: string;
  premise: string;
  chapters: StoryChapter[];
  cast: StoryCharacter[];
  voiceCast: StoryVoiceAssignment[];
  audioManifests: StoryAudioManifest[];
  updatedAt: string;
};
```

### Chapter model

```ts
type StoryChapter = {
  id: string;
  index: number;
  title: string;
  summary?: string;
  blocks: StoryBlock[];
  textFingerprint: string;
};
```

### Block model

```ts
type StoryBlock =
  | {
      id: string;
      kind: 'narration';
      chapterId: string;
      text: string;
      speakerId: 'narrator';
      order: number;
    }
  | {
      id: string;
      kind: 'dialogue';
      chapterId: string;
      text: string;
      speakerId: string;
      speakerName: string;
      order: number;
      confidence: number;
      attributionEvidence?: string;
    };
```

### Character model

```ts
type StoryCharacter = {
  id: string;
  displayName: string;
  aliases: string[];
  role: 'narrator' | 'protagonist' | 'supporting' | 'minor';
  description?: string;
  traits?: string[];
  iconAssetId?: string;
  detectedFrom: 'outline' | 'generation' | 'manual';
  confidence: number;
};
```

### Voice cast model

```ts
type StoryVoiceAssignment = {
  characterId: string;
  voiceId: string;
  voiceLabel: string;
  style?: string;
  fallbackVoiceId?: string;
  updatedAt: string;
};
```

### Audio manifest model

```ts
type StoryAudioManifest = {
  id: string;
  storyId: string;
  scope: 'chapter' | 'selected_chapters' | 'full_story';
  chapterIds: string[];
  sourceFingerprint: string;
  voiceCastFingerprint: string;
  jobId?: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'stale';
  audioUrl?: string;
  downloadFilename?: string;
  durationSeconds?: number;
  createdAt: string;
  updatedAt: string;
};
```

## Phase 1 — Native React Story Audio Panel

Replace the current DOM enhancer with a first-class React implementation.

### Work

- Add `StoryAudioPanel.tsx`.
- Move text extraction, cloned voice loading, job creation, polling, player state, and download state into React state/React Query.
- Use `omnixApiClient` instead of direct `fetch` calls where supported.
- Keep current user-facing capabilities: cloned voice select, generate full-story audio, progress, player, download.
- Remove MutationObserver-based Storyteller audio injection once parity is reached.

### Acceptance criteria

- The cloned voice dropdown remains stable while opened.
- Generate button reliably queues a Voice Studio job.
- Audio player is not recreated during normal progress updates.
- Download button enables only after playable audio is available.
- Tests cover dropdown stability, generate click, completed job, failed job, and download enablement.

## Phase 2 — Story Cast Registry

Introduce a persistent cast registry for each Storyteller project.

### Work

- Add a cast model with stable character ids, display names, aliases, roles, and descriptions.
- Seed `Narrator` as a required cast member.
- Detect initial cast from story title, premise, outline, and generated prose.
- Allow manual add/edit/remove of cast members.
- Save cast registry with the story/project, falling back to local storage until backend persistence is available.

### Acceptance criteria

- Every story has a `Narrator` character.
- Named recurring characters are listed in a cast panel.
- Users can add aliases such as `the cat`, `Barnaby`, or `smoky-caramel cat`.
- Character ids remain stable when display names change.
- Cast state survives page reload.

## Phase 3 — Structured Generation Contract

Make new story generation return structured blocks and cast updates in addition to display text.

### Work

- Define a `StoryGenerationResult` contract:

```ts
type StoryGenerationResult = {
  text: string;
  cast: StoryCharacter[];
  chapters: StoryChapter[];
  blocks: StoryBlock[];
};
```

- Update Storyteller generation prompts to request structured JSON with narration/dialogue blocks.
- Preserve existing rendered prose, but render from blocks where possible.
- Validate generated block metadata before saving.
- Reject or downgrade invalid speaker ids to `narrator`.
- Add migration/fallback path for legacy plain-text stories.

### Acceptance criteria

- New generated content stores ordered story blocks.
- Dialogue blocks include `speakerId`, `speakerName`, and confidence.
- Narration blocks always use `speakerId: 'narrator'`.
- Unknown or invalid speakers are not silently accepted.
- Legacy plain-text stories still render and can still use narrator-only audio.

## Phase 4 — Dialogue Attribution Validator

Add deterministic validation around LLM-proposed speaker metadata.

### Work

- Validate that every dialogue `speakerId` exists in the cast registry.
- Enforce confidence thresholds.
- Mark low-confidence dialogue as `narrator` unless the user enables aggressive casting.
- Merge aliases into existing character ids.
- Add validators for common attribution patterns:
  - `"..." Vexira said.`
  - `Vexira said, "..."`
  - `"Velkrith," Vexira announced, "the will has arrived."`
- Add an attribution reason/evidence field for debugging.

### Acceptance criteria

- High-confidence explicit attributions map to the correct character.
- Split quotes with the same speaker remain one dialogue speaker for audio purposes.
- Ambiguous quotes fall back to Narrator or are flagged for review.
- The UI can show why a quote was assigned to a speaker.

## Phase 5 — Voice Cast UI

Add a Voice Cast panel to assign cloned voices to characters.

### Work

- Load `voice_profile` assets.
- Render a cast table:
  - Character
  - Role
  - Aliases
  - Selected cloned voice
  - Style/emotion
  - Preview
- Save assignments by `characterId`, not display name.
- Add narrator voice assignment.
- Add missing-voice warnings for characters with dialogue.

### Acceptance criteria

- Users can assign a cloned voice to Narrator and each character.
- Voice assignment survives reload.
- Renaming a character does not break the assigned voice.
- Characters without voices fall back to Narrator voice.
- Preview uses the selected character voice.

## Phase 6 — Metadata-Driven Audio Segments

Make Storyteller audio consume structured blocks instead of reparsing rendered text.

### Work

- Convert story blocks into Voice Studio script segments:

```ts
type VoiceStudioScriptSegment = {
  index: number;
  speaker: string;
  text: string;
  voice_id: string | null;
  character_id: string;
  block_id: string;
  chapter_id: string;
};
```

- Map `speakerId` to `voiceId` through the saved voice cast.
- Preserve chapter ordering and block ordering.
- Use narrator fallback for missing/invalid voice assignments.
- Include metadata in TTS jobs: story id, chapter id, block id, character id, voice cast fingerprint, text fingerprint.

### Acceptance criteria

- Audio generation no longer guesses speakers from prose.
- Dialogue uses assigned character voices.
- Narration uses narrator voice.
- Missing character voices fallback gracefully.
- Generated TTS job payload can be audited back to story blocks.

## Phase 7 — Chapter-Level and Incremental Audio

Support partial regeneration and stale audio detection.

### Work

- Generate current chapter.
- Generate selected chapters.
- Generate full story.
- Track per-chapter text fingerprints.
- Mark audio stale when text or voice cast changes.
- Regenerate only changed chapters when possible.

### Acceptance criteria

- Editing one chapter does not require full-story regeneration.
- UI shows stale/ready/missing status per chapter.
- Full-story download updates after changed chapter regeneration.
- Failed chapters can be retried individually.

## Phase 8 — Audiobook Player and Downloads

Upgrade from a single generic audio player to an audiobook-style player.

### Work

- Add chapter list with play buttons.
- Add full-story playback queue.
- Show current chapter and current speaker/character.
- Add download options:
  - current chapter audio
  - full story audio
  - ZIP of chapter audio files
  - Markdown + audio bundle
- Store audio manifests as Storyteller assets.

### Acceptance criteria

- Users can play individual chapters.
- Users can play the full story in sequence.
- Full-story download is available after all selected chapter audio is complete.
- Chapter ZIP export contains deterministic filenames.
- Assets page can list generated Storyteller audio.

## Phase 9 — Pronunciation and Narration Controls

Add controls for quality and audiobook polish.

### Work

- Pronunciation dictionary per story.
- Pause after paragraph.
- Pause after chapter.
- Read/skip chapter titles.
- Narration speed.
- Dialogue style/emotion.
- Per-character style overrides.
- Bedtime/dramatic/documentary presets.

### Acceptance criteria

- Pronunciation overrides are included in audio job metadata.
- Users can set global and per-character narration style.
- Generated audio reflects pause/style settings where the TTS backend supports them.
- Unsupported settings are visible but do not break generation.

## Phase 10 — Backend Persistence and API Hardening

Move durable story/cast/audio metadata into backend APIs.

### Work

- Add backend storage for structured stories, cast registry, voice cast, and audio manifests.
- Add APIs for cast update, voice assignment update, audio generation, audio status, and audio download metadata.
- Add backend-side validation for story block speaker ids.
- Add stable asset linking between Storyteller and Voice Studio outputs.

### Acceptance criteria

- Story audio state is not browser-local only.
- Audio generation jobs can resume/reload after page refresh.
- Story assets link back to source story/chapter/block metadata.
- Backend rejects invalid speaker mappings.

## Recommended implementation order

1. Native React `StoryAudioPanel`.
2. Story cast registry with local persistence.
3. Voice Cast UI using cloned voice assets.
4. Structured generation contract for new story outputs.
5. Dialogue attribution validation and legacy fallback.
6. Metadata-driven TTS job segmentation.
7. Chapter-level regeneration and stale audio detection.
8. Audiobook player and download bundles.
9. Pronunciation/style controls.
10. Backend persistence/API hardening.

## Testing strategy

### Unit tests

- `splitStoryAudioSegments` for chapter-aware segmentation.
- `voiceOptionsFromAssets` for cloned voice assets.
- cast id generation and alias merging.
- voice assignment persistence.
- block-to-TTS-segment mapping.
- stale fingerprint detection.

### React tests

- cloned voice dropdown remains stable.
- selected voice persists.
- Generate current chapter queues the right payload.
- Generate full story queues all chapter blocks.
- Download button enables only when audio output exists.
- stale audio warning appears when story text changes.

### Integration tests

- generated story -> structured blocks -> voice cast -> TTS job payload.
- ambiguous dialogue fallback.
- full-story multi-chapter audio job.
- failed chapter retry.
- full-story download after all chapter outputs complete.

## Reliability rules

- LLM suggestions are never final until validated.
- Speaker ids must be stable and persisted.
- Voice assignments are saved by character id, not display name.
- Unknown speakers use Narrator.
- Low-confidence quotes use Narrator unless explicitly approved.
- Audio generation consumes structured blocks, never raw rendered prose when block metadata is available.
- Existing plain-text stories continue to work with narrator-only fallback.
