# Storyteller roadmap: fixes, interactive story mode, and voices (2026-11-25)

Storyteller is at `web/src/features/storyteller` (web) and `src/app/apps/story` (backend). Its job is
`story.generate`, in `jobs.py`. This plan does two things:

- It fixes the controls that look like they work but don't.
- It rebuilds interactive story mode around stories the model tags as it writes them. Narration then reads those
  tags instead of guessing them in the browser.

Work in the order of the phases. Each phase can ship on its own. The open questions in §2 must be answered before
Phase 1 starts. §7 is the status log; update it as items land.

## 1. Where it stands

**What reaches the model.**
- The prompt (`jobs.py:81-101`) opens "Write a polished long-form story draft.", followed by `Title:` (or an
  instruction to generate one), `Premise:`, `Action: <word>` and `Interaction mode: <word>`, and optionally
  "Story context" and "Player response".
- The system prompt is "You are a helpful AI assistant." (`jobs.py:155`). It's in `_call_chat_provider`, which
  `podcast.generate` shares.
- The web sends several fields the job never reads (`storyModel.storyJobRequest`, `storyModel.ts:208-262`):
  - `tone`, `writing_style`, `chapter` (:242-244)
  - `prompt_template_id`, `suggested_choice`, `source_job_id`, `source_library_item_id`, `source_story_title`
- So Rewrite, Expand, Dialogue polish and Summarize differ by one word. Each produces a whole new story in the
  library instead of changing a passage.

**Fake stages and controls:**
- The job's three stages (outline → draft → store) are one non-streamed LLM call (`stream=False`, `jobs.py:160`).
- Version labels "v7, v6…" are hard-coded (`StoryPanels.tsx:199`). `StoryVersions` shows the first five of all
  story jobs, not the versions of one story.
- The genre tags "Fantasy / Cozy / Mystery / Slice of Life" are hard-coded.
- The premise counter always reads "0/500" and nothing enforces a limit (`StoryControls.tsx:63`).
- The Output status "Clear" does nothing.
- Chapter media "Play" has no click handler.
- "Queue chapter" only writes a manifest to localStorage.
- The Characters, World Notes and Prompts library sections are empty placeholders.

**Developer panels shown to writers:**
- "Remote status / Metadata checks" (`StoryRemotePanel.tsx`).
- "Structured document / Generation contract preview", which shows fingerprints (`StoryDocumentPanel.tsx`).
- The audio "mapping JSON" textarea (`StoryAudioPanel.tsx`).
- The module title `h2` is rendered twice.

**Interactive story mode (`StoryModePanel`, `useStoryRequests.submitStoryModeMove`):**
- It shows only the last page.
- Each move re-sends the whole story as `source_text` (`storyModel.storyModeContext`), so the context grows without
  bound.
- Suggested moves are keyword guesses: "door" gives "Open the door carefully" and "cat" gives "Follow the cat"
  (`storyTextModel.ts:242`).
- There's no undo, no branching, and no record of the player's moves apart from the text.

**Who speaks.** Nothing asks the model to tag speakers. The browser guesses them afterwards:
- `storyCast.deriveStoryCast` counts as a character any capitalised word that appears at least twice (:65). It
  skips only Chapter, Story, The, A, An, As, I, He, She, They and You (:27). Confidence is 0.55 + 0.08 × count.
- `storyDocument.inferSpeakerFromContext` (:225-267) gives a quote to a nearby name. Confidence is 0.88 for a
  trailing tag, 0.82 action-first, and 0.55/0.5/0.45 for the nearest-name fallbacks; otherwise the quote goes to
  the Narrator at 0.2 (:220).
- The parser would accept `[speaker: X]` or `{"speaker":"X"}` markers, but none are ever produced.
- `storyAttribution.resolveDialogueSpeaker` has no callers. Only `validateDialogueAttribution` (used by
  `StoryDocumentPanel`) is live.

**Persistence.** The library merges three sources (`useStoryLibrary.ts:34-35`, `storyLibraryModel.ts:15-45`):
- one localStorage draft slot (`omnix:storyteller:last-draft`), so a new draft replaces the old one
- every completed `story.generate` job's output
- server story assets saved with "Save story" (`asset_save.py`)

Scene additions, new chapters, the trash (no restore or permanent delete), the cast, the voice cast, the structured
document and the audio manifests all live only in localStorage. That's 18 call sites across nine files.

**Read settings are stored twice.**
- `web/src/features/settings/storyReadSettings.ts` keeps them in localStorage (`omnix.storyteller.readSettings`).
  `StoryReadPanel` and `NarrativeSettings` use it.
- The server already has `StorytellerSettingsProfile` (`src/app/apps/story/declarations.py`), with read speed,
  pauses, chapter titles, style preset and pronunciation.

**Audio.**
- `StoryAudioPanel` first streams sentence by sentence over the `/ws/audiobook` WebSocket
  (`StoryAudioPanel.tsx:151-197, 385-604`; backend `src/app/apps/audiobook/streaming.py`, whose only client is
  Storyteller).
- If that fails, it falls back to one `tts.multi_speaker_synthesize` (or `tts.synthesize`) job over the whole text
  (:337-365).
- The speakers come from the browser guesses above, and the voice cast is per browser.

## 2. Target design

```
                 story.generate, one page/scene per job (structured)
premise/move ──► blocks[{kind, speaker_id, text}] + new_characters + suggested_moves
                         │  validated against the story's cast (deterministic)
                         ▼
        story project (PostgreSQL, per workspace): chapters, pages, moves, versions, cast, notes
                  │                                   │
   interactive page │                                   │ finished story / kept run
                  ▼                                   ▼
   shared speech service (platform/voice):      Audiobook project with speakers
   sentence PCM stream in cast voices,          already attributed → render, assemble, export
   used by RPG and Storyteller
```

Decisions settled in the 2026-11-25 review:

1. **Speaker tags come from generation.** The model writes each dialogue line with a speaker id from the story's
   cast. Its output is a proposal: deterministic code checks every id against the cast and flags any unknown id.
   For Storyteller, an unknown id never becomes a silent Narrator line.
