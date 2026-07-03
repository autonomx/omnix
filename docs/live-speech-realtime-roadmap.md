# Live Speech HF-Parity Roadmap

This document is the implementation source of truth for bringing Omnix live speech to the same architectural level as the Hugging Face `speech-to-speech` realtime engine.

## Target architecture

Omnix live speech should converge on a server-owned realtime pipeline:

```text
Browser microphone
  -> realtime WebSocket
  -> server VAD
  -> streaming STT
  -> LLM stream
  -> server TTS scheduler
  -> output-audio deltas
  -> browser playback
```

The browser remains responsible for capture, playback, UI state, and optional client-side VAD hints. The backend is authoritative for turn boundaries, response lifecycle, cancellation, and stale-output suppression.

## Phase 1 — Regression harness and contracts

- Add protocol event models, fake realtime providers, and regression tests.
- Cover session creation, audio append, partial transcript, response creation, response cancellation, stale generation handling, and metrics emission.
- Tests must not require GPU, LM Studio, TTS, or STT services.

## Phase 2 — Streaming STT

- Replace buffered-only STT behavior with a streaming contract.
- Emit `conversation.item.input_audio_transcription.delta` before the final utterance.
- Keep a buffered fallback for providers that cannot stream partial hypotheses.

## Phase 3 — Unified realtime WebSocket

- Provide a single realtime WebSocket route for speech sessions.
- The route accepts audio, text injection, session updates, response creation, and response cancellation.
- The route emits transcript, text, audio, cancellation, completion, and error events.

## Phase 4 — Server VAD and turn lifecycle

- Add deterministic server-side VAD as the authoritative speech boundary layer.
- Browser-side VAD becomes a UX accelerator, not the source of truth.
- Emit `input_audio_buffer.speech_started` and `input_audio_buffer.speech_stopped`.

## Phase 5 — Generation-aware cancellation

- Use a shared generation counter to cancel and discard stale output across STT, LLM, and TTS.
- Every pipeline event that can become stale must carry a generation.
- Barge-in and client cancel must stop current audio and prevent stale chunks from reaching the browser.

## Phase 6 — Server TTS scheduling

- Move text chunking and TTS scheduling behind the realtime session.
- Emit ordered `response.output_audio.delta` events.
- Keep low-level standalone TTS routes as fallback surfaces.

## Phase 7 — Browser realtime client

- Add a typed web realtime client for the shared React app.
- Keep legacy clients available during migration.
- The new client should use one socket for audio, transcript, text, audio output, cancellation, and metrics events.

## Phase 8 — Latency telemetry

Track per-response metrics:

- session start
- first audio append
- speech start
- first transcript delta
- final transcript
- response created
- first text delta
- first audio delta
- output audio done
- response done
- cancellation latency
- stale chunk drops

## Phase 9 — Backend optimization

- Add a benchmark contract for STT/TTS backend comparison.
- Support real backend adapters behind the same deterministic contract.
- Keep fake providers for tests.

## Phase 10 — Compatibility mode

- Prefer OpenAI/HF-style realtime event names where practical.
- Keep Omnix-specific metrics and compatibility metadata in additive fields.
- Preserve a stable event contract for external realtime clients.

## Definition of done

Live speech reaches HF parity when a single realtime socket can handle audio input, VAD, streaming transcript, LLM streaming, TTS audio deltas, cancellation, barge-in stale-output suppression, metrics, and deterministic tests without depending on browser-only orchestration.
