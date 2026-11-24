# Live companion roadmap (2026-11-15)

Five chatbot features the owner asked for, in the owner's order: 1 → 2 → 3 → 4 → 5.
Branch `companion-live` (worktree `F:/LLM/omnix-companion`), cut from `main` at 6992973858.

| # | Feature | Status |
|---|---------|--------|
| 1 | The call keeps talking while tool work and research run | in progress |
| 2 | Hear the user's voice, not the room | not started |
| 3 | AI-initiated conversation (polish what exists) | not started |
| 4 | Front camera: on-demand snapshots | not started |
| 5 | Several characters in one call | not started |

## 1. Background work during a live call

**Owner scope (2026-11-15):** Live Agent tool actions (web search, smart home, calendar, any tool added
later) and deep research. Not agent-runtime coding tasks.

**Where it stands today.** A live voice turn skips the agent-runtime typed router
(`agent_runtime/chat_bridge.py` `route_typed_chat_turn` returns None for live voice). It reaches tools only
through the legacy Live Agent (`chat/live_agent_store.py`): a regex classifier sends the turn to the Hermes
planner (up to 6 s), Kasa reads run inside planning, and a confirmed Kasa write runs inline in the confirming
turn. Web search, weather, home and calendar actions are not reachable from a call. Deep research starts only
from the text composer's mode setting.

**Design.**

1. *The call's model proposes the work, through the call-ability protocol.* Calls already let the model ask
   for a web search with one hidden request line, `[[look up: q || words to say]]` (`live_voice/llm/call_tools.py`).
   Background work extends that protocol instead of adding a second tag: `[[research: question || words to
   say]]` today, and later verbs for actions. Each verb maps to an ability in `assistant_tools/owner_grants.py`,
   granted per speaker by the person (`deep_research`: on for the System Assistant, off for characters). The
   prompt offers a verb only when it is granted *and* can run now (`offered_abilities`: deep research also needs
   its settings, a search provider and the release policy, kept a minute), so the model never promises work that
   cannot start. No word lists decide when to ask (owner, 2026-11-04); the line is a proposal only.
2. *The stream holds it back.* `RequestGate` holds every `[[` until it is clear whether it is a request, so the
   line is never spoken or shown. A background request ends the turn with its spoken line (or the model's own
   words when there is none, or "I can't right now" when it is not granted or unavailable); the grant is checked
   again in code. The saved reply records `metadata.call_tasks = [{index, ability, query, allowed, reason}]`.
   An early start (speculation) never runs requests.
3. *A committed request becomes a durable task.* `chat/generation_jobs._commit_chat_reply`, the one commit point
   for both reply paths, starts what the reply recorded (`chat/live_call_tasks.start_call_tasks`), only after the
   commit and never for a cancelled turn, and never lets a failure break the committed reply. Deep research
   starts through the `CHAT_RESEARCH` port (`begin_call_research`) as an ordinary `assistant.deep_research` job,
   with `create_job_once` keyed by `call-task:<user message id>:<index>`, so retries and recovery cannot
   duplicate it. Its result is appended as its own assistant message (`call_task_id`, `call_task_asked_in`),
   since the asking turn's reply already holds the spoken line.
   *Decision the owner can flip:* call research skips plan approval. The grant plus the spoken ask stand in for
   it; the configured budget and the release policy still apply.
4. *Deterministic code owns authority.* An action request (`[[do: <capability> <json> || …]]`, WP 1.5) is the
   model's structured proposal. Code validates it against the registry and the speaker's granted groups, and
   reviews it with `review_assistant_tool_request` in a job. Reads run through `execute_capability`. A write is
   saved as a pending governed proposal and never run by the job. The person hears a code-phrased confirmation
   and confirms it in the very next turn, matched deterministically (`_confirmation_choice` in
   `live_agent_store.py`), or with a button. Profiles and approvals are never widened for voice. Deep research
   starts through the `CHAT_RESEARCH` port.
5. *Status is read from the job.* `GET /api/chat/sessions/{id}/live-call/tasks` joins the message's request with
   its job record (queued, running, completed, failed, cancelled) and whether its report was delivered.
   `POST …/tasks/{task_id}/cancel` cancels.
6. *The call reports back on its own.* The live call polls the task list during a call. When a task settles, it
   asks the server for an initiative candidate. The server names the `task_report:<task_id>` reason, and the
   call runs it through the existing initiative authority (`/live-call/greeting/stream`). The result goes into the prompt as untrusted tool output, the
   character phrases it, and the delivery commit records `task_report_for=<task_id>` on the saved message.
   Floor rules still apply: no report while the user is speaking or a reply is playing. A report outranks
   social initiative, and its cooldown is short.
7. *Conversation continues meanwhile.* Ordinary turns go on as usual. Running tasks and their state go into the
   live prompt as trusted internal state, so "how's that going?" gets a true answer.

**Work packages.**

- 1.1 `[[research: …]]` request: grant, prompt offer when runnable, stream handling, `call_tasks` metadata, start
  after commit, research job keyed by task id, result appended as its own message, tests. **Done.**
- 1.2 Task state and start outcome.
  - Record the start outcome on the asking reply. After the start attempt, `call_tasks[i].start` is one of:
    - `started`;
    - `refused` (`begin_call_research` returned None, e.g. the release policy);
    - `failed`;
    - absent (the gateway died between commit and start).
  - There is no recovery start. An honest "couldn't start" beats research that begins long after the person was
    told it had.
  - `GET /api/chat/sessions/{id}/live-call/tasks` reads the session's assistant replies from the last 30 minutes
    that carry `call_tasks`. It joins each with its job, whose id is computed from the `call-task:<msg>:<i>`
    idempotency key with no scan, and with its result message (`call_task_id`).
  - It returns `{task_id, ability, query, state, asked_at, settled_at, result_message_id, reported}`.
  - `state` is `open | completed | failed | cancelled | not_started`:
    - `open`: queued, leased, running, waiting, retrying, paused, cancel_requested.
    - `failed`: failed, stale.
    - `not_started`: not allowed, start `refused`/`failed`, or no job 60 s after the reply's commit.
  - `POST …/live-call/tasks/{task_id}/cancel` checks that the task's reply belongs to this session, then cancels
    the job with `cancel_job`.
  - Tests:
    - unit tests for the state mapping;
    - a PG test that a background result append and a live turn's commit on the same session both land, so the
      revision check (`chat_store.save_session`) cannot drop either.
- 1.3 Report turn, chosen by the server.
  - `GET …/live-call/initiative-candidate` returns at most one reason. In item 1 the only reason is a settled
    task without a report, as `task_report:<task_id>`; item 3 adds more.
  - The proactive stream parses the `task_report:` prefix. It never puts the raw reason into the prompt.
  - It checks that the task belongs to this session, has settled, and has no report. Otherwise it answers 409 at
    stream start.
  - It uses `turn_id=task-report:<task_id>`, so the delivery commit dedupes by turn id. It derives
    `task_report_for` from the reason, never from the client.
  - Content by state:
    - `completed` research: the server loads the result message, and a bounded summary (about 1,500 characters)
      goes into the prompt as untrusted data. The character tells it in a few spoken sentences and points to the
      full write-up in the chat.
    - `failed` / `not_started`: a short "I couldn't finish/start that", phrased by the model, with no result text.
    - `cancelled`: no report. The task counts as reported.
    - A pending write proposal (1.5): the proposal message's own code-built text through the fixed-text path (the
      listener backchannel's), with no new message. See 1.5.
  - Length: the proactive stream stops at the first sentence or 500 characters. A `task_report` gets its own stop
    rule: at most 3 sentences or about 600 characters.
  - Initiative lease: `_proactive_initiative_policy` (`apps/character_interactions/routes.py`) gets a `task`
    branch with short spacing, not the social 25 s.
  - Live prompt history: a message with `call_task_id` is replaced in later live prompts by a bounded stub
    ("[research result: <query>, see chat]"). The report and 1.4 state carry what the call needs. An untrusted
    write-up never sits in the history as the assistant's own words.
  - Tests.
- 1.4 Web.
  - While the call has an open task, it polls the task list every 5 s, and stops when none is open.
  - It shows a "working on it" chip per open task, with a cancel button.
  - When a task settles, it asks `initiative-candidate`. That is the one path that starts a report, and the same
    endpoint is item 3's.
  - A report has its own decision function, `decideTaskReport`, and its own arbiter source (`task`). It obeys the
    floor: no report while the person speaks or a reply plays, while a turn is in flight, or while the call is
    closed. It ignores the idle threshold, the prompt cap, `previousPromptIgnored`, initiative mode and the
    hidden tab, because the person asked for this.
  - Component tests. **Done.**
- 1.5 Actions in calls: `[[do: <capability> <json input> || words to say]]`.
  - There is no general planner to reuse. The Live Agent planner is Kasa-only and needs Hermes. Text chat's direct
    lane builds only `home.set_state`/`home.get_state`, by regex. So the call's model proposes the structured
    call itself, and code validates every part.
  - Abilities and inputs. Two abilities of a new kind, `action`: `smart_home` and `calendar`. They are on for the
    System Assistant and off for characters. Each offered capability has a typed input model in code; the
    registry's `input_schema` is prose and cannot type-check.
    - Capabilities offered by voice, with their inputs:
      - `home.list_devices` {}
      - `home.get_state` {target}
      - `home.set_state` {target, on: bool}
      - `calendar.read_availability` {start_time, end_time, timezone}
      - `calendar.create_event` {title, start_time, end_time, timezone, location?, description?, reminder_minutes?}
    - Not offered by voice:
      - `kasa.*`: the plugs are reached through `home.*`, so there is one path per device;
      - `home.get_energy` (always "not supported");
      - `home.apply_scene` (a list of actions);
      - calendar attendees (inviting people by voice);
      - `calendar.delete_event`.
    - Aliases resolve through `canonical_id`, and only `assistant_visible` capabilities are offered.
  - The prompt offers `do` only when an action ability is granted and its connection is configured. The catalog
    lists id, one-line description and input fields. It is deterministic and sorted, kept a minute like
    research, and goes in the per-turn part of the prompt.
  - The stream parses the line. An action ability starts a task even though its writes need confirmation. Only
    a write waits, so `runs` uses the ability's kind, not `decision.confirm`.
  - Code validates before anything is recorded:
    - the capability is in a granted group;
    - the input parses into its typed model, with strings bounded;
    - otherwise the request is `allowed=False, reason="invalid"`, and the turn says it can't.
  - After commit, job type `chat.live_call_action` (one per task, `create_job_once`).
    - Grant: an *unapproved* `CapabilityGrant("chat", session_id, approved_by=None, policy_floor="always_ask")`,
      with no approval audit.
    - `_confirmation_grant` is not used in the job. It falls back to the process's default principal when no
      request is in context, which would record an approval nobody gave. It stays for the confirming turn and
      the button route, which run in a request.
    - The job branches on the capability's *effect*, not on the review's approval flag:
    - A read: `review_assistant_tool_request`, then `execute_capability`. The result is appended as a message
      with `call_task_id`, and the report (1.3) tells it.
    - A write: never executed by the job, even when per-action settings would let it run automatically
      (`policy_floor="always_ask"`).
      - Smart home: the job first resolves the device with `home.list_devices`. Exactly one device must match
        the target, by normalised name equality, else one unique substring match. Otherwise the task fails with
        "I couldn't find <target>".
      - The proposal's `target` is the resolved device id, not the spoken name, so a confirm acts on the device
        that was named.
      - Calendar: the job checks that the times parse, that the end is after the start, and that the timezone is
        a real IANA name.
      - It reviews the request (`review_assistant_tool_request`). If not allowed, the task fails with the
        review's summary.
      - It appends the proposal as the task's result message, with these fields:
        - `call_task_id`;
        - `pending_governed_tool_request` (the resolved device, absolute times);
        - `governed_tool_execution_status="pending"`;
        - `governed_proposal_origin="live_call"`;
        - a code-built question as its content, question first: "Turn on Desk Lamp? Say confirm or cancel." or
          "Add 'Dentist' on Tue 18 Nov, 15:00–16:00 Europe/London? Say confirm or cancel."
  - Report of a proposal. The report turn (1.3) speaks the proposal message's own text through the fixed-text
    path. No model is involved, and no second message is made.
    - At stream start, the server stamps `report_started_at` on the proposal message. It is a conditional
      update. The status must still be pending, and the proposal must be unreported with either no stamp or a
      stamp older than 10 s. That way a report stream that failed after stamping can be offered again by the
      candidate endpoint.
    - The delivery commit marks `reported`.
  - Confirmation, decided on the server when reading:
    - A live-call proposal is *confirmable* by a user message M when all of these hold:
      - `report_started_at` is set;
      - M is the first user message in the session created after `report_started_at`;
      - M comes within 2 minutes of it;
      - for a voice turn, M carries `heard_turn_id=task-report:<task_id>`.
    - The web sets `heard_turn_id` only when the person began speaking after the report's audio started. A late
      final of a "yes" said to an earlier question therefore cannot confirm it.
    - A text-composer turn needs no `heard_turn_id`, since the question is on screen.
    - A barge-in "yes" during the question counts. While a proposal report plays, overlap is checked with
      `_confirmation_choice` before the overlap judge, so "yes" or "confirm" always becomes a turn and is never
      dropped as a backchannel.
    - Any other case is *expired*. Expiry is worked out on reading, so there is no status write to race.
    - `_pending_governed_proposal` applies this rule to `live_call` proposals. Text-chat proposals keep today's
      rule.
    - The spoken match is the existing `_confirmation_choice`.
    - The call's Confirm/Cancel buttons call a route. It checks that the proposal belongs to this session and
      that its report started within 2 minutes; the person has seen or heard it. It uses the same function, the
      same approver (`current_approver("tools:approve")`) and the same audit.
  - Claim. A new store method `claim_message_metadata(session_id, message_id, *, require, patch)` merges `patch`
    into the message's metadata only while every `require` condition holds, and returns whether it won.
    - Each condition is a field equal to a value, or a field missing; a missing key is never `->> = NULL`.
    - PG: the existing `update_message_metadata` row update (session row lock), plus the `WHERE` conditions.
    - The in-memory store takes `CHAT_MUTATION_LOCK` itself.
    - The claim never uses the load-and-save fallback in `_patch_message_metadata`.
    - Confirm claims `pending → executing` before `execute_capability`, then writes `executed`/`failed`.
    - A crash after the claim leaves `executing`. It is shown as "unknown" and never re-run, because the write
      may have happened.
    - The `report_started_at` stamp uses the same method.
  - Speculation. While the session has a confirmable proposal, speculation neither starts nor is accepted. Today a
    speculated "confirm" commits a model reply and runs nothing, and the legacy Kasa path has the same hole. The
    fix covers both.
  - Approval policy is unchanged. `always_ask` stays ask, and voice never widens a grant.
  - Tests:
    - validation (unknown id, ungranted group, bad input, delete and scene not offered);
    - a read runs; a write never runs in the job, even with automatic per-action settings;
    - device resolution: none, one or several matches;
    - confirmable only after the report starts, as the first later message, within 2 minutes;
    - a voice turn without `heard_turn_id` does not confirm;
    - a re-stamp after a failed report;
    - the job's grant is unapproved and writes no approval audit;
    - a confirming overlap during the report becomes a turn;
    - a text-composer turn expires it;
    - spoken and button confirms run it once, by the claim;
    - an `executing` crash is never re-run;
    - speculation is refused while pending.
