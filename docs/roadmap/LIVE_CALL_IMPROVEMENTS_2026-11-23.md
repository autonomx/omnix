# Live call improvements (2026-11-23)

Owner request 2026-11-23, after a live call showed a speculation-accept 404 and an evaluation 422 that only the
browser console reported: make failures visible, finish what is built but untried, fix the known rough edges, and
add three features (pick up an interrupted reply, screen share in calls, a call recap).

Related plans: `docs/roadmap/LIVE_COMPANION_ROADMAP_2026-11-15.md` (items 1-6, group calls) and
`docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md` (portrait). This file is the plan and status for the new work.

Defaults chosen without an owner question (change any of them by saying so):

- A call's failures are counted per kind, never with content (status codes only), and shown after the call when
  there were any, and as they happen while it runs.
- An interrupted reply is picked up only when the interruption was an aside the call's model judged as not
  changing the subject; otherwise it is dropped as today.
- Screen share in a call works like camera share: glances described in the background, never on the reply's path.
- A recap is written for a call with at least three of the person's turns, as one assistant message at the end of
  the chat, marked as a recap. Its facts come from the call's committed messages only.

## A. Make failures visible

- A1. One browser reporter (`live-call-health.ts`): `reportLiveCallFailure(kind, {status})`, a fixed list of kinds,
  per-call counts, reset when a call starts. Call sites: speculation start/accept, evaluation save, prewarm,
  overlap judgement, greeting stream, camera glance, avatar socket, route check.
- A2. The call's durable evaluation carries `failure_<kind>_count` and `failure_count` in `quality_metrics`; the
  content-filter test checks those keys too.
- A3. Call health line: while a call runs, the first failure of a kind shows in the call's status line; after the
  call, a short line lists what failed ("Speculation accept failed twice (404)") until the next call starts.
- A4. Route check at call start: call-bound responses carry the answering process (`x-omnix-node`); a call whose
  call-bound responses come from two processes reports `call_route_split`. This is the check that would have
  caught the speculation 404.

## B. Finish what is built but untried

Claude can run:
- B1. Characters talk to each other (companion item 6) on a real model (Haiku, low effort): threads end sensibly,
  lines short and in character, nobody speaks for the person, extraction keeps only self-statements.
- B2. Camera glance with a real vision model, on a still image.

Owner (needs a person, a camera or a GPU session):
- B3. A four-guest group call. B4. A two-character call that lets them talk (with companion 5.7).
- B5. A call with the camera shared. B6. The newest FlashHead and portrait changes in a call.

## C. Known rough edges

- C1. Group calls: when the director's pick declines (SKIP), ask the director once more without that member,
  instead of ending the exchange.
- C2. Group calls: a question to everyone gets every guest's answer. Bound it: the director picks who answers
  (at most two), and the others may react later as usual.
- C3. Portrait: blinks while speaking (speech frames do not blink today).
- C4. Initiative (companion 3.4): tune when the AI speaks up from the saved evaluations' proactive metrics, once
  there are enough calls; report the numbers first.
- Deferred, noted: one portrait stream shared by the speakers of a group call; the STT-finalize allowance with
  the portrait on (a measurement, not a code change).

## D. Features

- D1. "Where was I?": a reply cut off by a short aside resumes after the aside is answered ("As I was saying, …"),
  from the unspoken part of the committed reply.
- D2. Screen share in calls: a share-screen control in the call; shared-screen glances described in the
  background like camera glances; a spoken turn takes the newest description and never waits for a vision call
  on the reply's path.
- D3. Call recap: after a call, a background job writes one recap message (decided, started, to follow up) from
  the call's messages, with the call's model.