2. **Interactive pages are voiced through a shared speech service, not Audiobook.** Audiobook is a batch pipeline
   (leased jobs per chapter, render cache, assembly) and can't give sound within a second or two of a page.
   - Two paths exist today: the session-free `/ws/audiobook`, which only Storyteller uses, and the RPG's
     session-bound `rpg_voice_routes.py`. The RPG path has `stream_audio_pcm16`, first-piece handling,
     `TtsServiceSaturated` and a cache.
   - The plan merges them into one service in `platform/voice` that both features call. ST-4.1 chooses which
     implementation it starts from.
   - Only committed pages are spoken. A page is committed when its job completes. The web learns that from the
     job's existing `job.completed` event on the shared `/events` stream, filtered by job id, so no kernel change
     is needed.
   - Streaming a page's text as it's written is deferred (ST-3.8). The structured gateway can't stream
     (`providers/structured/gateway.py:316`), and the job events carry no partial payload.
3. **Finished stories go to Audiobook.** "Narrate in Audiobook" hands over the tagged spans. Audiobook keeps the
   speech plan, performance direction, render, assembly and export. It verifies the speakers or fills gaps instead
   of classifying from scratch. A finished or kept interactive run goes the same way, as a transcript.
4. **The browser heuristics and the parallel audio pipeline are deleted** once the tags and handoffs replace them
   (§6).
5. **Read settings have one owner:** the server `StorytellerSettingsProfile`. The localStorage copy is deleted
   (ST-1.7).

Owner answers (2026-11-25): **Q-ST1** only the story pages, because the player's run is reflected in the story;
**Q-ST2** as recommended, a lightweight freeform mode that shares only voices with the RPG; **Q-ST3** existing
stories are imported. The questions as they were asked:

| Question | Blocks |
|---|---|
| **Q-ST1:** In a kept interactive run, does the transcript include the player's moves (read by the narrator, or in a player voice), or only the story pages? | ST-3.6, ST-4.4 |
| **Q-ST2:** Should interactive story mode share anything more with the RPG than voices (for example its world bundles), or stay a lightweight, freeform mode? This plan assumes freeform. | ST-1.1 schema, Phase 3 |
| **Q-ST3:** What happens to existing stories? This plan's default: a one-time import of the localStorage draft and scene additions, and old job outputs and server assets mapped into projects. The alternative is to start empty. | ST-1.4 |

## 3. Known risk found during the review (fix now, independent of this plan)

**The Audiobook routes cache the first request's tenant.**

How it happens:
- `_service_and_context` (`src/app/apps/audiobook/routes.py:273-284`, global `_SERVICE_CONTEXT` :49) captures
  the first request's `current_tenant()`. About 50 routes then reuse it for every later request.
- The repositories filter on that cached context (`WHERE workspace_id = %s` with `context.workspace_id`, for
  example `repository.py:110-120`).
- Meanwhile, each connection's `omnix.workspace_id` comes from the per-request contextvar
  (`persistence/tenant_scope.py`). Audiobook tables have ENABLE plus FORCE RLS (`0106_row_level_security.sql`).

What it does, depending on the database role:
- **Normal runtime role:** RLS uses account B's workspace while the query asks for account A's. B sees an empty
  Audiobook and gets 404s, B's writes fail the policy check, and B's jobs are stamped with A's workspace. That's a
  functional break, not a leak.
- **Superuser or BYPASSRLS role:** RLS is skipped, so B reads and writes A's data.

The first account can be a guest, because sign-in, guests and invites are on. No test has two workspaces.

The runtime role is `omnix_app`, created NOSUPERUSER NOBYPASSRLS by `deploy/postgres/initdb/10-omnix-runtime-role.sh`
and `desktop/supervise.py`, so an install set up that way gets the functional break, not the leak. Fixing it also
found the background workers had the same fault: the pipeline, render and preview loops claimed jobs with the
first tenant, and `claim_next` filters by workspace, so no other account's Audiobook job ever ran.

**Fix (ST-P.1, done 2026-11-25):**
- `routes.py` caches only the service (`_audiobook_service`), and `_service_and_context` reads `current_tenant()`
  on every call.
- Each worker poll lists the workspaces with a ready job of its resource class
  (`list_workspace_contexts_with_ready_jobs`, as the durable feature worker does) and runs the step under that
  workspace's tenant.