- 1.6 Running tasks in the live prompt, plus a real-model check.
  - The per-turn part of the prompt (not the cached prefix) gets trusted state: what is open, for how long, and
    what finished. Then "how's that going?" gets a true answer.
  - The check: does the call model write `research` and `do` (with valid JSON) when it should, and not otherwise?
  - Use a labelled set like the overlap judge's: about 40 remarks, including real asks, small talk, and role-play
    lines that mention lights or research.
  - Run it on Haiku low and the local model, and write the numbers here.
  - Results, 2026-11-15 (`scripts/live_call_tools_eval.py`, 40 remarks, every ability granted, a short stand-in
    persona; the call's own `RequestGate` and `check_voice_action` grade each reply):
    - Haiku 4.5, effort low (claude-cli, live turn): 40/40. 19/19 asks started the right request, 0/21 false
      starts (0/5 in role-play), 11/11 action inputs valid, first text median 0.65 s (worst 2.0 s). The answers
      about running tasks matched the task list ("still running", "waiting on you: say confirm").
    - The first run scored 39/40: a valid `[[research: …]]` with a 330-character question failed the parser's
      240-character cap and would have been spoken as text. Fixed: the question is cut at a word at 480
      characters, and a line that begins as a request is never spoken even when it does not parse.
    - Local model: not run. LM Studio was not running and could not be started from the agent's shell. Run
      `python scripts/live_call_tools_eval.py --provider lmstudio` with Qwen loaded (check commit headroom first).

## 2. Hear the user's voice, not the room

**Where it stands today.**
- The call's microphone uses the browser's echo cancellation and noise suppression (`live-voice-controller.ts`).
- The speech service cuts speech into segments (`providers/nemotron_eou_live_websocket.py`, which holds the
  segment's audio at finalize). Smart Turn decides when a turn ends. Overlap during a reply goes to the call
  model's overlap judge.
- Nothing knows *whose* voice a segment is, so a TV or another person in the room becomes a turn.
- The speech service already has a speaker model in the same process: TitaNet, `/speaker/embedding`, which loads
  lazily and unloads when idle. Today it checks TTS takes (`live_voice/speech/voice_likeness.py`).

**Design.** The person enrols a voiceprint, and it is used as a soft weight, never a hard gate. No print, no score,
or a score that came too late all mean today's behaviour. The final transcript is never delayed for a score.

- 2.1 Enrolment.
  - An opt-in "Learn my voice" step in the call's voice settings: about 20 s of the person reading three short
    passages, embedded by the speech service.
  - The averaged embedding is stored in the database (owner, Q2) as a document: module `live-voice`, record type
    `voiceprint`, record id = the user id. The document store is keyed by workspace, so the user id is what
    makes it per account.
  - It holds the embedding, model id, created time and sample count, with Delete. Omnix has no account deletion
    to hook into, so Delete is the removal path.
  - Guests cannot enrol.
  - No audio is kept, and the print is never logged.
  - The person can re-enrol after a new microphone or a cold.
  - Tests.
- 2.2 Score each segment.
  - The gateway's STT proxy (`platform/voice/stt_proxy_routes.py`) only relays bytes today. It sends its own
    `speaker_profile` message to the service before relaying the browser's `hello`, and drops any
    `speaker_profile` the browser sends. The service stays stateless about people.
  - The service warms TitaNet at call start and keeps it loaded for the call.
  - After each final, the service embeds the finalized segment in parallel. It sends a separate
    `speaker_score {segment_id, similarity}` message, so the final itself is never held back.
  - A segment shorter than about 0.8 s gets no score.
  - Only the Nemotron provider scores. The other `/ws/transcribe` provider (`providers/stt_live_websocket.py`)
    sends none, and the call falls back to today's behaviour.
  - The web logs the score with the segment (`stt_final_received` → a `speaker_similarity` field).
  - Tests with recorded fixtures.
- 2.3 Shadow measurement.
  - Calls log scores on the owner's real calls.
  - Add a labelled recording set: the owner's voice, the TV, another voice, and the owner over the TV.
  - Pick the threshold from those numbers. Target: under 1% of the owner's own segments fall below it.
  - Write the results up in this file before 2.4's default can change.
- 2.4 Use it: "Only respond to me", default off until 2.3 is written up.
  - When it is on and a segment's score arrives below the threshold before the turn is submitted:
    - the segment is not submitted as a turn;
    - it is shown greyed in the transcript with "Send anyway";
    - a speculation started from its partials is discarded, not accepted.
  - Overlap from another voice during a reply never interrupts it.
  - The overlap judge gets the score as a hint.
  - A missing or late score falls back to today's behaviour.
  - Component and unit tests.

**As built (2.2-2.4), where it differs from the design above.**
- The score is logged as its own `stt_speaker_score` record (segment id and sequence), not as a field on
  `stt_final_received`: it arrives after the final, and the final's record is written when the final arrives.
  With the setting on, `speaker_assessed` records the verdict, basis, similarity, threshold and wait.
- The service sends a `speaker_score` for every final of 0.8 s or more. `similarity` is null when there is no
  answer (TitaNet did not warm, or the score failed), so nothing waits on a model that will not answer.
  `session_ready.speakerScores` says whether the connection scores at all; without it the setting does nothing.
- "The final is never delayed" holds only while the setting is off. With it on, a final of 0.8 s or more waits up
  to 300 ms for its score (`SPEAKER_SCORE_WAIT_MS`), since the score always comes after the final. A late or null
  score means today's behaviour. This is the setting's latency cost, and why it is opt-in.
- The threshold is provisional (`PROVISIONAL_CALLER_THRESHOLD`, 0.35) until 2.3's recordings are written up.
- Overlap during a reply: with the setting on, an interruption the partials confirm is deferred, with the reply
  ducked (0.18), until the final's voice is known. The caller's voice or no verdict dispatches it; another voice
  drops it and the reply plays on. The duck lifts on every path, at the turn's reset, at the end of the call,
  and after 8 s at most. The caller's own interruptions therefore take effect at the final, not the partial.
- Speech before a reply is audible no longer cancels it while the setting is on; a final in the caller's voice
  (or with no verdict) cancels it then.
- The overlap judge gets no score hint: a final in another voice is held before the judge is asked, so the judge
  only ever sees the caller's voice or a final with no verdict.
- Known limits: the greeting at call start and a desktop-companion delivery still stop for any speech; the echo-
  aware duplex gate's own duck is not deferred. A held row's "Send anyway" works only during its call.
- Risk: TitaNet warms in a worker thread at call start, in the speech service's process; a cold load holds the
  GIL in parts and may slow the first partials of a call. Watch `stt_speaker_score` model times and first-partial
  latency on the first real calls.

## 3. AI-initiated conversation (polish what exists)

**Owner (Q3):** the companion starts conversations only inside a call, never outside one.

**Where it stands today.**
- The client's initiative controller (`live-conversation-initiative-controller.ts`, `-policy.ts`,
  `companion-initiative-arbiter.ts`) decides when a quiet call may speak.
- The server's lease authority (`companion_activity/initiative.py`) and proactive route
  (`chat/live_conversation_proactive.py`) run the turn. The model may answer SKIP.
- The *reason* for speaking is weak. Any transcript gives `continue_current_topic` (`unresolved_question` after a
  "?"); otherwise a profile default applies. Regexes (`THINKING_PATTERN`, `SENSITIVE_PATTERN`) gate it.
- The live prompt asks `plan_companion_initiative` (`live_voice/prompt/companion_context.py`). It only runs on
  legacy temporal retrieval, which is off now that memory v2 is authoritative, so on the live system it
  contributes nothing.
- Memory v2 holds `open_loop` assertions, such as promises found by conversation readings
  (`assistant_memory/v2/understanding.py`), but nothing raises them in a call.

**Work packages.**
- 3.1 Audit and measure.
  - From the call log of the owner's recent calls: how often initiative fires, is skipped, and is answered or
    ignored.
  - List every reason path and pattern.
  - Write it up here, with what to keep.
- 3.2 Grounded reasons from the server.
  - `initiative-candidate` (from 1.3) gains a second source, after task reports: one active v2 `open_loop`
    assertion in the speaker's own memory scope that has not been raised in this call.
  - The client asks for a candidate when its policy says it may speak socially. If it gets one, it speaks with
    that reason. Otherwise it keeps today's `continue_current_topic` fallback in gentle mode.
  - An open loop's text goes into the proactive prompt as the companion's own memory, bounded. It is raised at
    most once per call. The server derives `raised_open_loop_id` from the reason and records it on the
    delivered message. A call is bounded by the live call's id.
  - Private-transcript sessions and memory-off sessions get no open loops.
- 3.3 Controls.
  - A per-call "quiet" toggle on the call. Social initiative stops, and task reports still come.
  - Quiet hours and an hourly cap (beside `max_idle_prompts`) in the live profile. Regenerate the OpenAPI spec
    and the generated client.
  - An ignored opener (`previousPromptIgnored`) also cools that reason for the call, not just the next prompt.
- 3.4 Patterns.
  - Only if 3.1 shows that `THINKING_PATTERN` misfires: replace its "give me a minute" detection with the call
    model's judgement where it already runs (the overlap judge pattern).
  - `SENSITIVE_PATTERN` stays as a privacy floor.

**3.1 audit (2026-11-15).**
- The owner's call logs hold no initiative data at all. The initiative controller sent its decisions only as
  browser perf events (`ASSISTANT_VOICE_PERF_EVENT`), and nothing forwarded them to the call reporter. So how
  often initiative fired, was skipped, or was answered could not be measured from past calls.
- Fixed first. The controller now writes to the call log (source `live_conversation_initiative`):
  - every generation start, completion, skip and delivery;
  - `initiative_answered` (`when`: `during` or `after`) and `initiative_ignored`;
  - a policy, task-report or arbiter decision, only when it changes (the policy ticks every 750 ms).
  The numbers can be measured from the next real calls.
- Reason paths, in order:
  1. `task_report:<task id>`, from the server's `initiative-candidate` (1.3/1.4). It goes first.
  2. `open_loop:<key>`, from the same route with `social=true` (3.2). Social turns only.
  3. The transcript: `unresolved_question` after a trailing "?", otherwise `continue_current_topic`.
  4. With no transcript, the profile's long-pause behaviour: `gentle_reassurance` or `ask_to_continue`.
  5. Otherwise `ambient_visual_presence` when desktop context is fresh (source `ambient`), or no reason, so
     nothing is said.
- Patterns:
  - `THINKING_PATTERN` ("give me a minute", "let me think", "hold on", ...): `user_requested_time`.
  - `SENSITIVE_PATTERN` (password, PIN, account, card number, address, 4+ digits, ...): `sensitive_dictation`.
  - Kept: both.

**As built (3.2-3.4), where it differs from the design above.**
- 3.2. The server has no id for a live call. A loop counts as raised for 12 hours (`RAISE_WINDOW` in
  `chat/live_call_open_loops.py`), from the `raised_open_loop_id` on the delivered messages; that stands in for
  "once per call". The call never sees an assertion id: the reason carries a 24-hex key, a hash of it. The
  client also cools a loop for the call when the model skips it or the person ignores it.
- 3.2. The client asks for an open loop only after its own policy and the arbiter accept a social turn, with a
  1.5 s timeout. The loop replaces the local reason; ambient turns and task reports never ask.
- 3.3. "Ignored" is redefined. The old signal (`previousPromptIgnored`, which silenced every remark for the
  rest of the call) counted talking over a playing remark as ignoring it, which was backwards.
  - Speaking while a remark plays, or within 20 s after it, answers it.
  - 20 s of silence after a delivered remark means it was ignored, and that exact reason is cooled for the
    rest of the call.
  - Echo or room noise that passes speech detection counts as an answer. With "Only respond to me" on (2.4),
    it is less likely.
- 3.3. A model SKIP now sets the cooldown. Before, an ambient skip asked the model again on every tick. A social
  skip also spends one prompt of the quiet period, since its reason cannot change until the person speaks.
- 3.3. The hourly cap counts every delivered social and ambient remark, across calls, in the page's memory. A
  reload starts it again. `max_initiatives_per_hour` defaults to 4; 0 means no unprompted remarks.
- 3.3. Quiet hours (`quiet_hours_enabled`, `quiet_hours_start`, `quiet_hours_end`, local time, `HH:MM`) may wrap
  midnight; an equal start and end means no quiet hours. Quiet hours and the call's Quiet button hold back social
  and ambient initiative only. Task reports have their own policy (`decideTaskReport`) and still come.
- 3.3. Quiet is a button beside Mute, in the voice card and the full-screen call. It is not mute: the call still
  hears the person. Each call starts with it off.
- 3.4. Not done. 3.1 found no evidence that `THINKING_PATTERN` misfires, because there was no data. Revisit
  once the call log has a few weeks of initiative decisions.

## 4. Front camera: on-demand snapshots

**Owner (Q4):** only a snapshot's description is kept. The image is never stored.

**Where it stands today.**
- Live capture is audio-only (`video: false`).
- A vision path already exists for the desktop companion:
  `providers/desktop_vision.default_desktop_vision_client().describe(image, question)` turns a frame into a text
  observation, used by `chat/assistant_context/service.py`.
  - It runs on a local OpenAI-compatible vision model or on Codex, configured by `OMNIX_VISION_*`.
  - Codex is remote and needs explicit remote consent (`desktop_vision.py`).
- The call's own model (Claude CLI) takes no images. (Since 2026-11-22 it does: see that day's camera entry.)

