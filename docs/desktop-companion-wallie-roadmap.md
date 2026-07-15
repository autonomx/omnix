# Desktop Companion — Wallie Adoption Roadmap

Status: Implemented through SC-13; compatibility, privacy, and endurance finalization remain pending

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

Added a speech-specific release gate isolated from text evidence. Normal requested speech continues to degrade to text until one exact evidence partition includes:

- at least twelve speech-stage evaluation records;
- at least twelve completed or interrupted delivery outcomes;
- the normal observation and safety scenarios;
- `speech-completed`, `interruption`, and `speech-stale` scenarios;
- acceptable stale-output, duplicate, unsupported-claim, collision, provider-error, latency, and call-rate metrics.

The existing delivery controller now emits content-free presentation outcomes. Evaluation records generated, skipped, completed, interrupted, stale, discarded, and error states without retaining generated text. Speech continues to use the existing Live Conversation floor, unified TTS, avatar, barge-in, cancellation, and delivery-commit path.

A controlled speech validation canary is available only when the deployment explicitly sets:

```text
OMNIX_DESKTOP_COMPANION_SPEECH_CANARY=1
```

The canary remains off by default, requires the user to request speech and start Watch, and exists only to collect the evidence needed for the normal speech gate. It does not bypass capture consent, provider preflight, remote-provider consent, floor ownership, mute state, or stale-candidate checks.

### SC-14 — Compatibility, privacy, and endurance — Pending

Add browser/provider matrices, remote-provider disclosure, kill switch, long-session soak tests, GPU-contention tests, troubleshooting, and rollback documentation.

## Initial limits

```text
capture sampling                         2 FPS
provider-wide background vision calls    6 per minute
minimum background observation interval  8 seconds
background observation timeout           10 seconds
observation stale TTL                     12 seconds
normal commentary cooldown                25 seconds
background queue                          1 active + 1 coalesced pending
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

## Deferred scope

- autonomous keyboard or game control;
- cross-session visual memory;
- system-audio hearing;
- streamer tangents and autonomous monologues;
- application-specific critical events without evaluated policies;
- persistence of screenshots or gameplay video;
- a second persona, speech, or avatar subsystem.

## Definition of done

SC-13 is complete when speech is independently gated, default-off canary collection is explicit, delivery outcomes are evaluated without retaining content, interruption and stale speech are represented in evidence, and normal speech cannot activate until its own partition passes. Product rollout is complete only after SC-14 passes its compatibility, privacy, endurance, and rollback gates.
