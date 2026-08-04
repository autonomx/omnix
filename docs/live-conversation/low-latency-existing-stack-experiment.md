# Existing-stack low-latency voice experiment

This branch is an independent latency experiment built directly from `main`.
It keeps the existing Omnix live-voice stack unchanged at the provider boundary:

```text
Parakeet STT -> existing chat/LLM stream -> Qwen TTS -> PCM AudioWorklet
```

It intentionally contains no alternate STT provider, provider-selection logic,
semantic endpoint model, pre-final transcript speculation, or launcher service
for another speech runtime. Those belong to a separate experiment and must not
be introduced here.

## Changes in this experiment

1. **First-clause-only fast path**
   - First spoken clause: 12-character minimum and 160 ms deadline.
   - Later clauses: 24-character minimum and 420 ms deadline.
   - Existing punctuation, abbreviation, URL, number, quote, and parenthetical
     protections remain active.

2. **Lower owned playback onset buffer**
   - The unified PCM session receives a 220 ms minimum buffered-speech target
     for the first phrase instead of 400 ms.
   - The PCM session remains the sole owner of its AudioWorklet and start policy.
   - No browser constructors, prototypes, or global message ports are patched.

3. **Audible latency measurement**
   - PCM arrival is recorded separately at `phrase_first_frame_received`.
   - First audio is measured at the AudioWorklet `worklet_segment_started`
     event, when playback actually begins.
   - The existing durable metric name `first_token_to_first_audio_ms` remains
     unchanged for schema compatibility, but now represents audible output.

## Deliberate exclusions

- No STT replacement or STT protocol changes.
- No pre-final LLM generation from partial transcripts.
- No speculative or pre-accept TTS.
- No new model services, Docker services, dependencies, launcher wiring, or
  provider-specific workflows.
- No claim of adaptive buffering until rebuffer and maximum-rebuffer controls
  are owned and exercised end-to-end by the PCM session.

## Comparison criteria

Compare this branch against the alternate implementation using the same local
hardware, character voice, prompt, and scenario set. The primary metric is
speech-end to first audible substantive response. Also track p95 latency,
interruption-to-silence, audible underruns, phrase fragmentation, and cloned
voice quality.