**Work packages.**
- 4.1 "Show" button in the call. It appears only when vision is configured and allowed: local, or remote with
  consent.
  - The first press turns the camera on, with a visible indicator, and shows a preview.
  - A second press takes one frame, and the track stops at once. Closing the preview or ending the call also
    stops it.
  - The frame (JPEG, longest side 1024 px) is attached to the person's next turn.
  - Component tests, including that no track stays open.
- 4.2 Server.
  - A live turn accepts one `camera_image` in a field of its own, size-capped. It does not use `image_data_urls`,
    which is stored in message metadata and re-sent in later prompts.
  - Before the reply, the vision client describes it for the turn's words, with the same remote-consent check as
    desktop frames. The description joins the turn's context as untrusted observed content (source `camera`).
  - The image is dropped after the call returns. The saved user message records `camera_snapshot: {description,
    described_at}` only.
  - Automatic memory extraction skips that description.
  - The stream speaks a short fixed filler ("Let me look.") before the vision call.
  - A vision failure or timeout (about 8 s) is told in the reply ("I couldn't see it") and never blocks the turn.
  - A turn carrying a camera image is never speculated, since a speculated reply never saw the image.
  - On a local vision model in LM Studio, check commit headroom first (see the LM Studio notes).
  - Tests: not stored, not re-sent, consent required for remote, failure path.
- 4.3 The call asks to look.
  - A verb `[[look: what to look at || words to say]]`, with ability `camera`. It is off for everyone until the
    person grants it, and offered only when vision is available.
  - The turn ends with a `camera_request` event, and the web shows the Show button prominently.
  - The web never opens the camera by itself. Only the person's press does.
  - Tests.

**As built (4.1-4.3), where it differs from the design above.**
- 4.1. Show appears only while a call is active, not merely owned, and only for the chat whose availability it
  read (`GET …/live-call/camera`: `available`, `remote`, `reason`). It sits beside Quiet in the voice card and
  the full-screen call. The preview floats above the controls so the button row keeps its layout.
- 4.1. The picture goes with the next spoken turn only. A typed turn neither sends nor uses it, and the server
  also ignores `camera_image` on a turn that is not a live voice turn. Closing the preview, Discard, or a call
  starting or ending drops it.
- 4.1. A turn with a picture always goes to the chat route. Agent mode, desktop sharing and a local folder sit out
  that one turn, since only the chat route describes the picture.
- 4.2. The description is saved on the user message's metadata (`camera_snapshot`) and joins that turn's context
  only. Later turns' history and memory extraction read message content, so neither sees it again.
- 4.2. "Let me look." is committed as the reply's spoken prefix. A failure, timeout or empty description ends in
  "Sorry, I couldn't see it." and the turn goes on without the picture.