- D4. Podcast live avatars: when characters are picked for a podcast, an option turns on their live avatars
  (the call's portrait) for that podcast.

## Status log

- 2026-11-23: plan written. Work order: A, C1-C2, D2, D1, D3, B1-B2, C3-C4. D4 added at the owner's request,
  after D2.
- 2026-11-23: A done (one reporter, a fixed list of kinds, the call's status line and the post-call summary).
  C1 done: a SKIP asks the director once more without that member. C2 done: at most two members answer a
  thread the person started. D2 done: a Screen button in the call shares the desktop share's screen; glances go
  to `POST /api/chat/sessions/{id}/screen/glance` on speech and call start (same `camera_vision` consent), a call
  turn sends `screen_shared` and takes the newest description, kept on the message as `screen_snapshot`; typed
  chat still sends desktop frames. Not used yet for greetings or proactive lines.
- 2026-11-23: D4 done. Each podcast speaker can be cast as a library character (its name, description,
  personality and voice fill the speaker), and a "Live avatars" switch makes the cast speak the live preview
  through the call's TTS socket and portrait link: one PCM session per speaker change, the character's portrait
  on the avatar socket by `?character_id=` (workspace-scoped, no chat needed). The live preview replaces the
  per-line preview jobs and plays in real time; the final multi-speaker render follows unchanged. Characters
  without a portrait pack show their picture.
- 2026-11-23: D4 follow-ups from the owner's first use.
  - "Load live avatars" on the podcast stage (`portrait/CastPortraitLoadControl.tsx`), as a call has "Load
    live video". It loads the portrait model and prepares each portrait face, and the face's idle loop comes by
    `portrait-idle?character_id=` (no chat needed, only loops already rendered). Pressed again once ready, it
    unloads.
  - Fixed "another live call is using it". Each cast member had held its own portrait lease (`character:<id>`),
    so the second speaker was refused `portrait_busy`. The stage now has one run key, and every speaker's avatar
    socket sends it as `?run=` and shares the lease `character-run:<key>`. A speaker change replaces the stream,
    as a group call's does. The load and the run use the same key, so the loops loaded beforehand are the run's.
  - Regenerated the OpenAPI and types. This also picked up D2's `screen/glance` and D3's `live-call/recap`,
    which had not been generated before.
  - The player no longer waits for a stitched segment after a live-avatar run, where nothing is stitched. It
    says the cast is speaking, then that the final render is under way (`RENDERING`), and the finished render
    takes the player unless a stitched preview is still being listened to.
  - The podcast lists every clone in the voice library (`/api/voice-library`), as the chat does. The stored
    voice profiles missed clones that exist only on disk: Abhishek, Afra, Ehsan, Rudeus-Greyrat and
    rudeous-narrarator. Older gateways fall back to the stored list.
- 2026-11-24: the podcast script is the model's (owner report: Jinx, Abhishek and Donald Trump repeated six lines
  for 20 minutes). The browser had sent the script request as a chat message, but a chat send is queued and
  returns no reply, and the podcast view may not call `/api/chat`. So every episode fell back to the template
  builder, which cycles six lines to fill the length. Now `podcast/podcastScript.ts` runs a `podcast.generate` job
  on the podcast model (from settings) and reads its `podcast_script` output. The job carries the episode's format,
  tone, audience, length and each speaker's notes. Prompt `story.jobs.render_job` v2 asks for JSON segments at
  about 150 words a minute, in the speakers' own voices, with no repeated lines. The reader keeps the complete
  lines of JSON cut off mid-way, falls back to `Name: line` rows for the cast's names, and drops a line said word
  for word before. If the script fails or has no lines, the director note says why and nothing is voiced. The
  template builder (`scriptBuilder.ts`) and the chat-session helper are deleted.
  An episode longer than 10 minutes is written in parts (`story/podcast_script.py`), because one reply cannot
  hold a 60-minute script (about 9,000 words). The model first plans the episode
  (`story.jobs.podcast_outline` v1). It then writes one part of about 8 minutes per reply (render_job v3), so
  60 minutes takes 8 parts. Each part sees the plan, its own section and the last 8 lines. Only the first part
  opens the episode and only the last one closes it. Lines that repeat an earlier part are dropped. A part
  with no new lines is asked for once more and then fails the job. The job's progress shows "Writing part N of M"
  in the director note. The job timeout is 1800 s, and the browser waits 31 minutes.
  Script quality, same day (owner: "implement all"):
  - **Planning.** The plan gives each part three or four beats: a claim and who pushes back on it, a concrete
    example, and the question it hands on (`podcast_outline` v2). Each part is told the points already made
    (the model's `covered` list, at most 40 points) and to build on them, not make them again (render_job v4).
  - **Writing.** Lines are written for the ear: one to three sentences, examples and numbers, with no invented
    statistics or quotes. Each line may carry a short `delivery` note.
  - **Source notes.** The producer's source notes (up to 8,000 characters) go into the prompt fenced as data.
  - **Checking pass.** After writing, code flags near-repeats (a shared 8-word run, or 60% overlap of content
    words) and lines over 110 words. The model rewrites only those lines (`story.jobs.podcast_edit` v1). An empty
    rewrite cuts a repeat. A failed check keeps the script.
  - **Pacing.** Code sets the gap before each line: 150 ms before a quick reaction, 750 ms after a long turn,
    350 ms otherwise.
  - **Quality report.** The job reports `script_quality`: words against the target, repeats left, long lines,
    each speaker's share, and lines flagged, edited and cut. The director note shows it with the model that
    wrote the script.
  - **Render.** A studio line that comes back near-silent is rendered again, at most twice, and the take with
    the most voiced time is kept (`voice/speech_presence.py`, the live speech check's 29 characters per voiced
    second). The podcast view has opt-in "Intro and outro sting" and "Room tone" boxes (`voice/bookends.py`).
    Both sounds are synthesized and seeded: a soft chord and noise at -60 dBFS. Timeline entries shift by the
    intro. The chord is leveled to the take, 6 dB under the voices' speaking level with its peak capped at -3 dBFS.
    It used to have a fixed -20 dBFS peak, which played about 15 dB under the voices, and the owner didn't hear it
    on 2026-11-24. The chord is in the final render only; the streamed preview and live avatars don't play it.
  - **Limits.** Delivery notes reach only engines that take them (Fish S2 Pro). Even loudness per speaker
    (`assemble_chapter`) and picking the steadiest section of a clone sample already existed.

  Length and the final render, same day (owner: a 20-minute episode "didnt feel like 20 minutes", and its final
  audio never arrived):
  - **Length.** Each part asks for what the episode still lacks, split over the parts left, in words and in
    lines (about 20 words a line). A part under 75% of its words is continued on its own beats, at most twice.
    A short last part has already closed the episode, so it is written once more and the longer reply kept.
    `script_quality.continued` counts these extra replies. The prompt template is unchanged (render_job v4).
  - **Final render.** The page waited only 3 minutes for `tts.multi_speaker_synthesize`, which speaks every
    line at about 10 s each on the local GPU. It now waits a minute a line, at least 15 minutes, and shows the
    render's "Line N of M". A render that outlives the wait is reported as still running, no longer as
    "completed without playable audio".
  - **Research the topic** (owner asked whether to use web search, then "go ahead and implement"). An opt-in
    button under Source notes runs one research quick search (`POST /api/podcast/research`,
    `apps/story/podcast_research.py`) on the title and the start of the brief. The results come back as cited
    notes (title, link and up to 1,200 characters each, at most 6,000 in all) added after the producer's own
    notes, for them to check and edit before Generate. Nothing is searched while the script is written, and the
    notes reach the model through the existing fenced sources block, as data. The route needs `research:run`,
    which guests do not hold, and it follows research's feature flag and release policy: with research off or
    quick search switched off, it says so and searches nothing. Story declares `uses=("research",)`.
  - **Bigger box for a speaker's text** (owner request). Double-clicking a participant's identity, beliefs,
    personality, speaking style, goal or instructions cell opens it in a large dialog (`SpeakerFieldEditor.tsx`);
    edits apply as you type and Done closes it.
  - **Pause and Stop** (owner request). While a run is going, the Live production card shows Pause/Resume and
    Stop (`PodcastRunControls.tsx`, `podcastControl.ts`). Pause stops the stitched preview at once while the
    script and preview keep being made; with live avatars the cast holds once the current line ends
    (`CharacterSpeechRun.pause/resume`), because the voice session cannot pause mid-phrase. Stop aborts the run
    through one signal: the job in flight is cancelled on the server (`POST /api/jobs/{id}/cancel`), polling ends
    at once, and nothing after it is started, the final render included; what was stitched stays in the player.
    "Stop live avatars" still ends only the cast and lets the final render go on. To keep the workspace under its
    function-length ceiling (now 298), the episode setup, participants, research row and display pieces moved to
    their own components, and the run itself to a module function (`producePodcast`).
  - **Podcast library** (owner request, 2026-11-24). The sidebar's "Recent jobs" card is now a Library of every
    finished podcast (`PodcastLibrary.tsx`, `podcastEpisodes.ts`). It lists completed podcast
    `tts.multi_speaker_synthesize` jobs through `GET /api/jobs` with `module`, `type` and `status` filters,
    paging by cursor, at most 2,000. Each entry shows the title, format, voice count, length, date and speakers, and
    has Play and WAV. Play loads the episode into the studio player, reads the job's `script_segments` and shows
    them as the transcript, timed by line over the length. It is disabled while a run is going. A search box
    appears past three episodes. No backend change. Delete and rename are not offered, because there is no route
    for deleting a rendered audio asset.
  - **Progress bar** (owner request, 2026-11-24). Under Generate, a bar shows the whole run as one percentage
    with what it is doing now (`podcastProgress.ts`, `PodcastRunProgress`). The script is the first 10%, the
    preview the next 45% and the final render the last 45%, because preview and render cost about the same per
    line. Within a stage the bar follows the steps done: the script job's and final render's reported
    `progress.current/total` ("Writing part 2 of 6", "Line 12 of 40"), and the preview's lines made or the
    cast's lines spoken. The stage rail now lights the stage the run is on, where it always lit Speaking Turns.
  - **Transcript follows the audio; the final render reuses the preview** (owner request, 2026-11-24). The line
    being heard is highlighted and kept in view in the transcript box (`PodcastTranscript`, `podcastTimeline.ts`):
    the stitched preview times its lines from each piece's length, the live cast reports the line it speaks, and
    a final render now reports `timeline` (each line's start, after the opening sting) on its output, which the
    player and the library use. Renders from before have no timeline and are not highlighted. The final render
    spoke every line again after the preview had. Running the two at once doesn't help: one local GPU serves both
    and the live preview would stutter. Instead, a run now saves its script as a Voice Studio script
    (`podcastTakes.ts`, titled "… (podcast)"), each preview line is spoken under its saved line and kept as that
    line's take, and the final render asks for no line again (`render_line_ids: []`): it speaks only lines the
    preview missed, then mixes. The bar's shares follow (preview 80%, final 10%). A live-avatar run keeps no takes
    and still renders every line, as does a gateway without PostgreSQL (scripts answer 503).
- 2026-11-23: D1 done (`chat/live_call_resume.py`). When the chat's last line is a reply the person cut into
  (`delivery_status: interrupted`, something heard, at least 40 characters unheard, their turn within 180 s, the
  same speaker in a group call), the next spoken turn's prompt carries a per-turn note with the end of what they
  heard and up to 600 characters they did not. The call's model judges the aside: it answers it and picks up
  ("Anyway, as I was saying, …") or drops the rest. Offered once: anything that answers them ends it. Prompt
  `chat.live_call_resume.cut_off_reply` v1.
- 2026-11-23: D3 done (`chat/live_call_recap.py`). When a call stops, the browser waits 2.5 s for a last reply to
  commit and posts `POST /api/chat/sessions/{id}/live-call/recap` with the call's start. The call's lines are
  the person's spoken turns from the first one after that start and what answered them (task results included;
  an interrupted reply only as far as it was heard; typed messages and an earlier recap's lines left out). Fewer
  than three spoken turns: `too_short`, no job. Otherwise one `chat.live_call_recap` job per call (durable worker
  on PostgreSQL, a thread otherwise) asks the chat's provider and model for three lists, and code keeps at most
  five plain items each and writes one assistant message (`kind: call_recap`, the lists, the lines it covered).
  Nothing found: nothing written. The browser polls the job and refreshes the chat. Prompt
  `chat.live_call_recap.recap` v1.
- 2026-11-23: C3 done for FLOAT (`portrait/idle_loop.speech_blink_closures`, `FloatRuntime.render_blinking`). A
  reply's frames blink like the idle face (every 3.5-8 s, 110 ms shut, 190 ms open): a blinking frame is rendered
  again with its eyelid coordinate shut and takes that render's eye region by how shut the eyes are, so the mouth
  keeps the speech motion. The schedule is seeded per reply, so a frame decoded again after a rewind blinks the
  same way; about seven extra decoded frames a blink. FlashHead's speech blinks by itself and is unchanged.
  Untested on the GPU here: the owner's B6 call shows it.
- 2026-11-23: C4 numbers (no tuning yet). Saved evaluations: 65 on the live database, all from 2026-07-11 to
  2026-08-04 and none since (the evaluation 422 fixed in 25108d9400 is the likely cause); two of them hold a
  resolved proactive prompt (one accepted, one regretted). The call log (source `live_conversation_initiative`,
  2026-11-19 to 2026-11-23): 14 calls, 50 generations started (unresolved_question 23, scene_line 21,
  continue_current_topic 4, gentle_reassurance 1, scene_reaction 1), 14 completed, 11 delivered, 5 answered
  (4 after, 1 during), none ignored. 20 of the 50 starts were one call asking again every 0.7 s for 14 s, each
  turned down with 409 `initiative_spacing`: fixed. The 409 now carries `Retry-After` (the decision's
  `eligible_in_ms`), and the browser waits that long (`server_spacing`; 15 s without the header) before asking
  for another social remark; `initiative_server_held` in the call log, not a failure. Too few remarks to tune the
  thresholds: revisit after a few weeks of calls with evaluations saving again.
- 2026-11-23: B1 done on Haiku 4.5 at effort low through the CLI, with production scene code. The harness covers
  a two-character call (Maya, Daniel) and a three-character call (Maya, Alex, Leo): four person turns, four
  quiet spells, and the memory reader with `validate_learnings` on each thread.
  - Found: no quiet call ever started talk. Talk director v1 had no cast and no lines, so Haiku explained
    instead of naming anyone: 6 of 6 probes parsed as NONE. With the cast and the last lines, 6 of 6 named a
    member. Fixed as `chat.scene.talk_director` v2: `talk_opening` carries the call's last six lines, the
    person's included, and late lines are left out.
  - Re-run with v2:
    - In the three-character call, both quiet spells started a thread (Maya on the meal stories, Alex asking
      Maya about plants). Each ended on its own after two lines: director NONE, or SKIP and then NONE.
    - In the two-character call, Maya was picked twice and said SKIP right after the person shared a big
      decision.
    - Threads the person started ended at one to two lines, and a question to everyone got two answers (C2).
    - Nobody spoke for the person. Lines stayed in character, at most 243 characters; the server cuts them to
      240.
  - Extraction kept 13 learnings, every one a speaker's statement about themselves and none about the person.
    Code dropped one claim with no attribution (`claim_unattributed`).
  - Timings: director 0.48 s mean (1.17 s max), line 1.33 s mean (1.98 s max), extraction 2.9 s mean.
  - Noticed, not changed:
    - Opener SKIPs depend on the persona: Leo ("speaks up only when he has something to say") always skips.
    - Once a first reply on Haiku latched onto the earlier topic instead of the question asked. The harness's
      short personas make that likelier than the full live prompt does.
- 2026-11-23: B2 done on Claude Haiku 4.5 through the CLI vision client, thinking off, on the production path
  (`begin_glance`, then `camera_share_look`). Input was one still 640x480 frame, three glances: a portrait
  beside a held-up card printed with a test card number and an expiry.
  - Without the owner's remote consent nothing was sent (`remote_vision_not_allowed`).
  - With consent, each glance was described in 3.5-3.8 s, at 690-940 characters.
  - Safety rules held in all three: the card number and the expiry were never read out (the model said it would
    not transcribe them), and nobody was named or given an age.
  - A spoken turn that asks at once (2 s wait) misses a glance that slow. In a call the glance is sent when the
    person starts speaking, so an utterance longer than about 2 s finds it ready; otherwise the previous fresh
    description is used.
  - Found: Haiku wraps its "few plain sentences" in markdown ("# Visual Description", "**What I'm unsure
    of:**"). Collapsed to one line, that was noise in the prompt and on the kept snapshot. Fixed:
    `live_call_camera.plain_description` drops headings, bold and bullets, for Show and for camera and screen
    glances.