- Tests: `src/tests/audiobook/test_audiobook_tenant_postgres.py` runs two accounts through the routes; it fails on
  the old code (B saw A's book). `test_audiobook_background_ownership.py` covers the per-request tenant and the
  per-workspace worker step.

This is a prerequisite for ST-4.4 (the Audiobook handoff), but it's live today for any install with more than one account, so don't wait
for Phase 4.

## 4. Phases

### Phase 0: fixes with no schema change

| ID | Work | Files |
|---|---|---|
| ST-0.1 | Write one prompt per action (draft, continue, rewrite, expand, dialogue, summarize) with a fiction-writer system prompt. Use `tone`, `writing_style` and `chapter`, and declare them on `StoryGenerateInput`. Let `_call_chat_provider` take a system prompt per call, so podcast's stays the same. Cap `premise` at 500 on the server and in the form, with a live counter. | `src/app/apps/story/jobs.py`, a new `story/prompts.py` (delete the stale `story/__pycache__/prompts.cpython-311.pyc` first), `StoryControls.tsx` |
| ST-0.2 | Make the stages honest: one "Write" stage and one "Store" stage. The outline stage comes back in Phase 5. | `storyModel.storyJobRequest`, `jobs.py` |
| ST-0.3 | Remove the fake controls: version labels and the `StoryVersions` strip (versions return in ST-1.6), genre tags, Output "Clear", Chapter media "Play", "Queue chapter". | `StoryPanels.tsx`, `StoryControls.tsx`, `StoryChapterMediaPanel.tsx`, `StoryChapterAudioPanel.tsx` |
| ST-0.4 | Put the developer panels (remote status, structured document, audio JSON) behind a debug toggle, off by default. Remove the duplicate module title. Delete the dead `storyAttribution.resolveDialogueSpeaker`. | `StoryExtraPanels.tsx`, `StorytellerToolbox.tsx`, `StoryAudioPanel.tsx`, `StorytellerWorkspace.tsx` |
| ST-0.5 | Hide the Characters, World Notes and Prompts sections until Phase 2 fills them. | `storyModel.librarySections`, `StoryLibrary.tsx` |
| ST-0.6 | Label Rewrite, Expand, Dialogue polish and Summarize as whole-story actions. Their results stay new library items until ST-1.6. | `StoryPanels.tsx` (`quickActions` in `storyModel.ts`) |
| ST-0.7 | System map: the `story` node no longer says "outline -> draft -> store". | `scripts/system_map_data.py`, then `python scripts/system_map.py build` |

Done when:
- Unit tests on the prompt builder show each action's instructions, and tone and style, in the prompt.
- `src/tests/app/test_chat_generation.py:326-391` is updated, and the podcast-script tests pass unchanged.
- A storyteller web test lists each control from ST-0.3 and shows it is gone. It also shows the debug panels
  hidden by default (ST-0.4) and the three empty sections hidden (ST-0.5).
- ST-0.2: the client declares the stages and the job never advances them, so the labels change but there's no
  per-stage progress yet.
- ST-0.7: `test_system_map.py` passes.
- One real-model spot check of draft and rewrite.

### Phase 1: story projects on the server

| ID | Work |
|---|---|
| ST-1.1 | Migration `src/app/apps/story/migrations/0203_story_projects.sql`. Creating the folder is enough, with no registration step: `migration_roots()` (`persistence/migrations.py:95-116`) finds any `migrations/` folder next to a `feature.py`.<br>The first line is `-- omnix-migration: phase=expand transactional=true`. Numbering is global (0202 is the highest today), so re-check for a free number at merge.<br>Tables:<br>• `story_projects` (title, premise, mode, tone, style, read-setting overrides, `deleted_at`, `workspace_id`, and `origin_kind`/`origin_ref` with a unique index per workspace, for imports and legacy jobs)<br>• `story_pages` (project, chapter, order, blocks JSONB, `hidden`, `source_job_id` UNIQUE, created)<br>• `story_moves` (project, page, player text, chosen suggestion, `parent_move_id` for branches)<br>• `story_versions` (project, `version_number` unique per project, kind `rewrite\|expand\|dialogue\|summarize\|kept_run\|manual`, a blocks snapshot, `source_job_id` UNIQUE, created)<br>• `story_characters` (project, id, name, aliases, description, traits, role)<br>• `story_notes` (project, kind `world\|preset`, title, body)<br>Later items add their own columns in new migrations (rolling summary in ST-3.3, outline in ST-5.1); this one doesn't reserve them.<br>Every child table is ON DELETE CASCADE from `story_projects`, with an index on (project, chapter, order) for pages.<br>Every table gets `workspace_id` with ENABLE and FORCE RLS and the `tenant_isolation` policy, copied from `apps/dubbing/migrations/0165_dubbing_initial.sql:69-73`. |
| ST-1.2 | Repository and unit-of-work registration. Routes `/api/story/projects/...` (CRUD, list, trash with restore and permanent delete), registered by the story feature (`apps/story/feature.py`), so `feature_permission_guard` gives them `story:read` and `story:write` (`security/permissions.py:176, 414-428`).<br>Run `npm --prefix web run api:generate`, stage the regenerated `web/src/api/generated/*` and `web/src/features/storyteller/api/generated.ts`, then run `api:check` (it diffs against git). |
| ST-1.3 | `story.generate` takes a `project_id`, reads its context from the project, and writes its result as a page or a version. `source_job_id` is UNIQUE on both pages and versions, so a retried job is a no-op. A job without `project_id` (queued before the deploy) creates a project from its premise with `origin_kind = 'job'` and `origin_ref` = the job id, in the same transaction as its page, so a retry finds that project instead of making a second one. |
| ST-1.4 | Import per Q-ST3:<br>• the localStorage draft and scene additions become projects (once, then those keys are removed)<br>• each existing story asset becomes a project with `origin_kind = 'asset'` and `origin_ref` = the asset id<br>• old job outputs not already covered become projects with `origin_kind = 'job'`<br>Running the import again creates nothing new. |
| ST-1.5 | Trash retention: a `RETENTION` declaration in `story/declarations.py` whose handler deletes `story_projects WHERE deleted_at < now - retention_days` in batches; the cascade removes the children. Precedent: `_delete_archived_campaigns`, `rpg/declarations.py:69-89`. The worker already runs it under `system_scope`. Seed its `omnix_retention_policies` row in 0203 (`retention_days` 30 proposed; `terminal_only` FALSE, as `persistence/migrations/0171_rpg_campaign_retention.sql` seeds `rpg_archived_campaigns`), because without that row it never runs. |
| ST-1.6 | Versions: rewrite, expand, dialogue and summarize results become a new version of the same story. The version strip comes back with real numbers, plus restore. |
| ST-1.7 | Read settings: the account default is the server `StorytellerSettingsProfile`, edited in Settings. A project can override it, stored on `story_projects`, and `StoryReadPanel` edits that override.<br>Today `NarrativeSettings.tsx:10` copies the server draft into localStorage (dropping pronunciation) and `StoryReadPanel` reads that copy. Remove the copy, then delete `settings/storyReadSettings.ts` and its key. |
| ST-1.8 | System map: the story node and its edges to persistence. |

Done when:
- A story, its pages, cast and trash survive a different browser.
- PostgreSQL tests on the scratch DB (`OMNIX_TEST_DATABASE_URL` set literally) cover:
  - create and append
  - a retried page job and a retried version job
  - trash, restore and purge
  - an import run twice
  - a job without `project_id`
- `test_row_level_security.py` and `test_module_conformance.py` pass with the new tables.
- A route test shows account B can't read or change account A's project.

### Phase 2: tagged generation and the story bible

| ID | Work |
|---|---|
| ST-2.1 | Generate one page or scene per job, never a whole story in one object, so output isn't cut off. The output contract is `{title?, blocks: [{kind: narration\|dialogue, speaker_id?, text}], new_characters: [{id, name, description}], suggested_moves: [..3]}`. Use `app.providers.structured.StructuredOutputGateway` with a story contract and a retry budget; a truncated reply is retried, not saved. The gateway returns one whole object and can't stream, and that's the intended trade-off (see ST-3.8). Follow the story module's own precedent in `podcast_script.py`, which plans, writes in parts with speaker-tagged lines, checks, and reports progress. Don't import `audiobook/structured_call`. |
| ST-2.2 | Deterministic validation: each `speaker_id` must be in the project's cast or in this response's `new_characters`. Unknown ids are flagged on the block (`attribution: "unverified"`). `new_characters` is capped and sanitised. Text fields are data and are never run as instructions. |
| ST-2.3 | Story bible: Characters and World Notes become cards (`story_characters`, `story_notes`). They're sent with every generation within a fixed token budget, as quoted data. New characters the model proposes show up as suggestions the writer accepts. |
| ST-2.4 | Render the manuscript and pages from `blocks`, with the speaker in the margin for dialogue. Export Markdown from blocks. Delete `StoryRemotePanel`, `storyRemoteStore` and `StoryDocumentPanel`. |

Done when:
- Parser and validator tests: a valid page, an unknown id, a truncated reply, and more than the cap of new
  characters.
- A real-model check: 3 pages with 3 speakers, every dialogue line tagged with a cast id or flagged.

### Phase 3: interactive story mode rebuild

| ID | Work |
|---|---|
| ST-3.1 | A reader view showing the whole run (pages with the player's moves in between), scrolling to the newest page, with a jump-to-page list. |
| ST-3.2 | Suggested moves come from the model (`suggested_moves` in ST-2.1). Delete `suggestedStoryMoves`. |
| ST-3.3 | Bounded context: the prompt carries a rolling summary (updated each page, stored on the project), the last 2 pages and the bible, not the whole text. Delete `storyModeContext`. |
| ST-3.4 | Undo the last move (hides the page and keeps it as a version), and branch from any earlier move (`story_moves.parent_move_id`). Show branches in the page list. |
| ST-3.5 | Page arrival without polling: the web follows the job on the shared `/events` stream (`core_jobs_routes.py:92`; there is no per-job route) through `omnixEventClient` and `useJobEventRefresh(queryKeys, { jobId })` (`web/src/events/useJobEvents.ts`), filtered by `job_id`. It shows "writing…" from `job.running` and renders the page on `job.completed`. The server already emits `job.running` (`execution_repositories.py`), but `JOB_EVENT_NAMES` (`useJobEvents.ts:6`) doesn't include it: add it there, check `jobEventSchema` (`eventClient.ts`) accepts it, and drop `job.updated`, which nothing emits. When the stream isn't open (`useJobEventsOpen`), fall back to polling, as `useChatJob.ts` does. No kernel or job-contract change. |
| ST-3.6 | "Keep this run" (per Q-ST1): a branch becomes a finished story version that can go to Audiobook (ST-4.4). |
| ST-3.7 | System map: `web_media` (Storyteller follows job events, not polling) and the story flow. |
| ST-3.8 | **Deferred:** stream page text as it's written. Start it only if the page-arrival time measured in Phase 3 is too slow. Nothing streams partial output today:<br>• `JobProgress` is only `{current, total, message}` (`jobs/models.py:68-71`)<br>• `update_progress` emits no event<br>• job SSE carries lifecycle events only<br>• the old streaming routes are retired (`test_legacy_ui_retirement.py:44-50`)<br>Doing it means choosing between (a) a kernel `job.progress` event with a bounded payload (a jobs-contract, OpenAPI and system-map change) and (b) a dedicated story stream route. It also needs an NDJSON page contract parsed and validated line by line outside the gateway, replacing ST-2.1's call path, and a rule for audio of a page whose job then fails. |

Done when:
- A prompt-builder unit test shows prompt size flat (within 10%) from move 5 to move 30.
- Undo and branch have route and web tests.
- A web test shows "writing…" from the `running` event and the page rendered on `completed`.
- A real-model run of 10 moves, recording p50 and p90 page time from move to `job.completed`. ST-3.8 starts only
  if p50 is over 8 s or p90 over 15 s.

### Phase 4: voices

Order matters: the Audiobook handoff (ST-4.4) ships before the parallel audio code is deleted (ST-4.5), so writing
mode always has a way to be heard.

| ID | Work |
|---|---|
| ST-4.0 | Move `auto_cast`'s description-word matcher from `rpg/session/voice_cast.py:39-66` into `platform/voice`, separated from the campaign document. It takes a per-speaker tie-break, `tie_break(speaker_id) -> float`. The RPG passes one built from its own `rng_for(seed, 0, "voice_cast", stable_sub_index(speaker))` (`voice_cast.py:56`) and keeps `max(sorted(free), key=(overlap, rng.random()))`, so its casts stay byte-identical. The shared matcher also keeps the "author's voice if castable" branch and the `taken`/`free` fallback (`voice_cast.py:50-62`). Storyteller passes one seeded from a hash of project and speaker. Run `src/tests/unit/rpg/test_voice_cast.py` and `src/tests/rpg/playthrough/test_voices.py`. |
| ST-4.1 | One shared speech service in `platform/voice`: "speak these tagged lines with this cast". It keeps the RPG transport: `/speech-plan` splits with `split_sentences` at 240 characters, then one POST per sentence (`text` at most 300) streaming PCM16, `_first_piece`'s single retry on `TtsServiceSaturated`, the runaway guard (`RUNAWAY_FRACTION`: audio near 95% of its token budget is not cached) and whole-sentence caching only. The cache is a port: the RPG keeps `work.rpg_speech_audio`, Storyteller gets `story_speech_audio` (ST-4.2). Before building it, compare it with `/ws/audiobook` on the same 20 sentences (first-PCM latency, behaviour under saturation) and keep the RPG transport unless `/ws/audiobook` wins both. Unknown-speaker policy is a parameter: the RPG keeps its narrator fallback; Storyteller flags the line in the UI and speaks it in a neutral voice, defined as a castable voice other than the narrator's. The RPG routes become thin wrappers importing through `platform.voice.contracts`, with no behaviour change. |
| ST-4.2 | Migration in `story/migrations` (header and numbering as in ST-1.1): `story_voice_cast` (project, speaker, voice, chosen by the writer or automatically) and `story_speech_audio` (project, page, render key, audio). Both carry `workspace_id`, ON DELETE CASCADE from the project, and ENABLE plus FORCE RLS with `tenant_isolation` as in `0165_dubbing_initial.sql:69-73`. Routes `/api/story/projects/{id}/voices` and `/speech-*` are registered by the story feature, so `feature_permission_guard` gives them `story:*`. Contracts regenerated as in ST-1.2. |
| ST-4.3 | Interactive playback, after ST-3.5: a page plays line by line in cast voices once `job.completed` reports it. The handler writes the page in the job's completion transaction, so the page exists when the event arrives; nothing uncommitted is spoken. Controls: play/pause, skip line, auto-play on/off, and stop when the player starts typing. Read settings come from the server profile (ST-1.7). |
| ST-4.4 | Audiobook handoff, after ST-P.1:<br>• a new route that creates an Audiobook project from a story version with spans and speakers already attributed (today Audiobook only imports files: `routes.py:318, 477, 508`)<br>• Audiobook's classifier verifies the given speakers instead of starting from nothing<br>• "Narrate in Audiobook" from writing mode and from a kept run (ST-3.6)<br>This needs an Audiobook migration and its own Audiobook tests, including two accounts. |
| ST-4.5 | After ST-4.4 ships: delete the parallel audio code (§6), including `/ws/audiobook` and `audiobook/streaming.py` (only Storyteller's `StoryAudioPanel.tsx` and `storyAudioMessages.ts` use it), with the tests that pin them. |
| ST-4.6 | System map: the new platform voice node, the RPG and Storyteller edges to it, and Storyteller → Audiobook. |

Done when:
- First sound is measured from the page's `completed` event to first PCM over 20 pages on the real TTS service,
  with no live call in progress: p50 ≤ 1.5 s and p90 ≤ 2.5 s.
- RPG casts are byte-identical before and after ST-4.0; the RPG voice tests, the playthrough suite and the
  published-world golden are unchanged.
- An Audiobook project created from a story keeps every tagged speaker, and its classifier only runs on unverified
  spans.
- A second account can't read the first account's cast or speech audio (PostgreSQL test, non-superuser role).

### Phase 5: plan first, then write

| ID | Work |
|---|---|
| ST-5.1 | A real outline: a planning job returns chapter and beat outlines the writer can edit (stored on the project). Each chapter is drafted from its beat plus the rolling summary. |
| ST-5.2 | Prompt presets in the Prompts section (tone, style and instruction bundles in `story_notes`). |

Done when: route tests for outline create, edit and draft-from-beat; a prompt test shows the beat in the draft
prompt; presets round-trip through the API.

### Phase 6: writing-mode editor

| ID | Work |
|---|---|
| ST-6.1 | An editable manuscript: a block editor over `blocks`, where speaker tags stay attached to their dialogue. |
| ST-6.2 | Actions on a selection or the current scene, returned as a diff to accept or reject, and saved as a version. |
| ST-6.3 | Compare two versions, and restore one. |
| ST-6.4 | Layout: library left, manuscript centre, one right panel with tabs for Write, Characters, World and Audio, plus a toolbar on selection. This replaces the stacked header, the two toolboxes and the action bar. |
| ST-6.5 | EPUB, DOCX and PDF export alongside Markdown. |

Done when: web tests show that an edit keeps its speaker tag, a selection rewrite only changes the selected blocks
and can be rejected, restore works, and each export format opens with a fixture story.

## 5. Validation

Run these after the final change in each phase.

**Python** (`python -m pytest <paths> -q --tb=short`):
- `src/tests/story`, plus the new files: `test_story_prompts.py` (Phase 0), `test_story_projects_repository.py`
  and `test_story_project_routes.py` (Phase 1), `test_story_page_contract.py` (Phase 2), `test_story_prompt_context.py`
  (Phase 3)
- `src/tests/app/test_chat_generation.py`, `test_durable_feature_worker.py`, `test_effective_settings_defaults.py`,
  `test_gateway_openapi_schema.py`
- `src/tests/unit/test_podcast_script.py`, `test_podcast_research.py`
- `src/tests/api/test_legacy_ui_retirement.py`
- `src/tests/scripts/test_system_map.py`

**Web**, from PowerShell:
- `npm --prefix web run test -- src/features/storyteller src/test/FeatureSubmitFeedback.integration.test.tsx
  src/test/feature-boundaries.test.ts`
- `npm --prefix web run api:check`
- `npm --prefix web run build`

**PostgreSQL** (Phase 1 on): the scratch DB on port 16432, never 5432, with `OMNIX_TEST_DATABASE_URL` set
literally. Migrate it first. Phases 1 and 4 also run `test_row_level_security.py` and `test_module_conformance.py`
for the new tables.

**ST-P.1:** `src/tests/audiobook` and `src/tests/unit/audiobook/test_routes.py`, plus its new two-account route
test under a non-superuser role and the BYPASSRLS check.

**Phase 4 adds:**
- the RPG Python suites, `src/tests/unit/rpg/test_voice_cast.py`, `src/tests/rpg/playthrough` (including
  `test_voices.py`) and `src/tests/characterization`, because RPG voice code moves
- `src/tests/audiobook` and `src/tests/unit/audiobook`; `test_audiobook_streaming.py` until ST-4.5 removes it

**Real model** whenever prompts change: Haiku with low effort, one run at a time.

**Lint:** `ruff check` on the changed Python paths, and `scripts/architecture_lint.py` (stage new files first).

## 6. To delete

Delete these once the item that replaces them has landed:

| Code | Replaced by |
|---|---|
| `storyAttribution.resolveDialogueSpeaker` (dead today) | ST-0.4 |
| `StoryRemotePanel`, `storyRemoteStore`, `StoryDocumentPanel`, `storyAttribution` | ST-2.4 |
| `storyTextModel.suggestedStoryMoves` | ST-3.2 |
| `storyModel.storyModeContext` | ST-3.3 |
| `storyCast` (`deriveStoryCast`, its localStorage), `StoryCastPanel` | ST-2.3 |
| `storyDocument` speaker inference and its localStorage | ST-2.1–2.4 |
| `useStorySceneAdditions`, the localStorage keys in `storyModel.ts` and `storyTextModel.ts`, the trash in `storyLibraryModel` | ST-1.4 |
| `settings/storyReadSettings.ts` (and the unused `storyReadSettingsPayload`) | ST-1.7 |
| `POST /api/assets/story` (`story/asset_save.py`, `feature._story_asset_router`), `src/tests/app/test_gateway_text_asset_save.py`, `src/tests/story/test_story_asset_save_staging.py`, its rows in `docs/security/ASVS_L2_CHECKLIST.md` and `scripts/multihost_topology_test.py`. Stories are saved as projects; existing story assets stay readable and are imported by ST-1.4 | ST-1.4 (found in Phase 1) |
| `StoryAudioPanel`, `storyAudioMapper`, `storyAudioManifest`, `storyAudioMessages`, `StoryChapterAudioPanel`, `StoryChapterMediaPanel`, `StoryVoiceCastPanel`, `storyVoiceCast`, `StoryAudioEnhancer.css`, `storySnapshotStore` (once no panel reads it) | ST-4.5 (after ST-4.3 and ST-4.4) |
| `/ws/audiobook` (`audiobook/streaming.py`), `src/tests/audiobook/test_audiobook_streaming.py`, its entry at `security/permissions.py:279`, `docs/architecture/api-transport-exceptions.md:24,99`, `docs/security/PERMISSIONS.md:194` | ST-4.5 |
| `web/eslint.config.js` allowlist entries for the deleted files (one already names a missing `story-audio-enhancer.ts`) | with each deletion |

## 7. Status log

| Date | Item | Note |
|---|---|---|
| 2026-11-25 | — | Plan written from the Storyteller review. Revised after the first document review (21 findings). Nothing implemented. |
| 2026-11-25 | — | Second review: page arrival now uses job lifecycle events (no progress event exists), text streaming deferred to ST-3.8, Audiobook tenant risk restated (ST-P.1), migrations and RLS made concrete, Phase 4 reordered so the Audiobook handoff (ST-4.4) lands before the audio deletion (ST-4.5). |
| 2026-11-25 | — | Third review: ST-3.5 moved to the shared `/events` stream with `job.running` added and a polling fallback; `origin_kind`/`origin_ref` stop duplicate imported projects; retention precedent corrected to 0171; ST-P.1 test recipe; Phase 3 sets the ST-3.8 threshold. Reviewer satisfied (no blockers left). |
| 2026-11-25 | ST-P.1 | Done: one shared Audiobook service, tenant read per request; workers step every ready workspace under its own tenant (`list_workspace_contexts_with_ready_jobs`). Two-account PostgreSQL test fails on the old code, passes on the fix. |
| 2026-11-25 | Phase 0 | Done (uncommitted, worktree `omnix-story`, branch `storyteller`). `story/prompts.py` with one prompt per action and a fiction-writer system prompt; premise capped at 500 (server 422, form counter); payload drops `prompt_template_id`/`suggested_choice`; stages Write + Store; fake controls, genre tags, version strip and duplicate title removed; developer panels behind "Show developer details"; empty library sections hidden; whole-story action labels; system map updated (also fixed the gateway node's stale `src/tests/gateway/` path, which blocked the build). Real-model spot check (Haiku, low effort, the job's exact prompts): draft returned a title heading and a complete story; rewrite kept every event, added no heading or notes. |
| 2026-11-25 | Review | Agent code review of ST-P.1 and Phase 0; its findings were fixed before Phase 1 started. |
| 2026-11-26 | Phase 1 | Done (uncommitted). Server: migration 0203 (six `omnix_story_*` tables, RLS, retention row 30 days), `story/repository.py`, `story/service.py`, `/api/story/projects` routes (CRUD, trash/restore/purge, versions and restore, cast, notes, import), `story.generate` on a project (page, or a version for rewrite/expand/dialogue/summarize; `source_job_id` makes a retry a no-op; a job with no project gets one keyed by its id). Web: the library, manuscript, outline and story mode read the project; Save version, the version strip with restore, Move to Trash with restore and Delete forever; the job is polled until it settles and its outcome reported; a one-time import of the localStorage draft, scene additions, story assets and old job outputs (marker `omnix:storyteller:imported-v1`); read settings are the Settings default plus a per-project override (`settings/storyReadSettings.ts` and its localStorage copy deleted). PostgreSQL tests on `omnix_story`: retried page and version jobs, a job without a project, trash/restore/purge, import twice, two accounts, retention. Found while testing: two quick read-setting changes lost the first (now applied to the cached project at once); the header's primary style sat on the new Move to Trash button. The cast stays in localStorage until ST-2.3, so it does not yet survive another browser. The unused `POST /api/assets/story` is added to §6. |
| 2026-11-26 | Phase 2 | Done (uncommitted). Server: `story/page_contract.py` (one page per call through `StructuredOutputGateway`: blocks, proposed characters capped at 4, up to 3 suggested moves; a reply cut off or without text is asked for again within the budget, never saved); each spoken line's speaker is matched to the cast by id, name or alias, or flagged `unverified`; proposed characters are stored as suggestions; the bible (cast and world notes) goes with every prompt as quoted data within 6,000 characters; rewrite/expand/dialogue rework each page on its own. Web: the manuscript and story mode render from blocks with the speaker in the margin and "not in cast" on a flagged line; Markdown export from blocks; Characters & world cards (accept or dismiss a suggestion, add, edit, remove; world notes); the audio panels read the project's pages and cast instead of inferring speakers. Deleted: `StoryRemotePanel`, `storyRemoteStore`, `StoryDocumentPanel`, `storyAttribution`, `storyCast`, `StoryCastPanel`, the speaker inference in `storyDocument`, `storyTextBlocks`/`storyParagraphs`. The voice choices stay in localStorage until ST-4.5, now keyed by project id. The old localStorage cast was not imported: a heuristic built it and keyed it by text fingerprint. Real-model check (Haiku, low effort, the job's prompt, contract and checker; 3 pages, two runs): 53 spoken lines, every one tagged with a cast id, 3 speakers each run, the stranger proposed on page 1 and reused on pages 2-3, 15-23 s a page. One line in the first run had its dialogue tag inside the spoken block; the checker now splits a spoken block with words outside its paired quotes into the quoted lines and narration (test added). Found while testing: accented names made broken ids (`e-lodie`), fixed. Known limit: the cast is replaced whole, so a writer's change built from a list loaded before a page job added a suggestion removes that suggestion. |
| 2026-11-26 | Phase 3 | Done (uncommitted). Server: migration 0205 adds `parent_page_id` and a per-page `summary` (Phase 2's 0204 added `suggested_moves`); an interactive page is written from `interactive_context` (the newest page's summary, at most 1,500 characters, plus the last 2 pages within 12,000), so prompt size stays flat (`test_story_prompts.py`); `POST …/undo` hides the tip page when it has a move (409 otherwise), `POST …/pages/{id}/open` shows the chain ending at that page and hides the rest; nothing is deleted. Web: `StoryRunReader.tsx` shows the whole run with each move before its page, scrolls to the newest page, a page list to jump to, the model's suggested moves, Undo last move, Continue from here on any earlier page, Other branches (each hidden page no page continues from) with Open, and Keep this run (a `kept_run` version); it follows the story job on `/events` (`job.running` added to `JOB_EVENT_NAMES`, `job.updated` dropped) and polls only while the stream is closed. Deleted: `suggestedStoryMoves` (its heuristic moves; an empty story starts from the textarea) and `storyModeContext` (in Phase 1). Deviations: an undone page stays as an openable branch rather than a saved version, and the summary is stored per page, so each branch keeps its own; a job's page joins the run as it stands when the job completes, so the reader disables undo and branching while a job is active. The prompt tests are in `test_story_prompts.py`, not a separate `test_story_prompt_context.py`. Real-model run (Haiku, low effort, the job's prompt, contract and checker; opening plus 10 moves): page time p50 6.7 s, p90 10.1 s, max 11.7 s, so ST-3.8 stays deferred; the prompt levelled at 6-7k characters from move 4. The model wrote summaries of up to 193 words against the 150 asked; the 1,500-character cap bounds them. The time is the model call; queueing in the worker adds to it. |
| 2026-11-26 | Phase 4 | Done (uncommitted); the first-sound gate passed later the same day (row below). ST-4.0: the description-word matcher is `platform/voice/voice_casting.match_voices`; the tie-break is `tie_break(speaker_id) -> Callable[[], float]` (a draw source), so the RPG passes its own seeded `rng.random` and its casts stay byte-identical (RPG voice tests, playthrough suite and published-world golden unchanged). ST-4.1: `platform/voice/speech_service.py` keeps the RPG transport (240-character sentences, one POST per sentence streaming PCM16, `_first_piece`'s retry on saturation, the runaway guard, whole-sentence caching behind a port: `rpg_speech_audio` / `story_speech_audio`); `rpg_voice_routes` are thin wrappers. The `/ws/audiobook` comparison was not run (the TTS service was down) and the RPG transport is kept as the plan's default. ST-4.2: migration 0206 (`omnix_story_voice_cast`, `omnix_story_speech_audio`, RLS FORCE + `tenant_isolation`, cascade from the project); Phase 1's trash retention seed moved to kernel migration 0207. ST-4.3: `StoryVoicesPanel.tsx` and `storySpeech.ts` play a page line by line in cast voices once the job completes, one sink per line with the next line prefetched; play/pause, skip, auto-play (off by default) and stop on typing; `readSpeed` is not applied yet. A writer's voice choice is re-cast when that voice's recording changes. ST-4.4: `POST /api/audiobook/projects/import-story` (`audiobook/story_import.py`, migration 0208 for the stored story lines); the web relays the story (apps can't import each other, AL001) through `useNarrateInAudiobook.ts` and `storyAudiobook.ts`, from writing mode and from a kept run (a run is kept as a version first). Given speakers are trusted, not re-checked by the classifier; Find speakers gives a line to its cast speaker without a model and sends the rest to review; suggested characters are not in the cast. Two-account Audiobook tests pass. ST-4.5: deleted `StoryAudioPanel`, `storyAudioMapper`, `storyAudioManifest`, `storyAudioMessages`, `StoryVoiceCastPanel`, `storyVoiceCast`, `StoryAudioEnhancer.css`, `/ws/audiobook` (`audiobook/streaming.py`, its test, permission entry and transport-exception rows), and also `storyDocument`, `storyDebug` and the developer-details toggle; `rpgSpeechSink.ts` became the shared `assistant/workspace/pcm-stream-sink.ts`. ST-4.6: system map voice node (cast matcher and shared speech service), story → voice and rpg → voice edges, audiobook → persistence, and the `story_to_audiobook` flow. Also: story prompts are registry templates (`story.prompts.system` and the build pieces; the scorecard's inline-prompt count is back to its baseline); the library list lost its `LIMIT 500`; `storyClient.ts` names generated schemas directly (15 handwritten types gone; the 1 left is podcast `ScriptRequest`, older than this branch). §6's `POST /api/assets/story` is deleted with `asset_save.py` and its two tests; the multihost topology check now uploads an Audiobook text source on one host and downloads it from another (`audiobook` added to that compose file's features), and the ASVS V8.1.2 evidence is restated. Known limit: a page whose narration opens "Chapter N …" is read as a heading. Validation: §5 Python, PostgreSQL (RLS, module conformance, story voices two accounts), RPG suites, playthrough, characterization golden, web tests, build, api:check, ruff, architecture lint. Not run here: the runtime metrics probe (it accepts only the shared `omnix_test` names; left to CI) and the multihost topology job (nightly). **Pending:** first sound (p50 ≤ 1.5 s, p90 ≤ 2.5 s over 20 pages) needs the real TTS service with no live call in progress; it was down. |
| 2026-11-26 | Phase 5 | Done (uncommitted). ST-5.1: migration 0209 adds `outline` (JSONB chapters of beats, each beat with an id and the page drafted from it), `outline_source_job_id` and `preset_id` to `omnix_story_projects`, and `tone` and `writing_style` to `omnix_story_notes`; `story/outline.py` is the planning contract (`story.outline`: chapters of beats, at least one beat, cleaned and capped at 20 chapters of 8 beats; the writer's own plan may have 40 of 12). An `outline` story job plans from the premise, the bible and what is written so far, and stores the plan once (a retried job writes nothing again); `PUT …/outline` saves the writer's edit whole, keeping known beat ids. A `continue` with `beat_id` drafts a page into the beat's own chapter (opening it when the story hasn't reached it) and ties the page to the beat; the page carries a summary, and the next beat is written from that summary and the last pages (`prompts.planned_context`) while it reaches them, otherwise from the whole story. Web: `StoryPlanPanel.tsx` (Plan the story with a chapter count, Plan again after a confirm, edit chapter titles and beats, add and remove them, Save plan or Discard changes, Draft a beat, and "Drafted in chapter N" with the page's opening once drafted); an unsaved edit holds back planning and drafting. ST-5.2: presets are `preset` notes with a tone, a writing style and instructions, kept in the bible panel (now "Characters, world & presets") rather than a separate Prompts section; choosing one (`PATCH` with `preset_id`) gives the story the preset's tone and style, which the tone chips and style select offer beside the usual ones, and its instructions go with every page as quoted style notes; removing the preset in use clears it. The UI's manuscript-heading types are renamed `ManuscriptOutline*`, so they no longer clash with the generated `StoryOutlineChapter`. Tests: PostgreSQL route tests for plan, edit, draft-from-beat and presets on `omnix_story`; prompt tests for the beat in the draft prompt and the preset notes; two web tests. Real-model check (Haiku, low effort, the job's prompts and contracts): a 4-chapter plan of 4 beats each in 12 s, then three beats drafted in 12-21 s each; each page followed its beat and the preset's "short sentences, present tense", the chapter 2 beat opened "Chapter 2: Salt Ink", and the second and third were written from the rolling summary. Validation: `src/tests/story`, `src/tests/unit/prompts`, `src/tests/audiobook`, `src/tests/characterization`, `src/tests/security`, the system map test, web tests, typecheck, lint, build, api:check and architecture lint. The system map's story node names the plan and presets; its stale story → assets edge (gone with `POST /api/assets/story` in Phase 4) is removed. |
| 2026-11-26 | Phase 6 | Done (uncommitted). ST-6.1: `PATCH …/pages/{id}` saves a page's blocks in place; `StoryPageEditor.tsx` edits a page as paragraphs (narration or a spoken line), and a spoken line keeps the speaker the server recorded until the writer picks another, which then drops the `unverified` mark; an emptied page is refused. ST-6.2: migration 0210 adds `selection` to `omnix_story_versions` (`{page_id, start, end, original, proposed, status}`); a story job with a `selection` reworks only blocks [start, end) of one page, with the text before and after as context, and stores a pending version whose pages are the manuscript with the change made; `POST …/versions/{id}/accept` splices it in only while those blocks are unchanged (409 `story_selection_page_changed` otherwise, and the page before it is kept as a "Before accepting version N" version), and `…/reject` closes it (409 `story_selection_not_pending` once answered). The web shows a toolbar on a text selection inside one page, and each proposal as a word diff with Accept and Reject (when the page has changed since, Accept is disabled and Reject becomes Dismiss). ST-6.3: `StoryCompare.tsx` compares a version with the manuscript or another version as a block diff with a summary, and restores it. ST-6.4: the workspace is library left, manuscript centre and one right panel with Write, Characters, World and Audio tabs; the stacked header, toolboxes and action bar are gone. ST-6.5: `story/export.py` builds EPUB and PDF with the standard library and DOCX with python-docx (already installed for Audiobook) from the visible pages, chapters as headings and pages as scenes, speaker tags left out; `GET …/export/{epub,docx,pdf}`, next to the Markdown export. Tests: web tests for an edit keeping its speaker tag, a refused empty save, a selection rewrite changing only its blocks and being rejected, accept, a stale proposal, compare and restore, and the export downloads (now in `StorytellerManuscript.test.tsx`, with the shared mock server in `web/src/test/storytellerServer.tsx` so neither test file passes 1,200 lines); `test_story_export.py` opens each format with a fixture story (EPUB package and navigation, DOCX headings and paragraphs, PDF text across pages); a PostgreSQL route test on `omnix_story` covers edit, the selection prompt, pending, reject, accept, a changed page, bad ranges and a second account. Real-model check (Haiku, low effort, the job's prompt and page contract, a passage in the middle of a page): rewrite 3-5 s, dialogue 5-7 s, expand 10-13 s; no reply repeated the text around it and every spoken line stayed tagged. Expand first grew 75 to 1,193 characters, so the passage note now asks for at most about three times the length; it then gave 543 characters in one block, still about 7 times, but no longer runaway. Deviation: "each export format opens" is checked by the Python export tests, which open the files; the web test checks that each format is downloaded from the server. Validation: `src/tests/story` (PostgreSQL included), `src/tests/audiobook`, `src/tests/unit/audiobook`, `src/tests/characterization`, `src/tests/security`, the system map test, ruff, architecture lint, web tests, typecheck, lint, build and api:check; architecture metrics show only the items that need the runtime probe and the podcast `ScriptRequest` noted in Phase 4. The system map's story node names page edits, selection versions and the export. The Phase 4 first-sound gate was run after this (Gate row). |
| 2026-11-26 | Review | Agent code review of Phase 6; fixed: a page edit names the blocks it started from (`base_blocks`) and a page changed since is a 409 `story_page_changed` (the editor says so and keeps the edit open); `hidden` is no longer accepted by the page PATCH, so a branch cannot be hidden or shown by an edit; a page with no text left is a 422; control characters are removed from block text as it is read and from titles and text in the export, so DOCX and EPUB stay well-formed; a selection job carries the selected texts and fails `story_selection_page_changed` when the page no longer holds them; a selection that ends at the start of the next paragraph (a triple-click) counts only the paragraph it covers; the stale-proposal check compares blocks with the server's key; the export route is documented in `api-transport-exceptions.md`. Kept as limits: the PDF uses the built-in Latin fonts (cp1252), so other scripts need the EPUB or DOCX; a retried job's prompt keeps the text it was queued with. Validation after the fixes: story, audiobook, OpenAPI, system-map and security Python suites pass; web Storyteller tests (51), typecheck, ESLint, `api:check` and build pass; architecture lint 0; metrics show only the failures that were there before (runtime measurement fields and the podcast handwritten API type). |
| 2026-11-26 | Gate | Phase 4 first sound: p50 0.22 s, p90 0.23 s, max 0.81 s (the first page) over 20 pages → passes (≤ 1.5 s / ≤ 2.5 s). Measured on the real TTS service (Qwen3-TTS 0.6B Base, faster-qwen3-tts, RTX 4090) with no live call: the stack was otherwise off, so the service was started on its own from the worktree against the scratch database. Each page's first sentence (new text, so no cache) is timed from the request to the first PCM piece through `platform/voice/speech_service` (the route's cache-miss path), in the `default` voice, the only castable one in the worktree; the gateway hop and cast lookup are not in the number. Sentences were 4.3–9.1 s of audio. |
| 2026-11-26 | Review | Agent code review of the whole implementation (web, story server, Audiobook handoff); fixed: web: each story job is followed with the project it was asked for, so its result reaches that project, and a failure is explained in words rather than as its code; the plan editor's draft belongs to the saved plan it started from, and Draft and Plan again wait while it is unsaved; a bible save reports a failure instead of throwing; a voice choice is stored for the story it was made in; reading new pages aloud forgets the run when another story opens; server: a sentence can be spoken only for a page of its own project (404 `story_page_not_found`); an import has its control characters removed and is split into pages of at most `BLOCKS_MAX` blocks; a retried job reports the page it wrote even after the story went to the trash; the writing-mode manuscript in the prompt is capped (`MANUSCRIPT_MAX_CHARS`, 200,000, its tail cut at a paragraph); a chapter titled as the book is headed by its number and the EPUB nav always lists the title page; Audiobook: a rerun with no classifier decides only the story's own lines, so a classifier's attribution is kept; a resumed analysis replays the story's lines so the next chapter still matches; a stray word in a quotation kept as narration no longer jumps the matcher to a later line; a paragraph that reads as a chapter heading is joined to the one before it; a cast member named as another's alias keeps their own voice (the import returns `skipped_aliases` and logs them); a step that fails in one workspace is logged and the next is tried. The deleted asset-save regression is removed from the RPG deterministic workflow; system map and metrics baselines updated. Kept as limits: the whole-list saves of cast, notes and outline can drop a row a job added between the writer's read and save; the spoken text isn't checked against the page, and stored audio is kept until the project is purged; a manuscript over 200,000 characters is written and summarized from its tail; a chapter's first paragraph that reads as "Chapter N…" can still open a chapter of its own (the title only, no text lost); skipped aliases are not shown in the UI yet. Validation after the fixes: story, audiobook, prompt, OpenAPI, system-map and security Python suites pass; web Storyteller tests (54), typecheck, ESLint, build and `api:check` pass; architecture lint 0; metrics show only the failures that were there before. |