- 4.3. A granted `look` ends the turn: the call says its words (or "Can you show me? Press Show when it's in
  view."), the stream emits `camera_request` before `complete`, and `complete` carries
  `call_camera_request: {query, allowed, reason}`. Without the grant, or with vision unavailable, nothing is
  emitted and the model is told it cannot see the camera. `look up` still means web search.
- 4.1. **Known limit:** the `camera` grant gates only the model's `look`. Show is the person's own button, so a
  picture they send is described even when the companion may not ask for one. The remote-consent check of the
  vision client still applies.

**4.4 Camera share (added 2026-11-21, owner request).** The camera can be shared like the screen: it stays on
until the person turns it off, in live calls and typed chat.
- **Owner choices (2026-11-21).** Glance as the person speaks, so replies don't wait. Offered in live calls and
  typed chat. Camera and screen can be shared at once.
- **Web.**
  - The toggle is a Camera button beside Desktop in the composer, a Camera item in the "+" menu, and Camera in
    both call rows. Only that press opens the camera (`facingMode: 'user'`, video only).
  - While the camera is shared, a mirrored self-view tile sits in the stage's bottom-right corner, with a
    "Camera on" badge (`chat/CameraShare.tsx`).
  - Show steps aside while the camera is shared, and a picture Show held is let go.
  - The store is `workspace/camera-share.ts`.
- **Glances.** A frame (longest side 768 px) goes to `POST /api/chat/sessions/{id}/camera/glance`:
  - when the person's speech is confirmed, at most every 4 s;
  - on typing, at most every 10 s;
  - before a turn whose chat had no glance in the last 15 s.

  The gateway describes the frame in the background (`chat/camera_glance.py`, one at a time per chat) and keeps
  only the description, in memory.
- **Turns.** A turn sent while the camera is shared says `camera_shared: true`. It carries no image.
  - The chat, context and job routes all take the newest glance if it is under 30 s old. A live turn waits up to
    2 s for it; a typed turn waits up to 8 s.
  - The description joins that turn's context as untrusted `camera` content, and is saved as `camera_snapshot`.
  - With no fresh description, the model is told it cannot see the camera right now. There is no filler.
- **Unprompted turns (owner request, 2026-11-21).** The companion may speak up about what the camera shows.
  - A shared camera is a reason for the quiet-call turn, like fresh desktop context (`ambient_visual_presence`). The
    same idle threshold, cooldown and hourly cap apply; there is no polling loop of its own.
  - Just before such a turn, the web glances and sends `camera_shared=true` to `.../live-call/greeting/stream`.
    Task reports, open loops and scene lines don't carry it.
  - The server waits up to 8 s for the description and adds it to the prompt as untrusted content
    (`chat.camera_share.proactive_seen` v1). The prompt allows one specific thing worth a word, never the person's
    appearance, body or health, and the model may still answer SKIP.
  - If the camera alone was the reason and nothing was seen, the turn ends with `ambient_camera_unseen` and no
    model call. With another reason, the model is told it cannot see (`chat.camera_share.proactive_unseen` v1).
  - The description isn't saved with an unprompted line: its delivery is built from what the web sends.
- **Call start (owner request, 2026-11-21).** The web glances as the call starts (`ASSISTANT_LIVE_VOICE_CALL_START_EVENT`),
  while it connects. The generated greeting sends `camera_shared=true` and waits up to 2 s for that look
  (`GREETING_WAIT_SECONDS`). Only a look that saw something adds `chat.camera_share.proactive_seen` to the greeting
  prompt; with nothing seen, the greeting is unchanged. The first turn reuses the same glance while it is fresh (30 s).
- **Vision unavailable.** If vision is unavailable or remote without consent, the glance says so, and the web
  turns the share off with the reason.
- **Known limit.** As with Show, sharing is the person's own act, so it does not need the `camera` grant. The
  `look` instructions still speak of Show only.

## 5. Several characters in one call

**Where it stands today.**
- A chat session has one `character_id`. The call's voice, portrait, memory, grants (`owner_of(session)`) and
  pending proposals all follow it.
- Memory extraction runs per session from `chat.turn.completed`, using the session's character
  (`chat/persistence/chat_runtime.py`).
- There is no group chat. The RPG's NPC conversation code is prior art for speaker turns.

**Design.** The session's `character_id` stays the scene's *host* (the character the session was opened with), so
every normal session and every caller of `character_id` is unchanged. A scene adds guests. Every per-character
decision reads the reply's *speaker*, which is the host when there is no scene.

**Work packages.**
- 5.1 Scene model.
  - A new table `chat_session_scene_members (session_id, character_id, position, joined_at)`:
    - session FK with cascade delete;
    - character FK to `omnix_characters`, with `ON DELETE CASCADE`;
    - at most 2 guests, so 3 characters in all;
    - the workspace row-level security of migration 0106.
  - It needs a forward migration and the repository code.
  - Each assistant message records `speaker_character_id` in its metadata. When it is absent, the speaker is the
    host.
  - A helper `speaker_of(session, message)` is the one place that resolves it. Past messages from a removed
    guest still show the name stored on them, since sessions are soft-deleted and the cascade rarely fires.
  - Routes to add and remove a guest.
  - PG tests (cascade on character delete, RLS, the guest limit).
- 5.2 Per-speaker identity.
  - Grants: `owner_of` takes the speaker.
  - Pending governed proposals are bound to the speaker who proposed them.
  - Voice and portrait are resolved per reply from the speaker.
  - Memory: `chat.turn.completed` carries `speaker_character_id`, and extraction writes to that speaker's scope.
    The person's own statements are attributed as today.
  - Tests that no speaker reads another's memory, grants or secrets.
- 5.3 Prompts.
  - Each speaker's prompt has its own persona, memory and grants. The shared scene transcript is included with
    speaker labels, as data: another character's lines are quoted, never presented as the speaker's own.
  - Another character's memory and secrets are never in it.
- 5.4 Who speaks next, decided in code.
  - After the person speaks, a character they named answers (the roster's own names, matched in their words).
    Otherwise the character who spoke last answers.
  - After a character's reply, a short director call (the call model, one word, like the overlap judge) may
    propose one other character to react. Code accepts only a roster member who is not the one who just spoke.
  - At most two character turns follow one person turn, before the floor returns to them.
  - The person's speech always stops the chain.
  - Unit tests of the floor.
- 5.5 Voice and portrait.
  - The TTS lane resolves the voice per reply.
  - The portrait shows the current speaker; the others show their still image.
  - Measure the cost of switching the portrait session before choosing between one shared portrait session and
    one per character. Write the numbers here.
- 5.6 Web.
  - "Add to call" from the character list during a call.
  - Speaker names in the transcript.
  - Per-speaker portrait tiles.
  - Regenerate the OpenAPI spec and the generated client.
- 5.7 Real-call check with two characters: turn-taking, interruptions, voices, latency.

**As built (5.1-5.6), where it differs from the design above.**
- 5.1. The table is `omnix_chat_scene_members (workspace_id, session_id, character_id, seat, joined_at)`
  (migration 0197). `seat` is 1 or 2 and unique per chat, so the cap is a constraint: two adds racing for the
  last seat leave one guest in it (PG test). A guest leaves with its character or its chat (cascade). Guests
  need a character chat and the PostgreSQL chat store; the routes are `GET …/scene`, `POST …/scene/guests`
  and `DELETE …/scene/guests/{character_id}`, refusing with `scene_full`, `host_is_already_in_the_call`,
  `character_not_available`, `scene_needs_character_chat` or `scene_needs_postgresql`.
- 5.2. There is no `owner_of(session, speaker)`. A guest's turn is generated from `speaking_as(session, scene)`
  (`conversation/scene.py`), a read-only copy of the session whose identity is the guest's, so the grants,
  memory scope, persona and voice that every existing caller reads are the guest's without changing them. Every
  save path refuses that view (`refuse_scene_view`), since saving it would move the chat to the guest. The reply
  records `speaker_character_id` and `speaker_name` (`stamp_speaker`), and the turn's memory goes to the member
  who answered.
- 5.3. Each member hears the others' lines as quoted text inside the person's turn, never as its own replies.
- 5.4. Code picks who answers: a member the person names, otherwise whoever spoke last. A reaction is open only
  right after one reply to the person, to someone else in the scene. The web asks for it once, within 4 s of a
  reply's audio ending and only once the floor is free (`POST …/live-call/greeting/stream?purpose=
  proactive_reengagement&initiative_reason=scene_reaction`). The server checks the opening, asks the call's
  model for one name (4 s, 80 characters), accepts only a listed member who is not the one who just spoke, and
  streams under `initiative_reason=scene_reaction:<id>` with its own lease. Anything else is a 409
  (`scene_reaction_unavailable`, `_not_due`, `_declined`), which the call treats as nobody reacting. A reaction
  has no cooldown, does not count against the social prompt cap, waits for no answer, and is suppressed while
  the call is quiet. The person speaking clears it. A greeting ending also asks once; the server refuses it as
  not due.
- 5.5. The speaker is the response header `X-Omnix-Scene-Speaker` (absent for the host). The audio controller
  takes that guest's voice from the runtime's `scene_guests` (cloned speaker first), else the call's own.
  Adding or removing a guest re-reads the runtime, so a new guest's first turn finds its voice. **Cost:** a
  different voice replaces the shared PCM session (`live_audio_session_replaced`), so each change of speaker
  pays a TTS session open before its first word. Not measured yet: 5.7 writes the number here. **Portrait:** the
  portrait server picks its image from the session, so a guest's turn still shows the host's portrait; the
  call panel names who is speaking instead. Per-speaker portrait tiles are not built (left for after 5.7).
- 5.3. A call with guests is never speculated: the speculation stream and its accept both answer 409
  `speculation_in_scene`, since a speculated reply is the host's and the floor may belong to a guest. A guest
  added between a speculation's start and its accept makes the accept a 409, which the call shows as an error on
  that one turn. A seat read that fails counts as guests.
- 5.3. A turn's scene rides on a copy of the session (`conversation/scene.with_scene`), never the session a store
  keeps in memory, so one turn's scene cannot leak into the next.
- 5.4. A reaction stream that fails before it streams (the task-report claim or the director raising) gives its
  lease back, so the next initiative need not wait out the 90 s TTL.
- 5.1. A guest must be one of this workspace's characters. The seat's foreign key ignores row-level security, so
  `scene.add_guest` checks it through the workspace-scoped character store (`resolve_member`), as a chat's own
  character is. A character id is global and never moves workspace, so the check cannot go stale. Chat may not
  read `omnix_characters` itself (AL016).
- 5.4. **Known limit:** a delivered reaction's text comes from the client, as for any proactive delivery, and is
  saved as that guest's line. It can only be written into the person's own chat.
- 5.6. The live chat panel and the full-screen call show "On this call": one chip per member, the
  speaker lit (`aria-current`), Remove on a guest, and an "Add to call" picker of the person's other active
  characters while a seat is free. Transcript rows, live and saved, name a guest's reply by `speaker_name`.

## 6. Characters talk to each other (added 2026-11-16)

**Ask (owner, 2026-11-16):** in a call with guests, the characters also talk to one another. It is a setting,
with how often they talk.

**Status:** plan, revision 4. Ready to build.
- Round 1 of the agent review (2026-11-16) is folded in: races, server-side enforcement, the memory pipeline,
  echo and the plumbing.
- Round 2 is folded in: start backoff, the delayed memory job, the floor port, the heard text, echo against the
  lease, and the attempts table.
- Round 3 (a confirmation check) is folded in: the normalized heard text, the memory field's place, one
  attempt per lease, which reason follows a reply, and the echo order.
- Next: build, then a review of the build (same process as items 1-5).

**Today (5.4):**
- After the person speaks, one member replies, and at most one other member reacts.
- `chat/scene.reaction_opening` allows exactly one reaction (`MAX_CHARACTER_TURNS_PER_PERSON_TURN = 2`), counted
  from the saved messages (`replies_since_person`).
- `scene_director.choose_reactor` asks the call's model for one name. Code accepts only a listed member who did
  not just speak.
- The web asks once, within 4 s of a reply's audio ending (`initiative_reason=scene_reaction`, source `scene`).

**Rules this keeps:**
- The model proposes a line and, among two or more candidates, who says it. Code decides whether a line is due,
  who may speak, when a thread ends and what is saved.
- The person always wins the floor: their speech cuts in at once, and a line that lands after their message
  is not a line (6.3).
- Off by default. Only inside a live call. The server has no live-call id (3.2), so like all initiative this
  rests on the client.
- The server works out depth, the anchor and attempts itself, under the lease: from saved messages and
  companion_activity's own state, never from the client.
- No speaker's prompt holds another character's memory or secrets (5.3). Another character's lines are quoted
  data.
- Character talk never feeds the person's profile: memory facts about the person, conversation readings, or
  open loops (Q7).

**Terms:**
- A *thread* is the run of character lines since the later of:
  - the person's last message;
  - a talk opener (6.4).
- Any other kind of message ends a thread: a task report, a social or ambient remark, or a greeting.
- *Max lines in a row* (`scene_talk_max_lines`) counts every character line in the thread, including the reply
  to the person.
  - So after the person speaks: one reply, then up to `max_lines - 1` more.
  - With talk off, the limit is 2, as today (one reply plus one reaction).
- One pure helper, `scene.thread_of(messages, scene) -> Thread | None`, defines:
  - `root_id`: the thread's start, either the person's message or the opener;
  - `anchor_id`: the last non-transient message, which is what the next line follows;
  - the lines, the last speaker and the start kind.
  - Every check uses it. "Anchor" always means `anchor_id`, per line; the thread as a whole is `root_id`.
  - `reaction_opening` becomes a use of it.
  - Before the person has spoken (`replies_since_person` is `None`), a thread can only start with an opener.

**Work packages:**

- 6.1 Settings.
  - Live profile (`conversation/live_profile.py`, both the profile and the Update model, `extra="forbid"`), plus
    OpenAPI and the generated client:
    - `scene_talk_enabled`: default off.
    - `scene_talk_level`: `rarely` / `sometimes` / `often`.
    - `scene_talk_attempts_per_hour`: `null` (the level's number) or one of 6 / 12 / 24 / 48, chosen from a list
      like the other options (owner, Q10);
    - `scene_talk_max_lines`: default 4, 2-8 (Q11);
    - `scene_memory_per_character`: default 5, 0-20; the most memories about one present character in a
      prompt (Q12).
  - Levels (the defaults, to tune in 6.9):

    | Level | Silence before a start | Talk attempts per hour, per account |
    |-------|------------------------|-------------------------------------|
    | rarely | 90 s | 6 |
    | sometimes | 45 s | 12 |
    | often | 20 s | 24 |

  - The talk settings are global (Q14). They live in the profile's defaults only, and the effective read takes
    them from the defaults even when a chat has its own override. The per-chat override model does not carry
    them. They are edited where quiet hours and the hourly cap are edited today.
  - `initiative_mode=off` or `max_initiatives_per_hour=0` blocks starts (6.4), not the thread after the person
    speaks.
  - Quiet hours are known only to the client, which holds back starts and further lines during them. The server
    enforces on/off, the level and the cap.
  - Per-call switch "Let them talk" in "On this call":
    - shown only when the effective setting is on;
    - starts on each call;
    - kept beside `companionQuiet` in `live-call-presentation-store.ts`.
    - Off stops threads and starts. The single 5.4 reaction stays. The switch can only narrow the setting, so it
      stays on the client.

- 6.2 Attempts and declines, on the server.
  - Store: a new table `omnix_companion_scene_talk_attempts`, owned by companion_activity, with its migration in
    `companion_activity/migrations/`. It does not go on `omnix_companion_initiative_sessions` (0082), which has
    no account column and no history.
    - Columns: `attempt_id` (the intent/lease id, PK), `user_id`, `session_id`, `anchor_message_id`, `kind`
      (`reaction` / `line` / `start`), `outcome` (`streamed` / `declined` / `skipped` / `failed`),
      `streamed_text` (at most 240 characters), `next_start_after`, `created_at`, `finished_at`.
    - Index `(user_id, created_at)` for the cap.
    - Partial unique index `(session_id, anchor_message_id)` where the kind is `reaction` or `line` and the
      outcome is `declined`, for the closure.
    - No RLS, like the module's other tables (0081/0082). Rows older than 24 h are pruned on write.
  - Written in the same `_locked_postgres_state` transaction as `acquire`. `InitiativeAcquireRequest` gains
    `user_id`, `anchor_message_id` and `kind`. The in-memory authority does the same, with parity tests.
  - The route reads and writes it only through the initiative authority, as for leases, so there is no AL016
    issue.
  - One attempt per lease: the row is inserted at `acquire`, and its outcome is updated in place (director, then
    stream). The hourly cap (`scene_talk_attempts_per_hour`, or the level's number when it is `null`) counts `line` and `start` attempts
    per account, not deliveries, because model calls are the cost.
    - The count and the insert run under `pg_advisory_xact_lock(hashtext(user_id))`, so two chats on one
      account cannot both pass. The in-memory authority uses one lock per account.
  - Which reason follows a reply:
    - with talk on, the client always asks `scene_line`;
    - `scene_reaction` is used only when the setting is off, or the per-call switch is off. A switched-off
      client sends `scene_talk_switched_off=true`; the flag can only narrow;
    - the server refuses `scene_reaction` with a 409 when the setting is on and that flag is absent, so the
      first ask cannot pick the uncapped reason.
  - A 5.4 reaction (`kind=reaction`) is recorded and closes its anchor on a decline, but does
    not count toward the talk cap. With talk off, its behaviour is unchanged otherwise.
  - Declines:
    - a `line` or `reaction` declined (SKIP or "nobody") closes its anchor for good. A later ask at the same
      anchor gets a 409 `scene_talk_closed`, so a client loop cannot rerun the director;
    - a `start` declined sets `next_start_after = now + 2 × the level's silence` on its row. Until then a start
      gets a 409 `scene_talk_backoff`. A silence does not move the anchor, so closing it would stop all
      spontaneous talk until someone spoke.

- 6.3 Races, the lease and the person cutting in.
  - The opening is worked out **after** `authority.acquire`, from the session reloaded under the lease. Today
    `_checked_initiative_materials` runs on the session loaded at the start of the request (`routes.py`).
    Reactions get the same fix.
  - The lease-bound turn id carries the anchor: `scene-line:<anchor_message_id>:<nonce>` and
    `scene-talk:<anchor_message_id>:<nonce>`.
  - Commit (`commit_proactive_delivery`):
    - derives `scene_talk_started` and the speaker from that turn id, as `raised_open_loop_id` is derived today,
      never from the request;
    - saves a line whose anchor is no longer the last non-transient message as transient. That line is not a
      line, gets no memory and does not count. This is the backstop for when the floor port (below) is missing
      or fails.
  - The person takes the floor: a new chat port, following the `CHAT_CALL_ACTIONS` pattern.
    - `CHAT_FLOOR: Port[ChatFloor]`, `at_most_one`, declared in `platform/chat/contracts.py`. Its methods:
      - `person_took_floor(session_id, user_message_id) -> None`;
      - `active_scene_line_text(session_id) -> str | None` (for 6.5).
    - Contributed by the `character-interactions` feature (`apps/character_interactions/feature.py`), which
      already depends on chat and companion-activity. companion_activity gains no chat dependency.
    - Backed by a new locked authority method, `finish_owner(session_id, owner="scene", delivered=False)`, so
      there is no read-then-finish race on the lease id.
    - Chat calls it once, after the person's message commits, from the single live/streamed user-message commit
      site, not from each store's `append_user_message`. It is best effort (`optional(CHAT_FLOOR)`): absent or
      failing means no-op, and the TTL and the anchor check remain the guarantee. Not an outbox event, which
      would land after the client's next ask.
    - A commit on a lease finished this way gets today's 409 `initiative_lease_inactive`, and the client drops
      the line. The normal barge-in path still commits the interrupted line before the person's transcript is
      saved (`handleInterrupt`); only the rare race loses it.
  - The streamed text:
    - the line stream stops at 240 characters, so what is recorded is exactly what was emitted;
    - at stream end, the authority records it on the attempt row (`streamed_text`);
    - commit saves the recorded text, never the client's. The client also sends `heard_text`: the phrases the
      delivery ledger (`live-voice-delivery-ledger.ts`) played before the interrupt;
    - the ledger trims and space-joins phrases, drops unspeakable ones, and carries tags separately. So before
      the prefix test, both sides are normalized the same way: tags stripped with the server's tag parser,
      non-speech runs dropped, whitespace collapsed;
    - a normalized prefix is stored on the message. On a mismatch the line is still saved, with
      `heard_text=null`, and memory takes nothing from an interrupted line whose heard text is unknown. No 422;
    - The web sends `interrupted_at_phrase` as well, from the ledger.
    - For scene lines and reactions, that ends the known limit "the delivered text comes from the client" (5.4).
  - Reading the reply: `_reply_to` (`assistant_memory/conversation_reading.py`) takes the first assistant
    message after the person's message. It now skips transient messages and messages from a speaker other than
    the one who answered, so a character line is never read as the reply.
  - The web gives back the lease on `clearPending` (a line cancelled before playback), through the existing
    finish path with `delivered=false`. Today it holds until the 90 s TTL.

- 6.4 Who speaks and what.
  - After a line is delivered and its audio ends, the client asks for the next line (`scene_line`):
    - only after `commitPending` has resolved;
    - with the tab visible, and not Quiet, Mute or quiet hours.
  - The server checks all of these before a line is due:
    - the thread is under its max;
    - the anchor is not closed;
    - the cap is not reached;
    - the setting is on and a guest is on the call.
  - Speaker: the members other than the last speaker. With one candidate there is no director; the line model
    is called directly, and its SKIP means nobody. With two candidates, the director gets a new template that
    sees the thread's last lines, not only the last one. The current template is biased to "no" and sees one
    line.
  - Start (`scene_talk`): allowed only when all of these hold:
    - the setting is on, not `initiative_mode=off`, and `max_initiatives_per_hour > 0`;
    - the floor is free;
    - the last message of any kind, transient included, is older than the level's silence, measured on the
      server from its time. So a start never lands right after a social remark;
    - no start backoff is running (6.2);
    - the cap is not reached.
  - The opener's speaker: the member who did not speak last, or the director with two candidates. The
    director names a speaker only. It writes no topic, so free model text never feeds another prompt.
  - Precedence on the client:
    - a task report goes first and ends the thread;
    - a due social remark to the person goes before a start;
    - a start counts as activity (`lastActivityAtMs`) and spends no social prompt;
    - `evaluateSceneReaction` also gains the tab-visibility check.

- 6.5 Echo.
  - In a scene chat, a person's message is compared with any character's speech (reply, reaction, line or
    opener):
    - the active `scene*` lease's recorded text, read through `CHAT_FLOOR.active_scene_line_text`. A line heard
      "during" playback is not committed yet;
    - the last committed character message whose time is within about 2 s.
  - A close match (token overlap, threshold set in 6.9) is tagged `suspected_echo`. Chats without guests are out
    of scope.
  - Order at the commit site:
    1. read `active_scene_line_text`;
    2. save the person's message with its tag;
    3. call `person_took_floor`, because finishing the lease ends what the read can see.
  - It is still answered, but the memory job and `record_turn` (conversation readings) skip it.
  - Measured in the real call (6.9). "Only respond to me" (2.4) reduces it.

- 6.6 Memory: characters remember each other (Q7). This is a new pipeline, not a filter. Today extraction runs
  only on `chat.turn.completed` (one per user message) and reads only the user message. The structured
  extractor says "Nothing the assistant said is a fact about the user".
  - Event:
    - a chat outbox event `chat.scene_line.delivered` per committed, non-transient scene line, keyed by message
      id;
    - it carries the speaker, the members present, `memory_writes_allowed`, and the heard text (6.3).
  - Consumer:
    - an assistant_memory consumer and job type;
    - it honours `automatic_memory_derivation_allowed` and `write_memory`;
    - each line event enqueues a job keyed by its message id, with `available_at = now + 60 s` (the job store's
      `available_at`);
    - when the job runs, it reloads the session and runs `thread_of`. If a later line exists in the same thread
      (same `root_id`), it does nothing. Otherwise it extracts the thread's lines after the last one already
      extracted. The extraction is keyed by `(root_id, last line id)`, so a rerun is idempotent and lines that
      land after an earlier job ran are still extracted;
    - so there is one effective job per thread, with no close detection. Abandoned threads (call end, tab
      hidden, switch off, a failed stream, the TTL) are extracted too.
  - What is learned (owner, Q9: keep more than self-statements). From speaker S's lines, each other present
    member L may learn:
    - what S said about S, with subject S;
    - what S said about another character C (present or not), with subject C. It is kept as S's claim
      ("Mara says Bea is afraid of storms"), with lower confidence than a self-statement, and C's own word wins
      when the two disagree;
    - trust `assistant_inference`, never `user_explicit` or approved;
    - nothing S says about the person is kept. Q7 stands: character talk never feeds the person's profile, and
      the person's own words are the only source about the person;
    - the record text names the character ("Bea is afraid of storms"), never "I" or "she", because curated
      assertions render their own text.
  - New extraction prompt template and its golden.
  - Representation:
    - the job writes through the same automatic path as today's extraction (memory is on for all, so no
      approval queue). If it turns out to write candidates, the column goes on `omnix_memory_candidates`
      instead;
    - a typed optional `about_character_id` on `MemoryRecord`, plus OpenAPI and the client. It needs no
      migration: curated records live as `payload.memory_record` on v2 observations (`v2/curated_records.py`),
      and `omnix_memory_records` is the retired v1 table;
    - `MemoryRecord` is `extra="forbid"`, so code from before the change cannot read a payload that carries the
      field. Fine for a forward-only release;
    - the v2 graph already stores the subject in columns (`subject_entity_id`, `subject_entity_type`, 0070),
      so v2 needs no migration. `v2/curated_projection.py` maps the field to
      `GraphEntityRef(entity_type="character", entity_id=<character id>)` instead of the hard-coded `profile`
      subject. Without this, "Bea is afraid of storms" becomes a fact about the person.
  - Filters:
    - **prompts:** a memory about a character is included only while that character is on the call
      (`scene_of(session)`, at render time, not when the snapshot is made); the newest
      `scene_memory_per_character` (default 5) per present character.
      - The filter goes into the retrieval itself (`RetrievalQuery` gains the present characters), not after
        it, so absent characters' records do not use up the `top_k=12` slots in `_resolve_v2_prompt_memory`.
      - Pinned records go through the same filter;
    - **open loops:** `read_session_open_loops` and `live_call_open_loops.open_loop_material` take only
      person-subject items, or 3.2 would raise Bea's storms with the person;
    - **understanding:** the "known" input of the conversation readings takes only person-subject items;
    - **Memory tab:** about-character memories are grouped under the character.
  - No automatic deletion. The prompt cap above limits drift, and the Memory tab edits or deletes.

- 6.7 Plumbing for the two new reasons, `scene_line` and `scene_talk`.
  - Turn-id prefixes (6.3).
  - The reason↔turn-id validator of `ProactiveDeliveryRequest`, and `reacting_member`.
  - `_proactive_initiative_policy`, `_checked_initiative_materials`, `_check_materials`, `may_skip`,
    `skip_reason` and `_stamp_reaction`.
  - Prompts, with the golden regenerated:
    - a line to another member: short, 1-2 sentences, 240 characters, never speaking for the person, who is in
      the room;
    - the talk opener;
    - the thread director;
    - the extraction prompt (6.6).

- 6.8 Web.
  - The chain: ask for the next line after the commit; the person speaking cancels, clears and gives the lease
    back.
  - The silence timer for starts.
  - The per-call switch in `LiveCallScene`, and the settings in the call settings panel.
  - The transcript names each speaker (as in 5.6).

- 6.9 Checks. Tests:
  - two asks at the same depth: one line;
  - a line committed after the person's message is saved transient and gets no memory or reading (port
    absent), or is refused with 409 (port present);
  - a person's turn and `clearPending` give the lease back;
  - `_reply_to` skips a transient line and another speaker's line;
  - a re-ask after a declined line gets 409 `scene_talk_closed`; a start after a declined start gets
    `scene_talk_backoff` until it expires, then is allowed;
  - the cap counts attempts per account, across two chats at once, in PG and in memory;
  - the attempts migration, and in-memory parity with PG;
  - commit stores the recorded text; a tagged line and a multi-line line give the right `heard_text`; a
    mismatch saves `heard_text=null` and memory skips it;
  - the server refuses `scene_reaction` while talk is on;
  - a claim about another character is kept with subject C and lower confidence; a claim about the person is
    not kept;
  - the talk settings are read from the defaults even when a chat has an override; `attempts_per_hour` and
    `scene_memory_per_character` are honoured;
  - echo is tagged against an active lease's text and against a line committed within 2 s;
  - an echo-tagged turn is skipped by memory and readings;
  - the memory job: a later line makes the earlier job a no-op; an abandoned thread is extracted once; a line
    after a job that already ran is still extracted;
  - retrieval with the presence filter, including pinned records;
  - the projection subject of an about-character record;
  - open loops and the understanding input leave out about-character items;
  - the prompt includes Bea's memories only while Bea is on the call;
  - the Memory tab groups about-character memories under the character;
  - the web chain waits for the commit, sends `heard_text` and `interrupted_at_phrase`, and the switch resets
    each call;
  - the prompt golden;
  - architecture lint and metrics after staging.
  - Real-model check on Haiku low:
    - threads end sensibly;
    - lines stay short and in character;
    - no character speaks for the person;
    - extraction keeps only self-statements.
  - **Owner:** a real call with two characters, with 5.7: the echo rate and the latency per speaker change.

