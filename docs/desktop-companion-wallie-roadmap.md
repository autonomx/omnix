# Desktop Companion — Wallie Adoption Roadmap

Status: SC-0 through SC-15 tooling implemented; production text and speech remain evidence-gated and disabled by default

Source of truth: `autonomx/omnix` `main`

## Objective

Adopt the useful observer, attention, restraint, scene-memory, and commentary patterns from Wallie while retaining Omnix ownership of capture, temporal vision, safety boundaries, characters, live conversation, TTS, avatar delivery, persistence, and settings.

Wallie is an architectural reference, not a runtime dependency. Omnix uses a clean-room implementation unless a source file explicitly carries the Wallie MIT notice.

## Product boundaries

- Screen capture is explicitly user-authorized.
- Raw frames remain in browser memory and are not persisted by default.
- Screen text is untrusted observed content, never an instruction.
- Visual observations are uncertain and revisable, not deterministic application or RPG state.
- Background vision is change-gated, rate-limited, stale-aware, and lower priority than user-requested turns.
- Desktop observations are not represented as visible or persisted fake user messages.
- Commentary frequently chooses silence.
- Existing Live Conversation owns floor arbitration, TTS, avatar delivery, barge-in, and delivery commit.
- Existing centralized settings own defaults; session overrides may narrow or disable them.

## Runtime ownership

### Browser

- capture authorization and source lifecycle;
- temporal frame buffer and local frame sampling;
- conservative activity classification and behaviour tracking;
- page visibility and capture-generation identity;
- watch controls, effective rollout, transient text, speech evidence, and status projection.

### Gateway

- provider-wide vision coordination and priority;
- structured observation parsing;
- bounded revisable scene memory;
- observation/event deduplication;
- attention policy and commentary generation;
- partitioned text and speech release gates, redacted diagnostics, and evaluation traces.

### Live Conversation

- floor ownership and user-speech suppression;
- proactive generation transport;
- unified TTS and avatar presentation;
- interruption, cancellation, and delivery commit.

## Canonical pipeline

```text
user-approved stream
  -> temporal capture
  -> local activity/behaviour signals
  -> provider-wide vision coordinator
  -> factual structured observation
  -> bounded scene memory
  -> deterministic attention decision
  -> backend-resolved effective rollout
  -> existing proactive-turn pipeline
  -> transient text or existing speech/avatar delivery
  -> content-free delivery evidence
  -> exact-partition qualification report
```

## Persistence policy

Three records stay separate:

1. **Observation memory** — structured, bounded, short-lived, and never copied wholesale into chat history.
2. **Commentary ledger** — generated/delivered/skipped/interrupted metadata and fingerprints, bounded per session.
3. **Visible transcript** — only delivered comments allowed by the selected presentation policy.

Transient desktop-companion messages are excluded from ordinary provider history. Desktop delivery commits do not append unsolicited comments to durable chat history.

## Delivery phases

### SC-0 through SC-8 — Foundation — Complete

Defined ownership, versioned contracts, temporal capture, conservative activity classification, provider-wide coordination, structured observations, revisable scene memory, explainable attention, grounded proactive generation, existing TTS/avatar integration, centralized settings, and redacted evaluation contracts.

### SC-9 — End-to-end shadow orchestration — Complete

Connected the production capture buffer, classifier, coordinator, vision client, observation parser, scene memory, and attention policy in a default-off generation-safe loop.

### SC-10 — Preflight and in-session controls — Complete

Added explicit Start, pause/resume, mute/unmute, stop-and-forget, image-capability preflight, remote-provider consent enforcement, and actionable status.

### SC-11 — Automatic shadow evaluation — Complete

Connected content-free evaluation to the production Watch lifecycle with exact build identity, hashed model identity, bounded aggregation, and automatic best-effort submission.

### SC-12 — Gate enforcement and text rollout — Complete

Made backend rollout resolution authoritative, partitioned evidence by build and provider identity, required twelve records per partition, added one coalesced expiring delivery candidate, and implemented transient text independently from auto-speech.

### SC-13 — Speech rollout validation — Complete

Added an independent speech gate requiring speech-stage records, delivery outcomes, safety scenarios, and speech-completed, interruption, and stale-speech coverage. Normal requested speech degrades to text until this gate passes. The default-off deployment canary exists only to collect speech evidence.

### SC-14 — Compatibility, privacy, and endurance — Complete

Added:

- a deployment kill switch that blocks preflight, observation, and rollout;
- a browser provider-failure circuit with bounded backoff and stop behavior;
- a globally bounded background queue and ten-thousand-request queue endurance coverage;
- browser/provider compatibility guidance;
- privacy, remote-provider disclosure, troubleshooting, evidence deletion, and rollback procedures;
- full required GitHub Actions validation, including continuous 1000-turn endurance.

### SC-15 — Production qualification tooling — Complete

Added a deterministic, content-free qualification command and runbook for real evidence collected from one exact runtime partition. The report:

- requires exact commit SHA, provider class, model hash, schema/policy versions, and remote/local status;
- never combines incompatible partitions;
- evaluates text and speech gates independently;
- renders JSON or Markdown without frames, screen text, prompts, transcripts, or generated commentary;
- returns stable exit codes: `0` pass, `2` insufficient, and `3` fail;
- does not mutate rollout settings or manufacture evidence.

Actual production promotion remains pending until real runtime evidence passes for the deployed exact partition.

## Initial limits

```text
capture sampling                         2 FPS
provider-wide background vision calls    6 per minute
minimum background observation interval  8 seconds
background observation timeout           10 seconds
observation stale TTL                     12 seconds
normal commentary cooldown                25 seconds
background queue                          1 active + bounded coalesced pending
shadow evidence flush interval            60 seconds
text/speech delivery queue                 1 coalesced candidate
minimum text partition records            12
minimum speech partition records          12
minimum speech deliveries                 12
```

User-requested desktop questions always outrank background work.

## Evidence boundaries

Evidence never crosses these partition boundaries:

- exact commit SHA;
- observation schema version;
- attention policy version;
- provider class;
- vision model hash;
- remote/local provider status.

Evidence includes only aggregate counters, rates, latency, rollout stage, and identifier-only scenarios. It excludes images, frame data, source labels, prompts, visible screen text, generated commentary, transcripts, credentials, and endpoint secrets.

## Production qualification sequence

1. Deploy one exact `main` commit with rollout set to shadow.
2. Collect at least twelve records covering all required text scenarios in one exact partition.
3. Run the SC-15 text qualification report.
4. Promote to text only after a `pass` report and explicit operator approval.
5. Enable the speech canary only for controlled evidence collection.
6. Collect the required speech records, deliveries, and scenarios in the same exact partition.
7. Run the SC-15 speech qualification report.
8. Disable the canary and promote to normal speech only after a `pass` report.
9. Requalify after any commit, provider, model, schema, policy, or remote/local change.

## Deferred scope

- autonomous keyboard or game control;
- cross-session visual memory;
- system-audio hearing;
- streamer tangents and autonomous monologues;
- application-specific critical events without evaluated policies;
- persistence of screenshots or gameplay video;
- a second persona, speech, or avatar subsystem.

## Definition of done

Implementation is complete through SC-15 when qualification reports are reproducible, exact-partition only, content-free, and incapable of changing rollout state. Product rollout is complete only when real deployed evidence passes the relevant text and speech qualification gates and an operator explicitly promotes each stage.
