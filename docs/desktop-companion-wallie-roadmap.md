# Desktop Companion — Wallie Adoption Roadmap

Status: In progress

Source of truth: `autonomx/omnix` `main`

Implementation branch: `agent/screen-companion-sc0-sc8`

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
- watch controls and status projection.

### Gateway

- provider-wide vision coordination and priority;
- structured observation parsing;
- bounded revisable scene memory;
- observation/event deduplication;
- attention policy and commentary generation;
- redacted diagnostics and evaluation traces.

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
  -> existing proactive-turn pipeline
  -> existing floor / TTS / avatar delivery
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

Transient desktop-companion messages are excluded from ordinary provider history. A compact summary may be injected later through an explicit bounded context item.

## Delivery phases

### SC-0 — Decisions, contracts, fixtures, and attribution

Define ownership, versioned contracts, persistence rules, sanitized fixtures, and Wallie attribution.

### SC-1 — Capture runtime and safety controls

Bind watch state to one session, character, source fingerprint, and capture generation. Add minimum enable, pause, stop, visibility, and provider preflight controls.

### SC-2 — Activity classifier and behaviour tracker

Implement conservative local change classes first. Derive likely scrolling, typing, navigation, application switching, continuous media, rapid browsing, and settled state with confidence.

### SC-3 — Vision coordinator and shadow watch

Add a provider-wide foreground/background coordinator, hard rate budgets, coalescing, expiry, and shadow observation requests. No commentary delivery.

### SC-4 — Structured observation and scene memory

Parse a versioned observation schema with plain-text fallback. Maintain bounded, revisable, session-scoped scene memory and pre-generation event deduplication.

### SC-5 — Deterministic attention policy

Choose `ignore`, `observe_silently`, `glance`, or `deep` using activity, scene age, confidence, cooldowns, recent reaction streaks, live-conversation state, and session policy. Organic weighted selection remains optional and session-seeded.

### SC-6 — Generalized proactive delivery, text first

Extend the existing proactive pipeline with `desktop_companion` and `desktop_critical` sources, `SKIP`, grounding IDs, a bounded commentary ledger, post-generation deduplication, and transient-history filtering.

### SC-7 — TTS, avatar, and interruption integration

Reuse existing floor ownership, speaking state, barge-in, cancellation, TTS, avatar, and delivery commit. Ordinary desktop commentary never interrupts user speech or requested assistant responses.

### SC-8 — Evaluation and controlled rollout

Ship shadow mode first, then text-only comments, then spoken comments. Store versioned redacted evaluation traces and gate activation on stale-output, duplicate-output, unsupported-claim, collision, latency, and provider-load limits.

## Initial limits

```text
capture sampling                         2 FPS
provider-wide background vision calls    6 per minute
minimum background observation interval  8 seconds
background observation timeout           10 seconds
observation stale TTL                     12 seconds
normal commentary cooldown                25 seconds
background queue                          1 active + 1 coalesced pending
```

User-requested desktop questions always outrank background work.

## Deferred scope

- autonomous keyboard or game control;
- cross-session visual memory;
- system-audio hearing;
- streamer tangents and autonomous monologues;
- application-specific critical events without evaluated policies;
- persistence of screenshots or gameplay video;
- a second persona, speech, or avatar subsystem.

## Definition of done

SC-0 through SC-8 are complete when Omnix can observe a user-approved screen in shadow mode, classify meaningful activity conservatively, schedule bounded factual vision work, maintain revisable scene state, explain attention decisions, generate grounded non-repetitive commentary through the existing proactive runtime, respect floor and interruption state, expose explicit controls, and produce redacted versioned evaluation evidence with the feature disabled by default.