**Risks:**
- **Cost.** Per line: one line call, plus a director call with two guests. Per thread: one extraction call. The
  cap counts attempts.
- **Speaker-change latency.** Each change reopens the TTS session (5.5, not measured yet).
- **Echo** (6.5).
- **Size.** 6.2 adds a migration. 6.3 adds a chat port. 6.6 touches assistant_memory, its
  retrieval, its v2 projection and the Memory tab. This is the largest item on the roadmap.

**Owner decisions on the defaults (2026-11-16, Q9-Q14):** see "Owner decisions" below.

**As built (6.1-6.9), where it differs from the design above.**
- 6.2. Migration 0198 (`omnix_companion_scene_talk_attempts`) has one row per attempt (`reaction`, `line` or
  `start`), keyed by the attempt's lease. It is pruned after a day. A declined or skipped line closes its
  anchor, and a declined or skipped start sets `next_start_after` for its chat. The index on closed anchors is
  not unique, though the plan asked for a unique one. The closure check runs under the session row lock and the
  account's advisory lock, so a unique index would add nothing.
- 6.4. The commit checks the anchor before the append, outside the append's lock. It checks again on what the
  append saved (`_demote_if_late`), so a line whose commit raced the person's message is marked an aside
  before memory hears of it, even when the floor port did not fire.
- 6.3. The chat port is `SceneFloor` (`character_interactions/floor.py`). Its parts:
  - `person_took_floor` is called when the person speaks;
  - `active_scene_line_text` is the server's text for the commit check.
- 6.4. A dropped scene turn gives its lease back early through a new route, `POST …/live-conversation/proactive/release`
  (body `{turn_id}`, returns `{released}`), instead of waiting out the TTL. A turn id that is not a scene id gets
  a 422. The web posts it when a scene line is dropped before it plays.
- 6.5. The delivery commit takes `heard_text` and `interrupted_at_phrase`. The web takes them from the delivery
  ledger (`deliveredHeard`, `readLastProactiveTurnHeard`), which also holds the snapshot of what was heard.
  Transcript rows already named the speaker (5.6), so nothing new was needed there. Memory reads an
  interrupted line only through its heard text. When that text is null or blank (a mismatch, no heard text
  sent, or no phrase finished), memory takes nothing from the line. **Known limit:** the web's heard snapshot is
  keyed by chat, not by turn id. With one proactive turn in flight it is right, and a wrong snapshot is a server
  mismatch, which memory then skips.
- 6.6. Several changes from the design:
  - **The subject type is `about_character`, not `character`** (`v2/contracts.CHARACTER_SUBJECT`). A conversation
    reading already files the owner's own side (stance, promises, jokes) under subject type `character`, id
    `character:<owner>`. With `character`, the person-only and present-character filters dropped the owner's
    own stance from every chat. A PG regression test pins this.
  - Memories are written through `create_heard_memory`.
  - The present characters and the per-character limit come through the `SCENE_MEMORY_CHARACTERS` port
    (`floor.SceneMemoryCharacters`).
  - The "known" section was already person-only.
  - The extraction job is listed in the prompt registry as `scene_memory`.
  - **Known limit:** the line-delivered event is written in its own unit of work after the message append. A
    crash between the two loses that thread's memory job, and nothing else depends on it.
  - The about-character filters in `understanding_view.py` are a second guard. The retrieval filter is the
    first. The affect observations query has no subject column and is left as it was.
- 6.7. The Memory tab groups memories about another character under that character by `about_character_id`. It
  takes the names from `characterClient.list(true)` and shows a removed character by its id. The switch on the
  call is `sceneTalkOn` in the presentation store, and it resets when a call starts.
- Plumbing. Cross-feature imports go through `contracts`:
  - `chat.contracts` exports `resolve_member` and `thread_of` lazily;
  - `floor.py` imports from `characters.contracts`.
- 6.9. Results:
  - Python suites pass (PG on a scratch DB): companion_activity, assistant memory v1 and v2, call scene, call
    open loops, character_interactions, curated v2, understanding and scene members, and prompts.
  - Web suites `live-call-scene` (17), `LiveCallScene`, `CharacterMemoryPanel` (11) and
    `LiveConversationControls` pass, as do typecheck and the build.
  - Architecture lint and metrics show no new findings. AL011 (`persistence/cli.py`), AL015 ×2, 3 inline
    prompt strings, `_VOICE_SPEAKERS` and one unbounded cache are all equal to HEAD.
  - Ruff's 7 errors are also present at HEAD.
  - Real-model check on Haiku low done 2026-11-23 (B1 of `LIVE_CALL_IMPROVEMENTS_2026-11-23.md`): it found
    that no quiet call ever started talk, and talk director v2 fixed it. The owner's two-character call
    (with 5.7) is still to do.

## Owner decisions (2026-11-15)

