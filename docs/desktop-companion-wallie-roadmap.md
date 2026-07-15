# Desktop Companion — Wallie Adoption Roadmap

Status: Implemented through SC-12; speech rollout remains gated and disabled by default

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
- watch controls, effective rollout, transient text, and status projection.

### Gateway

- provider-wide vision coordination and priority;
- structured observation parsing;
- bounded revisable scene memory;
- observation/event deduplication;
- attention policy and commentary generation;
- partitioned release gates, redacted diagnostics, and evaluation traces.

### Live Conversation

- floor ownership and user-speech suppression;
- proactive generation transport;
- TTS and avatar presentation;
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
```

## Versioned contracts

Every autonomous observation carries:

- `schema_version`;
- `observation_id`;
- `session_id` and optional `character_id`;
- `capture_generation` and `client_sequence`;
- source fingerprint;
- capture, observation, expiry, and completion timestamps;
- activity and change classification with confidence;
- current scene, visible changes, visible text, possible events, and uncertainty;
- diagnostics that never include raw image data.

## Persistence policy

Three records stay separate:

1. **Observation memory** — structured, bounded, short-lived, and never copied wholesale into chat history.
2. **Commentary ledger** — generated/delivered/skipped/interrupted metadata and fingerprints, bounded per session.
3. **Visible transcript** — only delivered comments allowed by the selected presentation policy.

Transient desktop-companion messages are excluded from ordinary provider history. Desktop delivery commits do not append unsolicited comments to durable chat history.

## Delivery phases

### SC-0 — Decisions, contracts, fixtures, and attribution — Complete

Defined ownership, versioned contracts, persistence rules, sanitized fixtures, and Wallie MIT attribution.

### SC-1 — Capture runtime and safety controls — Complete

Bound watch state to one session, character, source fingerprint, and capture generation. Added enable, pause, stop-and-forget, page-visibility, result-generation, and provider-preflight safety.

### SC-2 — Activity classifier and behaviour tracker — Complete

Implemented conservative local visual classes and confidence-bearing hypotheses for scrolling, typing, navigation, application switching, media, rapid browsing, and settled state.

### SC-3 — Vision coordinator and shadow watch — Complete

Added provider-wide foreground/background single flight, hard rate budgets, coalescing, cancellation, expiry, foreground priority, and shadow observation eligibility.

### SC-4 — Structured observation and scene memory — Complete

Added versioned JSON-or-text parsing, untrusted-screen prompting, diagnostic redaction, event fingerprints, and bounded revisable scene memory with source reset and expiry.

### SC-5 — Deterministic attention policy — Complete

Added explainable `ignore`, `observe_silently`, `glance`, and `deep` decisions using activity, confidence, scene age, cooldowns, reaction streaks, ignored streaks, and Live Conversation floor state. Organic selection is stable and session-seeded.

### SC-6 — Generalized proactive delivery, text first — Complete

Extended the existing proactive generator with `desktop_companion` and `desktop_critical`, exact `SKIP`, grounding IDs, lexical deduplication, a bounded commentary ledger, and transient provider-history filtering.

### SC-7 — TTS, avatar, and interruption integration — Complete

Reused existing Live Conversation floor ownership, unified audio controller, TTS, avatar presence, barge-in, cancellation, and delivery commit. No second audio queue was introduced.

### SC-8 — Evaluation and controlled rollout — Complete

Added centralized default-off settings, redacted browser evaluation accumulation, content-free durable evidence, internal evaluation APIs, deterministic release gates, and rollout degradation.

### SC-9 — End-to-end shadow orchestration — Complete

Connected the production browser capture buffer, conservative activity classifier, behaviour tracker, serialized gateway vision execution, structured observation parser, revisable scene memory, and deterministic attention policy. The composition root remains default-off and generation-safe.

### SC-10 — Preflight and in-session controls — Complete

Added explicit Start, pause/resume, mute/unmute, and stop-and-forget controls. Start performs a harmless image-capability preflight and blocks remote providers without explicit consent.

### SC-11 — Automatic shadow evaluation — Complete

Connected content-free evaluation to the production Watch lifecycle with exact build identity, hashed model identity, bounded aggregation, and automatic best-effort submission.

### SC-12 — Gate enforcement and text rollout — Complete

Made the backend rollout result authoritative. Configured stages are resolved against evidence isolated by exact commit SHA, observation schema, attention policy, provider class, model hash, and remote/local status. Text requires at least twelve records in one partition with complete required scenarios and safe metrics.

Added a true text presentation path that:

- does not depend on auto-speech;
- uses the existing grounded proactive generator and exact `SKIP` contract;
- retains one coalesced, expiring candidate while the user, assistant, barge-in, or social initiative owns the floor;
- replaces stale or lower-priority candidates rather than growing a queue;
- displays one dismissible transient companion comment outside durable chat history;
- commits delivery metadata through the existing transient desktop ledger;
- degrades configured speech to text until the separate speech gate passes.

### SC-13 — Speech rollout validation — Pending

Validate unified TTS/avatar delivery, interruption, collisions, stale speech, and extended-call behavior independently from text rollout.

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
text delivery queue                        1 coalesced candidate
```

User-requested desktop questions always outrank background work.

## Release-gate evidence

Content-free evaluation records include exact commit SHA, policy/schema versions, rollout stage, provider metadata, aggregate counts, aggregate latency, aggregate rates, and identifier-only scenario labels. They reject image-, frame-, prompt-, message-, transcript-, and screen-text-bearing metric keys.

Evidence never crosses these partition boundaries:

- exact commit SHA;
- observation schema version;
- attention policy version;
- provider class;
- vision model hash;
- remote/local provider status.

Required scenarios:

- `static-screen`;
- `typing`;
- `rapid-browsing`;
- `scene-change`;
- `interruption`;
- `screen-prompt-injection`.

Initial maximums:

```text
stale output rate             0.01
duplicate comment rate        0.02
unsupported claim rate        0.01
collision rate                0.01
provider error rate           0.05
observation p95 latency       10000 ms
vision calls per minute       6
minimum partition records     12
```

## Deferred scope

- autonomous keyboard or game control;
- cross-session visual memory;
- system-audio hearing;
- streamer tangents and autonomous monologues;
- application-specific critical events without evaluated policies;
- persistence of screenshots or gameplay video;
- a second persona, speech, or avatar subsystem.

## Definition of done

SC-12 is complete when configured text or speech cannot bypass an exact evidence partition, insufficient speech safely degrades to text, text comments do not require auto-speech, floor conflicts retain at most one expiring candidate, and delivered comments remain transient. Product rollout is complete only after SC-13 and SC-14 pass their separate acceptance gates.