- Q1 (item 1): call research skips plan approval (see 1.1). **Keep it.**
- Q2 (item 2): the voiceprint embedding is **stored in the database**, per account, with Delete.
- Q3 (item 3): the companion **never starts a conversation outside a call**. Initiative stays inside calls.
- Q4 (item 4): snapshots keep **only their descriptions**. The image is never stored.
- Q5 (item 6, 2026-11-16): characters talk **both** after the person speaks and on their own during silence.
- Q6 (item 6): the settings live in the **call settings** (next to quiet hours), with an on/off switch for the
  current call in "On this call".
- Q7 (item 6): characters **remember each other** from their talk. It never feeds the person's profile.
- Q8 (item 6): same process as items 1-5 (agent reviews of the plan, build, agent review), in a **new session**.
- Q9 (item 6, 2026-11-16): characters keep **more** than self-statements: also what one character says about
  another, kept as that speaker's claim. Nothing said about the person (Q7).
- Q10: talk frequency is a level (rarely / sometimes / often) plus a configurable **attempts per hour**, chosen
  from a list.
- Q11: max lines in a row: default 4, configurable.
- Q12: memories per present character in a prompt: default 5, configurable.
- Q13: an echo turn is still answered but never remembered.
- Q14: the talk settings are **global** for now, not per chat.
- Q15 (group calls, 2026-11-19): when the person names no one, the call's model **picks who answers first**
  (up to 2.5 s; any failure falls back to the last member to speak, else the host). A member the person names
  still answers deterministically.
- Q16: a call seats up to **four guests** besides its host, five characters in all (migration 0199).
- Q17: characters talk to each other **on by default** (was off).
- Q18: lines in one exchange: default **6**, configurable **up to 10** (replaces Q11's default of 4).
- Q19 (follows from Q15-Q18): the lines that answer the person's message do **not** use up the hourly talk
  attempts. They are still bounded by the line limit and by a declined or skipped line. Quiet-call starts and
  the lines of a talk the characters started still count (migration 0200, `counted`).

## Status log

- 2026-11-15: plan written; 1.1 started.
- 2026-11-15: 1.1 done (uncommitted, worktree `omnix-companion`, branch `companion-live`). Design moved from a
  `[task: …]` tag to the existing call-ability protocol. Call, chat, research and stream suites pass (PG ones
  on a scratch DB).
- 2026-11-15: plan reviewed by an agent over three rounds. Round 1: the Live Agent planner is Kasa-only, and
  stale or speculated confirmations were possible. Round 2: no conditional claim, and the report/confirm
  order. Round 3: the job grant must be unapproved, plus the voice binding. All folded into the WPs. Owner
  answered Q1-Q4.
- 2026-11-15: 1.2 done. The asking reply records each start (`start`, `job_id`); `GET/POST …/live-call/tasks`
  list and cancel. Found on the way: on PostgreSQL a streamed reply carried no `reply_to_message_id` (now set
  at the one commit point, `_commit_chat_reply`), and a background append raced a live commit and failed as
  "changed after it was loaded" (now under the session row lock). The PG race test fails without the lock.
- 2026-11-15: 1.3 done. `GET …/live-call/initiative-candidate` names the oldest settled, unreported task. The
  report stream checks it again on the server (409 `task_report_not_due` otherwise), builds its prompt from the
  task record (the call's reason never reaches it), takes a `task` lease (high, 4 s), stops at 3 sentences or
  600 characters, and the delivery commit derives `task_report_for` from the lease-bound turn id. Live prompts
  see a task's result as a stub. Two prompt templates added (golden regenerated).
- 2026-11-15: 1.4 done. `live-call-tasks-controller` reads the task list when the call connects, after each
  reply and after a delivered report, and every 5 s while a task is open. One chip per open task, with Cancel,
  in the voice card, the full-screen call and the panel. The initiative controller asks `initiative-candidate`
  (at most every 5 s) while a settled task awaits its report, and speaks only a `task_report:` reason the server
  names. A report goes first, waits only for the floor, gets 3 tries per call, and does not count against the
  social prompt cap. Assistant web suite (990 tests), typecheck, lint and build pass.
- 2026-11-15: 1.5 done. `voice_actions` types the five voice capabilities; `chat.live_call_action` jobs run reads
  under an unapproved chat grant and turn writes into proposals (device resolved to one id, question first).
  `claim_message_metadata` (PG and in-memory) stamps `report_started_at` and claims `pending → executing` once;
  confirmability is worked out on reading (first later message, 2 min, `heard_turn_id` for voice). The call's
  Confirm/Cancel buttons post `…/live-call/tasks/{task_id}/decision` (409 `proposal_decided` when already
  answered). Speculation is refused while a proposal is confirmable. A "cancel"/"no"/"yes" said over or after the
  question is answered by the server's overlap route (`proposal_answer_only`), not a web word list. Chat reaches
  the assistant tools through a new `CHAT_CALL_ACTIONS` port (ADR-0016: chat must not import them); the two
  availability caches are bounded and listed in the process-local inventory. Python suites (app, chat,
  live_voice, assistant_tools, research, character_interactions, the two PG integration tests), assistant web
  suites, typecheck, lint, build and architecture lint/metrics (equal to HEAD) pass.
- 2026-11-15: 1.6 done except the local-model run. The per-turn prompt lists the call's tasks from their records
  (`live_call_tasks.call_tasks_prompt`: running for how long, finished and told or not, a proposal waiting,
  done, cancelled or unanswered), even when the ability was withdrawn mid-call; a turn without tasks reads no
  jobs. Real-model check on Haiku low: 40/40 after the long-question parser fix (see 1.6).
- 2026-11-15: 2.1 done. `platform/voice/voiceprint.py`: `GET/POST/DELETE /api/stt/voiceprint`, a document per
  account (module `live-voice`, type `voiceprint`), 2-5 passages of 3-20 s, refused when quiet or when the
  passages do not sound like one voice; guests cannot enrol; no audio kept, the print never logged or returned.
  "Learn my voice" panel in the call settings (`LiveVoiceprintPanel`), three passages recorded as 16 kHz WAV.
- 2026-11-15: 2.2 done. The STT proxy sends the account's `speaker_profile` before the browser's `hello` and
  drops one from the browser. The Nemotron service warms TitaNet for the call and scores each final of 0.8 s
  or more in a worker thread, sending `speaker_score` after the final. The web logs it (`stt_speaker_score`).
- 2026-11-15: 2.3 tooling done; the measurement waits for the owner. `scripts/voiceprint_threshold_eval.py
  --enrol DIR --clips DIR` enrols from the owner's passages, scores 2 s segments of labelled clips (labels
  starting `owner` are the owner; others `tv`, `other`, `owner_over_tv`, ...), and picks the threshold that
  rejects at most 1% of the owner's segments, with false accepts per label. It warns under 100 owner segments.
  **Owner to do:** record the labelled set and run it; write the numbers here before the setting may default on.
- 2026-11-15: 2.4 done, default off. "Only respond to me" toggle in the voiceprint panel (shown once enrolled).
  `live-voice-speaker-gate.ts` holds the call's scores and the held finals. A final in another voice is held:
  greyed in the transcript as "Another voice" with "Send anyway", no speculation final (the settled event
  cancels it), and any deferred interruption dropped. See "As built" in §2 for the deviations. Web suite
  (3,108 tests), typecheck, build and architecture lint pass.
- 2026-11-15: 3.1 done. The call logs held no initiative data (perf events never reached the reporter). Now they
  do: decisions only when they change, plus generation, skip, delivery, answered and ignored. Reason paths and
  patterns are listed in §3.
- 2026-11-15: 3.2 done. `initiative-candidate?social=true` names an active `open_loop` from the speaker's own
  memory (none for private-transcript or memory-off chats). The stream route checks it again, binds the turn id
  `open-loop:<key>:<nonce>` to the lease, and puts the loop's text in the prompt, capped at 240 characters. The
  delivery records `raised_open_loop_id`. A loop is not raised again within 12 h.
- 2026-11-15: 3.3 done. Quiet button on the call; quiet hours and an hourly cap in the live profile (OpenAPI
  and the generated client regenerated). Answered/ignored redefined, and an ignored reason cooled for the call.
  A skip sets the cooldown. Controller-level test `live-conversation-social-initiative.test.ts` (9 cases).
  3.4 deferred until there is data (see §3).
- 2026-11-15: 4.2 done. `chat/live_call_camera.py`: `SendChatMessageRequest.camera_image` (JPEG/PNG/WebP data
  URL, size-capped, excluded from serialisation) is described by the desktop vision client with the remote-consent
  check, under an 8 s timeout, and dropped. Prompt template `chat.live_call_camera.question` v1 (golden
  regenerated). `test_live_call_camera.py` (11 cases, PG).
- 2026-11-15: 4.3 server done. Ability `camera` (off by default), verb `look`, `camera_request` event,
  `GET …/live-call/camera` (OpenAPI and the generated client regenerated). `test_call_camera.py` (8 cases);
  `test_call_abilities.py` updated for the new ability.
- 2026-11-15: 4.1 and the 4.3 web part done. `workspace/live-call-camera.ts` store and `chat/LiveShowButton.tsx`.
  The speculation controller refuses a turn with a picture, and the context route is skipped for it.
  `live-call-camera.test.ts` (13 cases) and `LiveShowButton.test.tsx` (5). See "As built" in §4.
- 2026-11-15: 5.1-5.4 server done. Migration 0197 (`omnix_chat_scene_members`), `chat/scene.py`,
  `scene_director.py`, `scene_routes.py`, `persistence/scene_repository.py`, `conversation/scene.py`.
  `test_call_scene.py` (24 cases) and `test_chat_scene_members_integration.py` (3, PG). OpenAPI and the
  generated client regenerated. See "As built" in §5.
- 2026-11-15: 5.5 and 5.6 web done. `workspace/live-call-scene.ts` (members store, voice by speaker),
  `chat/LiveCallScene.tsx`, the reaction path in the initiative controller (source `scene`), speaker names in
  the transcript. Tests: `live-call-scene.test.ts` (9), `LiveCallScene.test.tsx` (6), a guest-voice case in
  `live-voice-unified-audio-controller.test.ts`. **Owner to do:** 5.7, a real call with two characters.
- 2026-11-16: implementation reviewed by an agent. Fixed, each with a regression test:
  - A call with guests could be speculated as the host's reply (now a 409, see 5.3).
  - The scene was set on the stored session and could carry into the next turn (now a copy).
  - A reaction that failed under its lease kept it for 90 s (now given back).
  - A live-call task or proposal ran on the chat's grant, not on the speaker's. The task and the proposal now
    record their speaker (`owner`), a task starts only while that speaker holds the ability, and Confirm runs a
    proposal only while its speaker still holds the capability; otherwise "Nothing was changed."
  - The model's own query went into system notes unwrapped (now delimited as data, `<<<…>>>`).
  - Workspace scoping of guests was verified (see 5.1). A PG test pins both halves: the character store does not
    see another workspace's character, and the seat table alone would take it, so the store check must stay.
  - Earlier in the same pass: the seat read is limited in SQL, the Show button's background uses a theme token, the
    voiceprint panel's timer was split out, and the long web test was split.
  Documented as known limits: Show ignores the `camera` grant (4.1); a reaction's text comes from the client (5.4).
- 2026-11-16: item 6 (characters talk to each other) added as a draft plan; owner answered Q5-Q8.
- 2026-11-16: item 6 plan review round 1: 15 findings (races, server-side caps and declines, memory had no
  trigger or subject field, echo, plumbing). All folded into revision 2.
- 2026-11-16: item 6 plan review round 2: 13 of 15 resolved or partly, 9 new points (start backoff, thread-close
  trigger, floor port vs transient, heard text, echo timing, anchor naming, retrieval filter, cap race, small
  gaps); store and port questions settled. All folded into revision 3.
- 2026-11-16: item 6 plan review round 3 (confirmation): two fixes (normalized heard text with no 422; the memory
  field on MemoryRecord, not the retired v1 table) and two clarifications, folded into revision 4. Reviewer:
  ready to build once those are in.
- 2026-11-16: owner settled the defaults (Q9-Q14); folded into revision 4.
- 2026-11-16: item 6 built (6.1-6.8, uncommitted, branch `companion-live`): migration 0198, the `SceneFloor` and
  `SceneMemoryCharacters` ports, the scene line and talk streams, the release route, heard text on the commit,
  the per-thread memory job (`scene_memory`), about-character memories (`about_character_id`, subject
  `about_character`), the web chain, start timer and "Let them talk" switch, and the Memory tab's grouping.
  See "As built" in §6.
- 2026-11-16: item 6 build reviewed by an agent: one blocker, one should-fix, three nits. Fixed, each with a
  regression test:
  - An interrupted line with unknown or empty heard text was read whole by memory. It now gives nothing.
  - A line whose commit raced the person's message could be saved as a line. It is now marked an aside after
    the append. The test fails without the fix.
  Added the missing 6.9 checks:
  - two asks at the same depth give one line;
  - a reading-shaped about-character row stays out of the understanding (fails without the filter).
  Open loops were already covered.
  Documented as known limits: the outbox write is not atomic with the message, and the heard snapshot is keyed
  by chat. The non-unique closure index is noted as a deviation.
  Results:
  - focused Python suites pass (PG on the scratch DB);
  - ruff on the changed files passes;
  - architecture lint shows AL011 and AL015 ×2, as at HEAD.
  **Still to do:** the owner's two-character call (with 5.7). The Haiku-low check ran 2026-11-23 (see 6.9).
- 2026-11-19: group calls (Q15-Q19, uncommitted on main):
  - Fullscreen gives every call member a tile: host and guests, with the speaker outlined. Layouts go up to five.
  - A first-speaker director (`chat.scene.first_speaker` v1) picks who answers first.
  - The thread director and line prompts (v2) now see what the person said. A character may give its own
    answer to a question put to everyone, or respond to another character. Not everyone has to speak.
  - Migrations 0199 (seat 1..4) and 0200 (`counted` on talk attempts).
  - The characterization golden `chat-live-sse-turn` was refreshed. It gains `heard_turn_id` and
    `reply_to_message_id`, both added by f453664542 (item 6); this change does not touch them.
  Results:
  - focused Python suites pass (PG on the scratch DB), as do the web tests, typecheck, build and ruff;
  - architecture lint shows AL011 and AL015 ×2, as at HEAD.
  **Still to do:** run the 0199/0200 migrations on the live DB, and the owner's four-guest call.
- 2026-11-19: group calls real-model check on Claude Haiku 4.5 (CLI), with a host and four guests over six turns:
  - The harness used the production scene code: first speaker, line opening (6-line limit), thread director,
    and the line prompt. Each character's system prompt was a short persona plus the real scene note.
  - Run 1: the thread director (old v2 wording) answered NONE after every reply, even after a question put to
    everyone, so nobody ever joined in.
  - Run 2: reworded. The talk happened, but nearly everyone piled on: "rough day" got five replies, and two
    exchanges hit the line limit.
  - Runs 3-4: restrained wording, now thread_director v2 and talk_line v2 (SKIP when one would only agree or
    echo). Results:
    - a question to everyone: all five answer, then some banter;
    - an opinion, a personal remark, or a line to one character: one or two lines;
    - goodbye: one reply.
  - Both directors now say "Reply with only one name ... and nothing else". Before that, Haiku sometimes began
    with prose, and the first line parsed as no one.
  - Latency: the first-speaker pick took 1.2 s on average (1.5 s at most, within the 2.5 s timeout); the
    thread director 1.1 s.
  - A scene line took 13-40 s to its first word: proactive turns never passed `live_turn`, so Haiku thought
    first. Every proactive turn (lines, reactions, initiatives, task reports) is spoken on a call, so it now
    passes `live_turn` when the provider declares LIVE_TURNS (only `claude_cli`). Lines now take 1.6 s on
    average.
  - Known limits:
    - The director sees only names, not who the characters are. It sometimes picks a character with nothing
      to add, whose SKIP then ends the exchange (Maya chosen on working from home instead of Daniel, who
      likes the office).
    - All five answering a question to everyone is more than the owner's example, which had three.
- Q20 (owner, 2026-11-19): the directors get a **one-line description of each character**, to pick who has
  something to add:
  - The line is the character's `description`, else its persona's first sentence, cut at a word near 160
    characters. `CharacterProfileSnapshot` now carries `description`, and `SceneMember.summary` holds the line.
  - Prompts quote it as data ("Who they are:"), as they do the lines: `chat.scene.thread_director` v3 and
    `chat.scene.first_speaker` v2. The thread director also now says that on an opinion, the one or two with
    the strongest view respond.
  - Real-model check on Haiku 4.5, runs 5-8 (harness personas as descriptions):
    - With Daniel described as liking the office, a work-from-home opinion got Maya, Daniel, Alex, then
      Daniel again, a back-and-forth; Leo and Sophie stayed quiet. Run 6, before the opinion sentence, had all
      five give a view.
    - Picks now fit who the characters are: Leo the chef took the knife-skills thread, and Alex the engineer
      took the side of hallway conversations.
    - Unchanged: a question put to everyone still gets all five answers. When the pick SKIPs, the exchange
      still ends, though less often. In run 8 the first-speaker pick chose quiet Leo four times out of six.
    - Latency is unchanged: first speaker 1.2-1.5 s on average (1.8 s at most), thread director 1.1-1.2 s.
  - Focused suites, ruff and lint as before (3 violations, as at HEAD).
- Q21 (owner, 2026-11-19): a group call keeps a **Claude CLI process waiting for each of its characters**:
  - The warm pool (`claude_cli_provider._WarmPool`) keeps a place for every live kind used in the last six
    minutes, plus one, up to 8 (it was 3 for everything). When it is full, a process for anything but a live
    call makes room first. A one-on-one call (replies and the overlap judge) still holds 3. A full group call
    can hold 8 idle processes at about 200 MB each, about 1 GB more than before.
  - Character lines and reactions dropped `per_turn`, so the system prompt changed every turn and no line ever
    matched a waiting process. So did a live turn through the chat store's own streaming path
    (`prompt_store`). Both now keep it on a live turn, as the prewarm and speculation paths already did.
    Typed chats are unchanged.
  - Real-model check (Haiku 4.5, the two-turn harness, runs 9 and 10):
    - The characters' turns took a waiting process 1 time in 9 before, and 6 in 11 after: every turn after
      each character's first one.
    - A line went from 2.1 s to 1.6 s on average, and a reply from 2.3 s to 1.9 s.
    - The directors already took a waiting process (all but the first).
  - The harness builds its own prompts, so the `per_turn` fix is covered by unit tests, not by this check.
  - Not part of this change: the config registry is stale. `OMNIX_TRADING_STOCH_SWEEP`, from 9fb04035fc, is
    missing, so `test_configuration_doc_is_generated_from_registry` fails.
- 2026-11-20: three fixes after the owner's call with Jinx (uncommitted on main):
  - **A new call starts with the chat's character alone.** Guests used to stay seated after a call, so Abhishek
    joined the next call with Jinx. Ending a call now clears its seats (`clear_guests`,
    `DELETE /api/chat/sessions/{id}/scene/guests`, from `stopLiveVoice`). A browser that closes mid-call skips
    that, and its guests are still seated next time.
  - **A guest's turn draws the guest's own face.** The portrait used to stream the host for every turn, so Jinx
    spoke with Abhishek's voice and lines. The audio session is now keyed by its speaker too. A guest's turn
    opens the avatar websocket with `speaker_id`, which the gateway checks against the seats (`speaker_view`;
    `speaker_not_on_call` for anyone else) before it reads that guest's portrait image.
  - **Every member is live.** The service streams one face at a time, the speaker's. The others play their own
    idle loops with blinks (`MemberPortrait`, `PortraitIdleLoop`). A loop is kept from the member's own stream,
    or comes from `GET /api/tts/live-call/portrait-idle` (portrait service `POST /portrait/idle`). That route
    hands out only a loop the service has already rendered, because a call's stream holds the GPU. A guest
    invited mid-call has no loop until its first turn, so its tile shows its picture until then.
  - The portrait service change goes live when the service restarts. Focused Python suites, ruff, lint (3
    violations, as at HEAD), web typecheck, the related web tests (113) and the build pass.
- 2026-11-20, the owner's next call: Jinx's avatar went unavailable near the end and stayed that way (uncommitted
  on main).
  - **Cause.** A turn first opened an audio session for Abhishek, then swapped to Jinx when the speaker was known.
    The gateway admits one live-call socket per process (`OMNIX_LIVE_MAX_CALLS`, default 1), and it freed the old
    socket's slot only after awaiting the portrait link's close. So Jinx's new socket was refused (429; a browser
    sees only close 1006 before open). The PCM session then counted as failed but not closed, and the controller
    reused it for every later turn: no audio session, no hello, no portrait, until the call ended.
  - **Fixes.**
    - The gateway frees the slot as soon as the call's transport is done, before the portrait's close.
    - The PCM session asks again for a socket refused before it opened (after 250, 500 and 1000 ms), and logs
      `session_websocket_retry`. Events from a replaced socket are ignored.
    - `hasFailed()` on the session: the controller and the output coordinator replace a failed session instead of
      reusing it.
  - Tests: the retry (refused twice, then plays and gets its hello), the retries spent, no retry after stop, the
    controller and coordinator replacing a failed session, and the gateway's slot being free before the portrait
    closes (it fails without the fix). Python websocket suites, ruff, lint (= HEAD), the related web suites (812)
    and the build pass.
- 2026-11-20, review of that call (uncommitted): 12 of its 18 replies were the host's speculated reply, though guests
  were seated. "Hey Afro, how's it going?" and "Aphra, tell him about your family." got Jinx ("I'm not Aphra").
  - Cause: only the `/stream` speculation route refused a call with guests. The browser starts speculation through
    `/start` (handshake) and `/start-stream` (inline). Those set no `scene_possible`, so the accept's seat check was
    skipped too.
  - Fix: `refuse_speculation_in_scene` in `live_chat_speculation`, called by all three start routes, which also
    record `scene_possible` from it. The guest test now covers the three routes (it fails without the fix).
  - Also seen, not fixed: gateway event-loop stalls from trading background jobs (296 in the call's 7 min, 58 s
    in all, max 1.4 s). The worst, at 19:10:25, was `strategy_interday_learning_monitor` filtering up to 10,000
    events per strategy on the loop. It delayed a final transcript by 5.6 s, so "Sure that I control you" was
    answered late and then cut off. Others: synchronous DB reads (`require_background_owner`, `load_settings`) and
    HTTP connects on the loop. STT misheard "tinkering" and the name Afra.
- 2026-11-20, the three follow-ups from that review (uncommitted on main):
  - Gateway stalls: async trading monitors (cycles, startup and shutdown) and the strategy runner now run on a
    dedicated trading loop thread (`monitor_task.on_trading_loop`), never on the gateway loop. The interday
    monitor's event filtering runs in a worker thread. Trading suite passes.
  - Names: the call members' names go to speech recognition as phrases to boost (`context_phrases` on the STT
    websocket, NeMo greedy boosting tree, `OMNIX_STT_CONTEXT_BOOST_ALPHA`, default 0.5). The shared decoder changes
    only between utterances; a rejected tree falls back to plain decoding (`stt_context_phrases_failed`). A
    real-model check is still owed: it needs an STT service restart.
  - Late lines: all three lines between characters in that call (76, 79, 82) were saved one exchange late. For two,
    the person's speech stopped the line's audio 50-120 ms in, but the call kept it pending and committed it
    "completed" when the next reply ended. The third played to the end, but the call's speaking state stayed set,
    so it waited 65 s. The initiative controller now settles a line the person speaks over at once (interrupted
    with what was heard, or dropped with its lease given back if nothing was heard), and commits a line when its own
    audio ends (`ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT`). Three tests in `live-call-scene.test.ts` fail without the fix.
  - Sound-alike names (owner asked, same day): recognition spells names as it hears them ("Aphra", "Afro" for
    Afra), and `named_member` matched only exact spellings, so the wrong member could answer. When no member is
    named exactly, a word now names a member when it sounds like their one-word name: same consonant key (vowels
    and s/sh folded) and at most about one letter in four apart. Names shorter than four key sounds ("Bea",
    "Theo") are never matched by sound; a word that sounds like two members names neither. Your words are not
    rewritten. `test_a_name_recognition_misspells_still_names_the_member`.
- 2026-11-20, review of 94ba6faee6 and 216765c15f (three review agents; fixes uncommitted on main):
  - Sound-alike: a match now counts only when the word is said as a name. That means capitalised mid-sentence,
    possessive, or set off by commas or a greeting. Everyday words ("like", "make", "mine") never count.
    `test_an_everyday_word_that_sounds_like_a_name_names_no_one`.
  - STT boosting:
    - Each call's names are kept per owner, and the decoder boosts their union, so a second call no longer erases
      the first one's names.
    - A rebuild waits out any stream that is mid-utterance, rebuilds at most every 2 s, and restarts quiet streams
      on the new decoder.
    - A stream not fed for 30 s no longer blocks rebuilds.
    - A failed fallback no longer raises.
    - The phrase map has its own lock, so `release` never waits on the GPU lock.
  - Trading loop:
    - A lag probe warns when the trading loop stalls 5 s or more.
    - A second cancel still waits for the cycle to finish before shutdown.
  - Portraits:
    - Between speakers, prepare and idle no longer render a loop on the GPU. The idle route asks for a loop that
      is already rendered only.
    - An unreadable member gets `portrait_failed`, not a 500.
  - Web:
    - A clear waits for an add still in flight.
    - The playback-off edge carries its kind.
    - The call's names stay while the panel shows another chat (`callScenePhraseSource`).
    - A turn whose speaker the runtime doesn't list yet reads the runtime again.
    - Member idle loops reset when a call stops.
    - A portrait that attaches after its session was replaced is dropped.
  - The open items, closed the same day (owner: "go with recommended"; uncommitted on main):
    - Seats expire on the server. While a call is open, the speech proxy stamps the chat's seats every 60 s
      (migration 0201, `last_call_at`). A seat whose call has been quiet for 10 minutes is gone. A seat chosen
      before any call has no stamp and stays. `test_a_seat_expires_once_its_call_has_been_quiet...` (PG).
    - The gateway owns the call's names. The browser names its chat only. The proxy replaces any phrases it
      sends with the chat's host and seated guests, read through the tenant-scoped store (port
      `voice.call_roster`, contributed by live voice). A chat that isn't the caller's boosts nothing.
    - Concurrent calls: each owner's names carry its account's scope (a workspace hash). The decoder boosts the
      union only when every open call shares one scope; with calls from two accounts open, no names are boosted.
    - Name cleaning: accents fold to ASCII (Zoë → Zoe), all-caps or all-lower names are capitalised, and a full
      name also boosts its first name, skipping titles.
    - Smaller items:
      - The trading loop can be closed and restarted cleanly.
      - The portrait idle route reads rendered loops without the GPU thread.
      - The avatar websocket and idle loops share `call_session`.
      - Member idle loops are keyed by the pack revision, so a changed face is asked for again.
      - A PCM session stopped before its socket opened ends the phrases waiting for it.
    - Before a call uses this: migrate 0201 on live, then restart the gateway and the STT service.
- 2026-11-21: 4.4 camera share built (uncommitted, beside the FlashHead work).
  - Server: `chat/camera_glance.py`, the glance route in `live_call_task_routes.py`, and `camera_shared` on the
    chat and context requests. The prompt is `chat.camera_share.glance` v1.
  - Web: `workspace/camera-share.ts`, plus `chat/CameraShare.tsx` (toggle and self-view tile).
  - Tests: `src/tests/chat/test_camera_glance.py` (PG), `camera-share.test.ts`, and `CameraShare.test.tsx`.
  - Unprompted turns see the camera too (owner request, same day): `camera_shared` on the greeting stream,
    `proactive_camera_note` and the `ambient_camera_unseen` skip. Tests are in
    `src/tests/unit/chat/test_live_conversation_proactive_camera.py` and
    `live-conversation-initiative-camera.test.ts`.
  - Call start (owner request, same day): the glance on call start, and the greeting takes a look that saw something.
    Tests are in the same Python file, `camera-share.test.ts` and `live-voice-unified-audio-controller.test.ts`.
  - Live idle video before the call (owner request, same day). Once the portrait model is ready and the chat asked
    for live video ("Load live video"; since 2026-11-22 a loaded model alone is not enough), `LivePortraitLoadControl` fetches the chat character's idle loop
    (`GET /api/tts/live-call/portrait-idle`, which serves a rendered loop outside a call too). The stage plays the
    loop until the call's first frame. If the model is ready but this face's loop is not known, the button stays
    pressable, and pressing it renders the loop. Tests: `LivePortraitLoadControl.test.tsx`.
  - Not yet tried on a real camera or vision model.
- 2026-11-21: the Live Chat page is tabbed: Character, Presence, Voice, Video and Call (owner request). The open tab
  is remembered, and Start Call and the call preview are on the Call tab. The live portrait engine (FLOAT or
  FlashHead Lite) moved from Settings → Assistant & Chat to the Video tab (`portrait/LivePortraitEngineCard.tsx`).
  It saves `assistant.livePortraitEngine` at once through `settings/assistantSettingsUpdate.ts`.
  Tests: `LiveChatPanel.test.tsx`.
- 2026-11-21, review of the owner's call with Jinx: "Jinx" was transcribed as "Jenks" and stayed that way.
  - Both names were boosted before the first utterance (`stt_context_phrases_applied`, 1 then 2 phrases), and the
    finals came from the boosted full decode.
  - The boost is too small to change this word. "Jinx" and "Jenks" share their first token (`▁J`), and the deciding
    token (`in` against `en`) gains only about 1.35 nats (alpha 0.5 × 2.69).
  - Fix: the speech proxy now writes a heard word as the call's name when it sounds like exactly one of them and is
    said as a name. It applies to partials, previews, finals and a resumed session's finals
    (`app/conversation/heard_names.py`, `stt_proxy_routes._to_browser`). An everyday use ("don't jinx it") stays as
    heard. `scene.py` now uses the same helpers.
  - Tests: `test_heard_names.py`, `test_stt_proxy.py`. It takes effect when the gateway restarts.
- 2026-11-21, owner report: FlashHead's "live video" looked like the still picture.
  - Cause: the browser did get the loop and play it. But FLOAT's rest-pose rule had cut it from the stillest 4.3 s
    of the render: mean change from the first frame was 2.0/255, with no visible blink or sway.
  - Fix: a FlashHead reply starts from the loop's own last frames, not from the picture, so the loop no longer has
    to stay near the picture. `flashhead_runtime.idle_loop_bounds` cuts a loop of at least 8 s from 15 passes of
    silence (about 14.4 s), skipping the first pass.
  - Re-measured on the service with Jinx: a 9.6 s loop with a head turn and eye movement. Mean change from the first
    frame is 2.4 (max 3.1), and the eye band's std reaches 33. The seam step is 2.5, against 1.0 for an average step.
  - Test: `test_flashhead_runtime.py`.
- 2026-11-21, owner report: in a group call with Ehsan the picture kept resizing and the live video was choppy.
  - Cause: each speaker change opens a new FlashHead stream (one stream, one GPU thread). FlashHead renders 24 frames
    a pass and needs about 1 s of audio ahead of each, so a start released on its first frames ran out of video at
    once. Frames came late, the portrait fell back to the still picture and back again, every turn. The quality
    levels only change the JPEG, not the render, so they could not catch up.
  - Fix 1: a portrait that drops out mid-call idles on its loop instead of a still fallback picture
    (`useDrawnAvatarPack.ts`). A moving fallback (sprite with mouth frames, Live2D, Rive) is kept.
  - Fix 2, D-5 revised by the owner: the start hold is per engine (`PORTRAIT_START_RULES`, sent in the avatar
    socket's `ready`). FlashHead Lite waits until frames cover 1.28 s of the phrase, or all but 80 ms of a shorter
    one, capped at 1.2 s. FLOAT is unchanged (first frames, 250 ms cap). A slow FlashHead start now costs up to 1.2 s
    of silence before a reply.
  - Deferred: one stream per call shared by the speakers.
  - Tests: `LiveChatFullscreenShell.test.tsx`, `livePortrait.test.tsx`, `live-voice-pcm-session.test.ts`,
    `live-voice-pcm-worklet.test.ts`, `test_gateway_live_call_avatar_websocket.py`, `test_flashhead_runtime.py`.
    Not yet tried in a call; takes effect when the gateway restarts and the page reloads.
- 2026-11-21, owner report: FlashHead's idle loop barely moves, "almost a still image with blinking"; blink more.
  - Head motion: none found from the model. In silence FlashHead moves the head 0 px with any seed or with room tone,
    and faint speech at any gain lip-syncs (wav2vec ignores scale). A post-render sway was shown and rejected by the
    owner. Open; a reference recording of the wanted motion would help.
  - Blinks: the browser fades the idle loop into its eyes-shut twins every 3.5-8 s, but FlashHead's twins were its
    loop frames, so those blinks showed nothing, and the model blinks in only about a third of 14 s silent renders.
    Fix (`flashhead_runtime.py`): `blink_frame` finds a silent render's own blink (a brief change in the eye band);
    the twin is the loop frame with the eye area from that frame (`eye_region_mask`, as FLOAT's). Ahead of a call,
    `find_blink` tries up to two more seeds (about 5 s each) when the loop's render has none; never in a call.
    Six test faces: four get twins, Abhishek missed with both seeds, Mohammad wears dark glasses (no twins, as before).
  - Tests: `test_flashhead_runtime.py`, `test_portrait_service.py`. Live after the portrait service restart of
    2026-11-21 19:40; not yet seen in a call.
- 2026-11-21: FlashHead idle head motion from LivePortrait (owner approved after an offline prototype).
  - A recorded idle motion (each frame's pose, expression, x/y shift and scale change from the first frame; lips
    held) drives LivePortrait (KwaiVGI, MIT) to animate the portrait into a closed loop ahead of a call; LivePortrait's
    eye retargeting makes the eyes-shut twins. FlashHead still renders all speech, starting from the loop's frames.
    Without LivePortrait's models or the motion file, or when either fails to load or render, the loop is FlashHead's
    own as before.
  - Code: `services/portrait/liveportrait_idle.py` (motion file, loop closure, renderer), `flashhead_runtime.py`
    (`load_liveportrait`, `liveportrait_idle`; the twins replace the blink search). Catalog: `liveportrait-code`
    and `liveportrait-weights` in the FlashHead bundle (pinned revisions, checksums). Motion from a recording:
    `scripts/portrait_idle_motion.py` (OPERATIONS §7).
  - The motion ships (owner, 2026-11-22): `services/portrait/assets/idle-motion.npz`, 237 frames of head pose and
    expression numbers taken from the reference video the owner chose (a third-party demo); no pixels are kept and the
    video was deleted. A user's own
    motion in the portrait models' folder, or `OMNIX_PORTRAIT_IDLE_MOTION`, replaces it.
  - Real service (Afra, the shipped motion): loop and twins in 12.9 s of a 34 s prepare;
    seam 2.5 vs a 2.24 frame step; idle → speech first frame 4.5; colours matched; GPU peak 17.6 GB total with the
    other services; commit headroom 36.8 GB.
  - Handover: FlashHead's speech frames lose the eye catchlight and draw a darker lash line than LivePortrait's idle
    frames (sharpness 493 vs 266). A blur of the loop doesn't match that, so none is applied; watch it in a call.
  - Open: a real call.
  - Tests: `test_liveportrait_idle.py`.
- 2026-11-22: live calls without live video (owner request). Start Call no longer brings the portrait up; a chat
  gets live video only after "Load live video" is pressed in it.
  - The request is kept per chat in the page (`requestLiveVideo` and `liveVideoRequested` in `livePortrait.ts`) until
    the page reloads. `livePortrait.wanted` needs it, so a call without it opens a voice-only audio session and the
    faces stay still pictures: no idle loops are fetched, on the call card or in the full-screen call.
  - "Load live video" also shows in the full-screen call card. Pressed during a call, it loads the model, and the
    next reply replaces the audio session with one that draws the portrait (`ensureSharedAudioSession` compares the
    session's `portrait` flag).
  - The benchmark's `--portrait on` presses the button before the call (`test_live_voice_performance.py`).
  - Owner report, same day: an invited guest (Abhishek) stayed a still picture after "Load live video". The button
    rendered only the host's loop, and the gateway hands out rendered loops only, so a guest's came first with its own
    turn. Now the button also has each portrait guest's picture prepared (and its loop rendered), one at a time,
    outside a call only, and fetches its loop; a guest invited later is prepared then (`claimGuestRender` in
    `memberIdleLoops.ts`, so the call card's and the full-screen button do not both ask).
  - Owner request, same day: pressing "Live video ready" again unloads the video. The portrait service gained
    `POST /portrait/unload` (refused while a call streams, `model_busy`, or mid-load, `warming`; with a launcher it
    exits and restarts light, as the idle unload does), the gateway `DELETE /api/tts/live-call/portrait-load`
    (`unload_portrait` in `link.py`), and the button: on success it turns the chat's video off (`cancelLiveVideo`) and
    drops the idle loops, so the faces are still pictures again; a refusal keeps the video and says why.
  - Owner request, same day: the load shows its progress. The service reports only loading or ready, so the bar
    (`LiveVideoLoadProgress.tsx`, `loadProgress.ts`) follows the button's own steps: the model (when it is not up),
    the chat's face, then each portrait guest, each named ("Rendering Jinx's live video…", "Step 2 of 3 · about 6 s
    left"). A step fills evenly to 90% at its expected time and then creeps toward 99%; the expected times start at
    12 s for the model and 5 s a face (the service logs: 9.5-13.5 s and 1-4 s) and follow this browser's own loads
    (`omnix.livePortrait.loadTimes`). A load the button did not start (a call's) shows a sliding bar.
  - Tests: `livePortrait.test.tsx`, `LivePortraitLoadControl.test.tsx`, `LiveChatFullscreenShell.test.tsx`,
    `live-voice-unified-audio-controller.test.ts`, `test_portrait_service.py`, `test_portrait_setup.py`. Not yet
    tried in a real call.
- 2026-11-22: the camera sees with the chat's own model (owner report and decision). Shared from the Mac, the camera
  turned itself off at the first question: no vision model was set ("No vision model is set up"), and the chat ran on
  Claude Haiku 4.5 through the Claude CLI, which took no images. Now, with no vision model set, the chat's model looks:
  - The Claude CLI provider sends the latest user message's pictures as image blocks ahead of the prompt in its
    stream-json message (`prompt_content` in `claude_cli_provider.py`; measured: Haiku 4.5 described a test picture
    in 1.7 s, CLI 2.1.330). Like Codex, only the latest message's pictures go.
  - `default_desktop_vision_client` follows the chat provider: Codex and the Claude CLI through their CLIs
    (`ProviderVisionClient`, with `CodexDesktopVisionClient` and the new `ClaudeCliDesktopVisionClient`), and
    LM Studio or llama.cpp through their local server with the chat's model (`follows_chat`). A vision model set
    explicitly still wins, and `claude_cli:<model>` picks Claude as `codex:<model>` picks Codex.
  - Claude and Codex are remote, so the owner still ticks "Allow remote vision provider" before a picture goes.
    A local chat model without vision fails its look, which the call already says ("I couldn't see it").
  - Tests: `test_assistant_context.py`, `test_claude_cli_provider.py`. Not yet tried in a real call.
