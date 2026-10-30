# Omnix Live Portrait — Plan & Roadmap

**Status:** Reviewed, plan revision 4 (four review rounds; the last found no blocker or major issue). Owner decisions D-1 to D-6 and Q-1 settled 2026-10-29. Phase 0 has started: the standalone pass, its optimizations and lip-sync scores are done (see Phase 0 status). Phase 0 decides whether the rest goes ahead.
**Date:** 2026-10-29
**Primary route:** live calls in Chat and Character Mode (`web/src/features/assistant`, `src/app/platform/live_voice`)
**Model:** FLOAT, "Generative Motion Latent Flow Matching for Audio-driven Talking Portrait" (ICCV 2025): [paper](https://arxiv.org/abs/2412.01064), [code](https://github.com/deepbrainai-research/float)
**Looked at, not adopted:** [mohamed-em2m/fast-float](https://github.com/mohamed-em2m/fast-float)

## Summary

A character in a live call gets a talking-head video made from a single portrait image. The video is lip-synced to the voice the character is speaking at that moment. FLOAT turns speech audio into head and lip motion and renders 512×512 frames at 25 fps.

We don't adopt fast-float. We build FLOAT into the stack live calls already run on:
- the persistent live-call TTS websocket, synthesizing phrase by phrase
- cancellation by output and generation epoch
- speculative TTS
- the audio worklet's segment clock
- the avatar pack renderers
- the model catalog and desktop bundles
- the model-service boundary (ADR-0012)

| Phase | Delivers |
| --- | --- |
| 0 (go/no-go) | A spike on the 4090: streaming method, time to first frame, VRAM, and the paired effect on live-voice latency and LLM speed |
| 1 | Catalog and install (FLOAT, its audio models and a face detector, as a desktop bundle) and a `portrait` model service with a streaming session API and admission control |
| 2 | The gateway copies phrase audio to the portrait service, cancels it with the reply, and runs an avatar websocket bound to the call |
| 3 | A rest-pose idle loop, a `portrait` renderer timed against the segment clock, speculative first frames, and adaptive quality for remote clients |
| 4 | Portrait setup in the avatar packs panel, emotion mapping, and a cache cleaned up with its pack |
| 5 | Hardening: release-gate scenarios with a portrait on, paired on/off thresholds, and remote runs over throttled links |

**Out of scope:**
- several faces in one frame
- full-body video
- macOS or MLX (Macs keep the current renderers)
- recording or exporting call video
- a WebRTC or LiveKit stack

## Why not fast-float

fast-float wraps FLOAT in a FastAPI server with a studio UI and WebSocket, WebRTC and LiveKit outputs. Its inference code (`fast_float/core/inference_optimized.py`) shows these limits for a live call:

| Area | fast-float | What a live call needs |
| --- | --- | --- |
| Audio input | The whole clip per request | Audio arriving phrase by phrase while TTS is still speaking |
| Continuity | Batched chunks each "start from zero prev-frames", so motion jumps at chunk joins | Each window conditioned on the previous one's committed motion and audio features, which is how FLOAT was trained |
| Live output | "batched chunk generation does not support a frame dispatcher yet" | Frames sent out while the next window is still generating |
| Portrait encoding | Repeated on every request | Once per tenant and portrait image |
| Interrupting a reply | None | Our `(output_id, generation_epoch)` cancellation |
| Published numbers | None (FPS, latency or VRAM) | Measured on our hardware (Phase 0) |

Ideas we keep from it:
- fp16 autocast for sampling and decoding together
- decoding several frames per decoder call (upstream decodes one frame per Python loop iteration). Batches stay small so cancellation stays responsive; see GPU sharing.
- TensorRT for the image decoder, if Phase 0 shows we need it
- GPU encoding of frames

## Where we are today

### Audio path

- Live calls stream PCM16 over one websocket that stays open for the call (`src/app/platform/live_voice/transport/websocket.py`, `/api/tts/live-call/websocket`).
- **One request per phrase.** The browser sends a request per phrase carrying `output_id`, `generation_epoch`, `segment_id` (the browser makes it with `createSpeechSegmentId(traceId, phraseIndex)`) and `phrase_index`. The handler synthesizes phrases one at a time (`_stream_phrase`).
- **Binary frames are bare PCM.** The ids travel on the JSON `start`, `format` and `done` messages around them. A `format` message can change the sample rate mid-stream; the default is `DEFAULT_SAMPLE_RATE = 24_000`.
- **Cancellation is explicit.** The client sends `cancel` with the exact `(output_id, generation_epoch)`. The server does not cancel older audio just because a newer epoch appears.
- **The TTS lane** (`speech/tts_lane.py`, `PriorityTtsScheduler`) orders TTS generation and gives accepted turns priority. It does not send audio.
- **Speculative TTS** (`speech/speculative_tts.py`, plus `chat_speculative_tts.py` for chat) makes audio before a turn is accepted.
    - Entries are keyed by `generation_id` and claimed by text-prefix match (`_claim_entry`).
    - A claim can replay a cached prefix and then synthesize the remainder fresh.
    - Replayed chunks carry `speculation_generation_id` in their timing.
- **A call lease.** Each call takes a `LiveSpeechLease` keyed `live-call:{id(websocket)}`, so GPU engine swaps wait while a call is live.

### Browser playback clock

`worklets/live-voice-pcm-stream.worklet.ts` and `live-voice-pcm-session.ts`:
- **Per-segment counter.** Each phrase is its own segment. `segment_played_samples` resets to 0 at every `segment_started`, and counts at the AudioContext rate after resampling.
- **Browser-only silences.** The browser inserts clause silences between phrases (`enqueueSilence`), which the gateway never sees.
- **Start buffer.** Playback waits for `START_BUFFER_SECONDS = 0.4` of buffered speech.
- **Rebuffering.** An `underrun` pauses playback to rebuffer, and `resumed` restarts it.
- **Infrequent progress.** `render_progress` posts only every 0.5 s. `avatar_frame` (a quantized mouth frame plus RMS) posts only when the frame changes.
- **"Played" means rendered by the worklet**, not heard. Output latency is separate; `getOutputTimestamp` is already wrapped in the session.

### Avatars

- `CharacterAvatarPack` (`characters/avatar_models.py`, `extra="forbid"`) has three renderers: `sprite`, `live2d` and `rive`. `validate_renderable_pack` requires `rig_asset_id` for every renderer except `sprite`.
- Packs are stored per tenant (`persistence/avatar_store.py`).
- `resolve_live_call_runtime` (`characters/live_call.py`) attaches the pack to the call.
- `LiveCallVisual.tsx` chooses between the sprite, a Live2D host and the voice orb.
- Visemes come from text and are only fitted to the audio's length (`characters/visemes.py`).
- `LiveCallSpeechStyle.emotion` is a per-character default, not per utterance.

### Models

- Catalog entries live in `app/models/catalog.json`. `app/models/catalog.py` validates them and `platform/voice/model_catalog.py` is a speech view over them.
- **What the schema allows today:**
    - `source` must be `huggingface` or `package` (catalog.py:258–260)
    - `ModelKind` is `tts | stt | audio`
    - `requires_acceptance` is true only for `huggingface`
- **How installs run:**
    - `install_model` (`platform/voice/model_install.py`) raises for anything but Hugging Face and checks digests with `_check_digests`.
    - On desktop, installs go through `model_packs` as bundles: a capability's models plus the runtime packs (environments) they run in.

### GPU services and gates

- **Services.** Speech models run in model services (`docs/architecture/VOICE_MODEL_SERVICES.md`). The resident set is TTS, live STT and the local LLM. Exempt helpers (`src/services/helper_models.py`) check free VRAM only.
- **No compute arbitration between processes.** Windows time-slices the GPU between them, and there is no MPS.
- **Release gate.** `platform/live_voice/release_gate.py` has absolute thresholds on `stt_finalize_ms`, `final_to_first_token_ms`, `first_token_to_first_audio_ms` and `interruption_to_silence_ms`.
    - The browser records `first_token_to_first_audio_ms` when the first audio frame is received, not when it is heard (`live-voice-release-observer.ts`).
    - The gate has no paired on/off comparison.

## How FLOAT works, and what streaming needs from it

Defaults in upstream `options/base_options.py`:
- 25 fps, 16 kHz audio, 512×512 output
- `wav2vec_sec = 2` (50 frames) and `num_prev_frames = 10`
- `nfe = 10` with the Euler method: `linspace(0, 1, nfe)`, which is 9 steps. `sample()` ignores its `nfe` argument and reads `opt.nfe`.
- `a_cfg_scale = 2.0`. Guidance already runs as one batch of three in `FMT.forward_with_cfv`, so batching it is not an optimisation for us.
- `wav2vec2-base-960h`, using all hidden layers
- The emotion encoder (`Audio2Emotion`) is built in `FLOAT.__init__` whether or not speech-to-emotion is used.
- Upstream pins torch 2.0.1 and transformers 4.30.2, tested on Python 3.8 on Linux.

Upstream inference (`models/float/FLOAT.py`):
1. Encode the portrait once into an identity latent and decoder features.
2. Encode the whole clip's audio with wav2vec2. The feature extractor normalizes the input as a whole.
3. Generate motion over **non-overlapping** 50-frame windows (`wa[:, t*50:(t+1)*50]`). The last window is padded by replication.
    - Each window is conditioned on a carry: the previous window's last 10 motion latents **and** its last 10 audio features (`prev_x_t = sample_t[:, -10:]`, `prev_wa_t = wa_t[:, -10:]`). The first window's carry is zeros.
    - FMT's positional embedding is fixed at 60 positions (10 carry + 50 window), so every pass costs a full 60-position pass.
4. Decode every frame (identity latent plus motion latent) into an image, one at a time.

### Streaming method: overlapping windows with a hop

Upstream's windows don't overlap, so there's no later context to wait for: a frame is final once its window is generated. To stream with low latency we instead **slide a 50-frame window by a hop `H` < 50** and keep only part of each pass.

1. A pass covers frames `[s, s+50)`.
    - Its carry is the **10 committed frames before `s`**: their motion latents and their audio features.
    - Audio beyond what has arrived is padded by replication, as upstream pads its last window.
2. The pass **commits** frames `[s, s+H)`, where `H` is the number of frames whose audio has at least `R` ms of real audio after it. Uncommitted frames are thrown away and generated again by the next pass.

   `R` doesn't strictly bound what a committed frame depends on:
   - In FMT, attention per layer is local (`enc_dec_mask`, `attention_window = 2`), but across 8 layers and 9 Euler steps a frame can still draw on the whole 60-position window.
   - wav2vec2 attends over its whole buffer.

   So committed frames do see some of the replicate padding. `R` and `H` are chosen by measurement: Phase 0 measures how far committed motion latents and lip-sync scores land from a full-context reference, as a function of `R` and `H`. 200 ms is only the starting point.
3. The next pass starts at `s+H` as soon as enough new audio has arrived for a useful `H` (for example 10 frames, 400 ms). The carry is the 10 frames just committed, never uncommitted frames generated from padding.
4. **Phrase end.** When a phrase's `done` arrives, its last frames, those without `R` of audio after them, stay uncommitted until one of these happens first:
   - **The next phrase's audio arrives in time.** Generation continues across the join using the next phrase's real audio as lookahead. Nothing gets thrown away and nothing jumps.
   - **The deadline.** The held frames are committed with silence padding at their projected play time minus one pass time and a transport margin. The margin is at least the `frame_ack` interval (250 ms) plus the call's measured round-trip time, recomputed per call, because the reported play position can be that old on a slow remote link.
       - The projected play time comes from the browser's `frame_ack` reports of its play position (Phase 3), plus the phrase's remaining duration.
       - Before the first ack, it is estimated from the phrase's first audio arrival plus the 0.4 s start buffer.
       - This covers a slow LLM, where neither the next phrase nor a silence arrives. The browser queues a clause silence only together with the next phrase (`precedingPause` → `enqueueSilence`).
   - **The output ends** (`output_end`, Phase 2). Pad with silence and commit everything.

   **No silence tails are generated.** The browser alone decides how long gaps last (clause silences, pauses waiting for the next phrase, and cues), and often decides late. The renderer covers them from the idle loop instead (Phase 3).

   **The next phrase's carry** is the last 10 committed frames of the previous phrase, which were shown. Phase 0 measures how often the deadline fires and rates the joins it produces.
5. **Audio features.** wav2vec2 runs over a sliding buffer of up to about 4 s ending at the newest audio. Features for committed frames come from the pass that commits them.
    - The normalization upstream applies to the whole input is applied per buffer here.
    - Phase 0 measures how far this lands from whole-clip features.
6. **Input rate.** Audio is resampled to 16 kHz from the rate declared by the phrase's `start`/`format` message. The rate is never assumed to be 24 kHz.

**Cost per pass:**
- one wav2vec2 run over the sliding buffer of up to about 4 s
- one full FMT solve: 9 Euler steps over 60 positions, with three-way guidance

With hop `H` that is `50/H` passes per 50 frames. Decoding costs the same per committed frame whatever the hop. Phase 0 measures all three. The time for one pass (wav2vec2 plus FMT) is also how long the priority pause can be delayed, because a pass can't be split, so Phase 0 bounds it.

**First frames.** The first pass of a reply runs as soon as the received audio covers `H₁ + R`, with `H₁` about 8 frames (320 ms) and `R` about 200 ms, so about 0.5 s of audio. That is close to the 0.4 s the browser already buffers before it starts playing. The carry is the rest pose (Phase 3), not zeros. Starting from a part-filled window, padded by replication, is outside what FLOAT was trained on, so Phase 0 rates it against a full-window baseline.

## Target architecture

```
browser                              gateway (live_voice)                          portrait service (own env)
-------                              --------------------                          --------------------------
TTS websocket   <-- start/PCM/done --  _stream_phrase --- copies phrase PCM -----> PortraitStream(call)
  worklet: segment_started,                (ids from start/format/done,            - admission: 1 stream per GPU
  portrait_clock every 20 ms,               declared rate)                         - latent cache (tenant, image SHA-256)
  underrun / resumed                                                               - resample -> 16 kHz
                                                                                   - wav2vec2 over sliding buffer
avatar websocket <-- frames ---------- relay, bound to the call by <-- frames ---- - hop scheduler + 10-frame carry
  canvas renderer                       a server-issued token, drops               - fp16 decode in micro-batches
  draws by (segment_id, offset)         cancelled outputs                          - JPEG at the call's quality level
```

### Invariants

1. **The voice never waits on the portrait** beyond the capped start hold (D-5). If the portrait service is missing, slow, short on VRAM, already serving another call, or failing, the call carries on with the pack's `fallback_renderer`: sprite, Live2D or Rive, or the voice orb.
2. **Cancellation follows the audio.** Frames belong to an `(output_id, generation_epoch)`. When the client cancels that pair, the gateway forwards the cancel. The service stops between decode micro-batches and drops queued frames. The relay and the browser throw away late frames for the pair. After a cancel, the next output starts from the rest pose.
3. **Frames are stamped by segment.** Each frame carries `(output_id, generation_epoch, segment_id, offset)`, where `offset` is in samples at the segment's source rate. The browser converts offsets into its own segment clock (Phase 3). Wall-clock time is never used.
4. **The portrait service gets only audio and a portrait image the gateway resolved itself.** It never sees transcripts, prompts, memory or character secrets. Image bytes never come from the browser.
5. **New models run in a model service** (VOICE_MODEL_SERVICES.md), never in the gateway or a worker.
6. **The portrait is an exempt helper model.** It loads beside the resident set when free VRAM allows and fails fast with a reason when it doesn't. It is never swapped in for TTS, STT or the local LLM. On compute, it yields to TTS (see GPU sharing).

### GPU sharing

Helpers are only arbitrated on VRAM, and Windows time-slices the GPU between processes. So the portrait service keeps its own work small and gives way:
- **Decode micro-batches** of at most 8 frames (Phase 0 tunes this), checking for cancellation between batches. One batch should take tens of milliseconds, so a barge-in waits at most one batch.
- **Yielding to TTS.** While an accepted reply's TTS has not produced its first chunk, the gateway sends `tts_priority{on}`. The service pauses at the next micro-batch or pass boundary, so the pause takes effect within one pass time (bounded in Phase 0). The gateway sends `tts_priority{off}` from a `finally` block: at the first `start`, or on error or cancel before it.
- **Admission.** At most one portrait stream per GPU by default (`OMNIX_PORTRAIT_MAX_STREAMS=1`).
    - A stream is a **lease** with a 2 s heartbeat from the gateway, which expires after 6 s without one.
    - Opening a stream for the same principal and session evicts that principal's older stream, so `browser-reload` gets its portrait back straight away.
    - A different call gets the fallback renderer with the reason "portrait busy".
- **Not managed:** contention with the LLM's token generation, and with TTS for later phrases. The plan measures it and gates it (Phase 0 and the paired gate) but has no scheduler for it. If it fails the gate, the next steps are a lower `nfe`, smaller micro-batches, or a lower decode rate (12.5 fps, as in L3) on the local GPU.

### Portrait service API

Authenticated by `ModelServiceMiddleware`. It binds to loopback when on the same host as the gateway. When API replicas use a shared remote service (ADR-0012), it is reached through `OMNIX_PORTRAIT_URL` with service headers, like the shared TTS service.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Model loaded, VRAM (`gpu.vram_free_bytes`), host commit (`host.commit_free_bytes`), active streams, warm status |
| `POST /portrait/prepare` | `{tenant, image_sha256, image}` from the gateway only. Checks byte and pixel limits before decoding, detects and crops the face, encodes the latent, and caches it under `(tenant, image_sha256, model revision)`. Also warms the kernels with one dummy pass |
| `DELETE /portrait/cache/{tenant}/{image_sha256}` | Called when no pack in the tenant uses that image any more. The gateway checks this with a count over the tenant's packs. A cache miss at stream open just runs `prepare` again |
| `WS /portrait/stream` | One per call, a lease counted against admission. **In:** `open{call_key, principal, session, latent_key, emotion, quality}` and `heartbeat`; then per phrase `phrase_start{output_id, epoch, segment_id, sample_rate}`, binary PCM, `phrase_done{segment_id}`. Also `play_position{segment_id, offset}` (from the browser's `frame_ack`), `output_end{output_id, epoch}`, `cancel{output_id, epoch}`, `tts_priority{on\|off}` and `quality{level}`. For speculation: `spec_start{generation_id, sample_rate}`, binary PCM, `spec_drop{generation_id}`, `spec_bind{generation_id, output_id, epoch, segment_id}` and `spec_prefix_end{generation_id, samples}`. **Every binary PCM block carries a header** of stream id (`segment_id` or `generation_id`) and sample offset, so blocks copied from different threads can't be misordered. **Out:** binary frames (header: `output_id` or `generation_id`, `epoch`, `segment_id`, `offset`, then JPEG) and `pass_done` timing records |
| `POST /portrait/idle` | Renders the idle loop for a latent (Phase 3) |

Errors the caller acts on come back as `200 {"ok": false, "code", "message"}`, following the services rule.

The hop scheduler is plain Python behind a model interface. It covers hop and commit maths, carry selection, the phrase-end deadline, the rest-pose seed, speculative binding, cancellation between micro-batches, and the priority pause. Tests run it against a fake model with no GPU.

**Upstream code.** It is not vendored, shipped or modified (D-1 and Q-1).
- A runtime pack can't carry it: packs are hash-locked wheels, and anything without a wheel is built at release time and shipped in the installer (`app/models/packfiles.py`).
- Instead, the upstream source files are a **`direct` model entry** of their own, `float-code`. Each file is downloaded from `raw.githubusercontent.com` at a pinned commit and checked against its own SHA-256. GitHub archive downloads aren't used, because their checksums aren't stable.
- `float-code` is executable code in a folder the user can write to, so the service **checks its digests every time it starts**, not only at install. On a mismatch it refuses to load.
- The service imports upstream's top-level `models` and `options` packages from that folder under an isolated package name, so they can't clash with other modules called `models` in the service environment.
- Our streaming, batching and fp16 behaviour lives in our own wrapper that calls the upstream modules.
- Leaving out the emotion encoder when speech-to-emotion is unused needs a subclass that skips `Audio2Emotion`. That is a wrapper change; upstream files are not edited.
- **The runtime pack holds only dependencies.** It sits on the desktop torch layer (CPython 3.11, torch 2.6), so upstream's own pins (torch 2.0.1, transformers 4.30.2, Python 3.8) are not an option on desktop. Running on that base is a Phase 0 exit criterion.

### Avatar pack contract

- Add `"portrait"` to `AvatarRenderer`.
- `validate_renderable_pack`: a portrait pack needs `base_asset_id` (the portrait image) and no `rig_asset_id`.
- New `fallback_renderer: Literal["sprite", "live2d", "orb"] = "orb"`, used whenever the portrait isn't available.
    - `rive` is left out because `LiveCallVisual` doesn't render it today.
    - `portrait` is left out by the type itself.
    - A `sprite` or `live2d` fallback needs that renderer's own assets in the pack, checked by the validator.
- New `portrait_emotion` (one of FLOAT's seven labels, or `auto`), defaulting to `neutral`.
- **Compatibility:** the model is `extra="forbid"`, so a build without these fields refuses packs that have them.
    - The fields are added in the same release as the renderer.
    - `avatar_store` is checked for a stored shape that needs a forward migration.
    - The generated web API types are regenerated.

## Phases

### Phase 0 (go/no-go): spike on the 4090

A script under `scripts/` that runs upstream FLOAT through a prototype of the hop scheduler, in a scratch environment. It runs on the desktop torch base (CPython 3.11, torch 2.6) with current transformers. Upstream's own pins can't be used on desktop, so failing on that base is a no-go, not a reason to fall back. No product code changes.

**Inputs:** at least **40 recorded live-call replies** (N = 40), covering short, long and multi-phrase replies. Each includes its phrase PCM, its `start`/`format`/`done` messages, the browser's clause-silence decisions, and **their recorded arrival times**. They are replayed on that schedule, not at an even real-time pace.

**How the load is made:** for the paired runs, the existing `scripts/run_live_voice_performance_benchmark.py` drives real TTS, STT and the configured LLM. Those turns produce new replies of their own. So the spike's input is **time-aligned synthetic load**: a separate spike process feeds the recorded replies into FLOAT, starting each one when a benchmark turn's first TTS chunk arrives. Each run is repeated with the portrait process idle (off) and active (on).

**Statistics:**
- **Per-reply metrics** (N = 40): p50 with a bootstrap 95% confidence interval (2,000 resamples). Comparisons are on p50; p95 is recorded but not gated.
- **Per-pass and per-cancel timings:** gated at p95. These have thousands of samples per run (passes) or at least 200 cancels.

**Results:** recorded in `docs/measurements/portrait-spike-<date>.json`.

| Measure | Target to proceed |
| --- | --- |
| Runs on the desktop torch base (CPython 3.11, torch 2.6) with current transformers | Required |
| Free VRAM and host commit with TTS, STT and the configured LLM resident | ≥ the portrait's measured peak + 1 GB; the peak itself ≤ 4 GB |
| Steady-state work per second of audio (wav2vec2, FMT and decode) | ≤ 0.5 s |
| One pass (wav2vec2 plus FMT), which bounds how late the priority pause can start | ≤ 40 ms p95 |
| Extra start hold: the first frame's ready time minus when the browser would start (0.4 s of audio buffered) | ≤ 150 ms p50 |
| Slack at phrase joins: each held frame's ready time against its play time, for joins where the next phrase arrives in time and joins where the deadline fires (slow LLM) | Ready before play in ≥ 95% of joins |
| Deadline joins | How often they fire is recorded; no visible jump, rated on 10 |
| Joins where the next phrase arrived in time but the browser then inserted a clause silence (the held last frame may show the next phrase's mouth shape) | No visible wrong mouth shape, rated on 10. If it shows, commit phrase ends without lookahead when the controller plans a pause |
| Barge-in, measured over at least 200 cancels | ≤ 60 ms p95 |
| Paired on vs off: `first_token_to_first_audio_ms`, TTS chunk jitter, LLM tokens/s, `stt_finalize_ms` | On's p50 within 10% of off's, with confidence intervals reported |
| Paired underruns per reply | No higher than off |
| Divergence from a full-context reference (whole clip, upstream windows) as a function of `R`, `H` and the per-buffer normalization: motion-latent distance, and SyncNet LSE-C/LSE-D as the FLOAT paper uses | Lip-sync scores within 5% of the reference at the chosen `R` and `H` |
| Rest-pose first pass and phrase joins | No visible jump, rated on 10 replies, alongside the LSE scores |
| Share of accepted replies whose first pass can run from speculative audio before playback | Recorded (it sets how often the hold is zero) |

Also try:
- `nfe` of 10, 7 and 5
- hops `H` of 10, 20 and 40 against FMT cost
- micro-batch sizes 4, 8 and 16
- fp16 eager, then `torch.compile` if Triton works on Windows
- TensorRT for the decoder only if fp16 eager misses the targets

**Exit:** go, go with changes (for example, TensorRT is required, or a longer `H₁` with speculative frames to cover it), or no-go, recorded with the numbers.

#### Phase 0 status (2026-10-29): standalone measurements done, loaded runs to come

The first pass ran `scripts/portrait_spike.py` with FLOAT alone on an otherwise idle 4090, on the desktop torch base. Results are in `docs/measurements/portrait-spike-2026-10-29.json`.

| Measure | Result | Target |
| --- | --- | --- |
| Runs on CPython 3.11, torch 2.6, transformers 4.57 | Yes, with one wrapper change: upstream's wav2vec2 needs `attn_implementation="eager"` | Required |
| Weights in VRAM | 1.15 GB without the emotion model, 2.36 GB with it | — |
| Peak VRAM, streaming path (one stream, decode batch 8, fp32) | 4.09 GB allocated, 5.27 GB reserved | ≤ 4 GB: marginal; a decode batch of 4 should bring it under |
| Work per second of audio (H = 20) | about 0.18 s (25 frames × 4.6 ms decode, plus 1.25 passes × 54 ms) | ≤ 0.5 s: met |
| One pass (wav2vec2 + FMT), nfe 10 | 54 ms p50, 63 ms p95. FMT is 47 ms of it; wav2vec2 is 7 ms | ≤ 40 ms p95: missed |
| One pass, nfe 7 / nfe 5 | 40 ms / 28 ms p50 | — |
| Decode per frame, batch 1 / 4 / 8 / 16 (fp32) | 10.9 / 5.1 / 4.6 / 4.6 ms | — |
| fp16 decode | No faster; PSNR 74 dB against fp32 | — |
| Estimated extra start hold, TTS at 0.25 / 0.5 / 0.8 real-time factor | 129 / 159 / 195 ms | ≤ 150 ms p50: near, before speculative frames |
| Streamed vs whole-clip motion | H = 20 best on all four clips. Within or below the seed-to-seed noise floor (0.59–0.79) | Lip-sync needs LSE-C/D (to come) |
| Per-buffer vs running audio normalization | Identical to 4 decimal places | Per-buffer chosen |

**What it shows:**
- **FMT is launch-bound.** Nine Euler steps of a small 60-position transformer take 47 ms. The likely fixes are CUDA graphs or `torch.compile` in the wrapper, and `nfe = 7` if lip-sync scores hold at it.
- **Decode is CPU-bound.** fp16 doesn't help, and batches past 8 don't either. Upstream's `ToFlow` builds a NumPy grid and copies it to the GPU on every call; caching that grid in the wrapper is the obvious first fix.
- **H = 20 with R = 5–8** is the working choice.
- **The emotion model costs 1.2 GB.** Leaving it out when the emotion is a label is confirmed worthwhile.

**Optimizations (`scripts/portrait_spike.py --optimized`).** Results: `docs/measurements/portrait-spike-optimized-2026-10-29.json`. Three wrapper changes; no upstream file edited:
- The flow grid is built once per size on the GPU.
- The timestep frequency table stays on the GPU.
- Each window's Euler solve is captured as one CUDA graph. Its motion latents are identical to upstream's `odeint` path (difference 0.0).

| Measure | Before | After | Target |
| --- | --- | --- | --- |
| One pass, nfe 10 (p50 / p95) | 53 / 63 ms | 33 / 35 ms | ≤ 40 ms p95: **met** |
| One pass, nfe 7 / nfe 5 (p50) | 33 / 29 ms | 23 / 17 ms | — |
| Decode per frame, batch 4 / 8 | 5.1 / 4.6 ms | 3.8 / 4.0 ms | — |
| Peak VRAM streaming, decode batch 4 (allocated / reserved) | 4.09 / 5.27 GB (batch 8) | 2.09 / 2.83 GB | ≤ 4 GB: **met** |
| Work per second of audio (nfe 10, batch 4) | 0.18 s | 0.14 s | ≤ 0.5 s: met |
| Estimated extra start hold, TTS at 0.25 / 0.5 / 0.8 real-time factor | 129 / 159 / 195 ms | 80 / 110 / 146 ms | ≤ 150 ms p50: **met** (estimate) |

**Lip-sync (`scripts/portrait_lipsync.py`, SyncNet).** Results: `docs/measurements/portrait-lipsync-2026-10-29.json`. Mean over the four clips:

| Variant | LSE-D (lower is better) | LSE-C (higher is better) | LSE-C vs whole-clip nfe 10 |
| --- | --- | --- | --- |
| Whole clip, nfe 10 (upstream) | 8.01 | 6.77 | — |
| Whole clip, nfe 7 | 7.87 | 6.89 | +1.8% |
| Streamed R5 H20, nfe 10 | 8.31 | 6.35 | −6.2% |
| Streamed R8 H20, nfe 10 | 8.29 | 6.40 | −5.5% |
| **Streamed R5 H20, nfe 7** | 8.20 | 6.47 | **−4.4%** |
| Streamed R5 H20, nfe 5 | 8.14 | 6.51 | −3.8% |
| Control: mismatched audio | 14.53 | 1.09 | — |

**What the lip-sync scores show:**
- **The scores separate sync clearly.** Every synced variant is between 6.3 and 6.9 LSE-C; mismatched audio scores 1.1.
- **Fewer sampling steps don't hurt lip-sync.** nfe 7 and 5 score slightly better than 10, both whole-clip and streamed.
- **With nfe 7, streaming is within the 5% target:** LSE-C −4.4%, LSE-D +2.4%. With nfe 10 it is just outside.
- **The loss is concentrated in short replies.** The 5 s Sofia clip loses 13% of its LSE-C when streamed, while the 15 s sample loses nothing. The likely cause is the short, padded first window, which matters most when it's a larger share of the reply. Phase 3's speculative first frames, and a longer `H₁` where speculation covers it, are the levers. Phase 0's live-call replies will show what typical reply lengths look like.
- **The −1 or 0 frame offsets aren't from streaming.** They appear in whole-clip and streamed output alike.

**Choice so far:** nfe 7, `R` 5, `H` 20, decode batch 4, the CUDA-graph solve and the cached grid. One pass is 23 ms p50, and work per second of audio is 0.12 s.

**Still to do in Phase 0:**
- **A rating of the side-by-side videos** by eye. The joins, and the rest-pose start, are rated in the loaded runs.
- **Recorded live-call replies** with their arrival times (N = 40), to replace the estimated start hold. This needs live calls on the gateway.
- **Paired on/off runs** under real TTS, STT and LLM load: start hold, barge-in time, joins and the speculative share. These are scheduled so they never overlap the RPG session's model gates.

### Phase 1: catalog, install and the portrait service

**Catalog and install (D-1, D-2, D-4).**
- Entries go in `app/models/catalog.json`.
- **Catalog changes:**
    - `app/models/catalog.py`:
        - a new `direct` source: a list of `{url, path, sha256}` files
        - `pinned` extended to cover `direct` (it is Hugging Face only today, catalog.py:76)
        - a new `ModelKind` value: `portrait`
    - `platform/voice/model_catalog.py`: `requires_acceptance` true for `direct` as well as `huggingface`, so the licence is always shown (D-1).
    - `model_packs._pack_status`: count `direct` models as installed, not only Hugging Face ones.
- **Five entries (done 2026-10-29), to be grouped as one desktop bundle, `live-portrait`, once the runtime pack exists.** The bundle gets a new `capability`, `min_vram_mb` and `min_commit_mb`, and a `portrait` runtime pack of dependencies only:
    1. `float` (`direct`, folder `float-weights`): `float.pth` from the authors' Google Drive file. `drive.usercontent.google.com/download?...&confirm=t` serves it as a plain, resumable HTTPS download, checked by its SHA-256. The terms text shows both licence statements.
    2. `float-code` (`direct`, folder `float-code`): the ten upstream source files at commit `3b5b2dfc3e`, each from `raw.githubusercontent.com` with its own SHA-256. The digests are of the bytes GitHub serves; a Windows clone's line endings differ.
    3. `wav2vec2-base-960h` (Hugging Face, pinned, Apache-2.0)
    4. `wav2vec-english-speech-emotion-recognition` (Hugging Face, pinned, Apache-2.0). Optional: the spike's wrapper runs FLOAT without it when the emotion is a label, saving 1.2 GB. Only `auto` emotion needs it, so it becomes a bundle option, not a default.
    5. `s3fd-face-detector` (`direct`, BSD-3-Clause): the S3FD weights. Upstream's crop uses only `face_alignment`'s S3FD detector, never its landmarks. So the service builds `face_alignment.detection.sfd.FaceDetector(path_to_detector=...)` from the catalog file, and nothing is downloaded on first use.
- **Install paths (done).**
    - `downloads.download` fetches `direct` files into the same snapshot layout used by the desktop store.
    - `install_model` fetches them into `resources/models/portrait/<folder>`.
    - Both use the resuming, digest-checked `packs.download_file`.
    - Desktop installs go through `model_packs` as the `live-portrait` bundle. Installing the runtime pack needs `models:runtimes:admin`, as for every runtime pack.
- **Manual download (done).** When a host refuses a scripted download, the error names the URL and the exact path to save the file to. A file already there with the right SHA-256 is used without fetching.

**The service.**
- **Code:** `src/services/portrait/portrait_server.py` (FastAPI) and `portrait.in`, compiled to Windows and Linux lock files. It gets its own environment unless Phase 0 shows torch **and** transformers both match an existing one.
- **Launcher:** a `ServiceSpec` with a fixed port (`5501` proposed), an interpreter role, `OMNIX_PORTRAIT_URL`, and an optional-service policy.
- **Behaviour:** the wrapper and hop scheduler described above, plus admission, the priority pause, micro-batch decoding, and the latent cache keyed by tenant and image hash.
- **Lifecycle (revised after the runtime check):** the model loads in the background when the service starts, if the models are installed and VRAM and host commit allow, and `/health` reports `warming` until it is ready. Loading takes about 60 s on the 4090, almost all of it cuDNN building plans for each network's one input shape, so it can't happen on the first `prepare` of a call. The model stays resident (about 2 GB peak) and unloads only after a long idle timeout (30 minutes by default) or when VRAM is needed. A call that arrives while it is warming or unloaded gets the fallback renderer with a reason.

**Done so far (2026-10-29):**
- **The hop scheduler** (`services/portrait/scheduler.py`), with 9 tests against a fake model.
- **Portrait images** (`services/portrait/portrait_image.py`): limits, decoding and upstream's crop on one 360×640 detection canvas. 8 tests.
- **The FLOAT runtime** (`services/portrait/float_runtime.py`): Omnix's own model built from upstream's modules, with nothing patched.
    - wav2vec2 always gets a 100-frame buffer, padded with silence before the audio.
    - The decoder always gets batches of exactly 4.
    - Every network is warmed at load.
    - JPEG is encoded on the CPU.
- **Checked on the GPU** (`scripts/portrait_runtime_check.py`, `scripts/portrait_latency_probe.py`; results in `docs/measurements/portrait-runtime-2026-10-29.json`):
    - With float input, the latents equal the spike's.
    - LSE-C is 6.40, against the spike's streamed 6.47.
    - Passes take 23.5 ms p50.
    - torchvision's GPU JPEG encoder corrupted frames, which is why encoding moved to the CPU.
    - After a few seconds of GPU idle, the first passes take 80–170 ms; 150 ms of GPU work brings them back to 24 ms. In a call, TTS should already have the GPU busy; the loaded Phase 0 runs confirm it. If not, a short wake at `phrase_start` is the fallback.
- **The service** (`services/portrait/portrait_server.py`), built by a `create_app(...)` factory with an injectable loader. 10 contract tests run it against a fake model, without torch.
    - `GET /health` reports `missing`, `short`, `warming`, `ready` or `failed`, plus streams, VRAM and host commit.
    - `POST /portrait/prepare` checks the image digest; cache keys are tenant, image SHA-256 and FLOAT revision.
    - `DELETE /portrait/cache/...` forgets an encoding.
    - `WS /portrait/stream` runs the scheduler on its own worker thread. `cancel` and `tts_priority` take effect between micro-batches. Admission is one lease per GPU: a reload by the same principal and session replaces the old stream, another call gets `portrait_busy`, and a lease expires after 6 s without a message.
    - The model loads in the background at start and unloads after 30 idle minutes with no stream open.
- **Binary messages** (`app/conversation/portrait_stream_contract.py`): a length-prefixed JSON header, then the payload (PCM in, JPEG out). Phase 2's gateway uses the same module.
- **Environment:** `services/portrait/portrait.in` and a hashed Windows lock, `portrait.lock.txt` (pip-compile; torch 2.6 cu124, transformers 4.57.6, timm 1.0.30, face-alignment 1.4.1). The lock pins the versions the GPU checks ran on.
- **Launcher:** interpreter role `portrait` (`OMNIX_PORTRAIT_PYTHON`, conda env `omnix-portrait`), and an optional `ServiceSpec` on port 5501. It auto-starts when that interpreter exists and sets `OMNIX_PORTRAIT_URL`. 2 launcher tests.
- **Architecture lint:** the branch adds no violations. `main` already reports 28 outside this work, the same list on both.
- **Still to do in Phase 1:**
    - the Linux lock
    - the desktop `live-portrait` bundle and its `portrait` runtime pack, which need the desktop release tooling to build the pack's file list
    - creating the `omnix-portrait` environment from the lock, then a smoke test of the service process itself on the GPU

**Tests:**
- the scheduler against a fake model
- the service contract: error shape, authentication, admission refusal, image limits, cache keying and deletion
- the catalog: `direct` validation, acceptance required, bundle planning

### Phase 2: gateway — copying audio, cancelling, avatar websocket

**Runtime.** `resolve_live_call_runtime` marks a call as a portrait call when all of these hold:
- the pack's renderer is `portrait`
- the bundle is installed and accepted
- the service is healthy and has a free stream

Otherwise it records why it fell back.

**Prewarm.** The live-call prewarm resolves the pack's `base_asset_id` on the server and calls `/portrait/prepare`. That warms the latent and the kernels before the first reply.

**Binding.**
- **A `hello` message on accept.** Today the TTS socket sends nothing until the first phrase's `start`. It gains a server `hello` sent as soon as the socket is accepted, carrying:
    - a random **call key**, replacing `id(websocket)`, which isn't unique, in the `LiveSpeechLease` name too
    - an **avatar token**: signed, short-lived, and bound to the principal, the session and the call key

  The protocol version in `transport/capabilities.py` goes up, so the browser knows to wait for `hello`.
- **Compatibility.**
    - Older clients log the unknown `hello` as `unexpected_control_message` and carry on.
    - A new client talking to an older server waits at most 1 s for `hello`, then runs the call without a portrait.
- **The avatar socket.** The browser opens `/api/tts/live-call/avatar-websocket` (under the live-voice feature's routes and permission guard) with the token, straight after `hello`, before any reply. A browser WebSocket can't set `X-Omnix-Call-Id`, so both sockets rely on the `omnix_call_affinity` cookie to reach the same replica (ADR-0012).
- **Refusal.** A token that doesn't match a live TTS connection on that replica is refused.
- **Speculation requests.** Speculative prefetch requests also carry the call key (Phase 3).

**Copying audio.** The hook sits in `_stream_phrase`.
- **What it sends.** For a portrait call it sends `phrase_start` (with the phrase's ids and declared rate, and again on any `format` change), the PCM blocks it sends the browser, and `phrase_done`.
- **The end of an output.** The browser knows when a turn's last phrase has been queued, because the LLM stream has ended. It sends a new `output_end{output_id, epoch}` on the TTS websocket, and the gateway forwards it. The browser sends it from a `finally` block, so a turn whose LLM stream errors or aborts still sends `output_end` (or `cancel`) and doesn't wait for the deadline.
- **Play position.** It forwards the play position from the browser's `frame_ack` as `play_position`, for the phrase-end deadline.
- **Heartbeat.** It keeps the stream's lease alive with `heartbeat`.
- **Priority.** It sends `tts_priority` on and off around an accepted reply's first chunk.
- **Cancellation.** It forwards client `cancel` messages as they are.
- **Never blocks audio.** The copy is non-blocking: when the portrait queue is full, blocks are dropped for the portrait only, the portrait output is marked degraded, and the drop is logged. Audio to the browser is never held up, and the copy does no extra work on the event loop: no resampling or encoding there.

**Relay.** Frames are sent on to the avatar websocket as they are; the JPEG quality is chosen at the service.
- It drops frames for cancelled pairs.
- It records frames received, sent and dropped, plus the event loop's lag, per call.

**Tests:**
- ids and rates copied correctly, including a `format` change
- cancellation reaches the service and stale frames are never sent
- `hello` comes before any phrase
- token binding: wrong principal, wrong call, expired token, another replica
- a stalled or missing portrait service has no effect on audio delivery (the TTS websocket tests, run with a stalling sink)
- an admission refusal falls back cleanly
- a reload evicts the old stream
- the lease expires when heartbeats stop
- `tts_priority{off}` is sent on error and on cancel
- `output_end` is sent when the LLM stream errors or aborts

### Phase 3: idle loop, renderer, sync, speculative frames, remote quality

**Rest pose and idle loop.** This comes first: the hold cap and the degrade path both need it.
- **What FLOAT can and can't do.** It can't be forced to end at a chosen pose, and a pixel crossfade between two different head poses ghosts.
- **Making the loop.** `/portrait/idle` renders about 12 s from silence, seeded from the rest pose (the source portrait's own motion latent). Then:
    - It keeps the least-moving ~6 s span: every frame's motion latent within a set distance of the rest pose.
    - It cuts the loop at the pair of frames whose motion latents are closest.
    - It stores the frames as an asset per latent.
- **Transitions.** Every speaking output starts its carry from the rest pose. Because every idle frame stays close to it, the browser's crossfade between idle and speaking (about 80 ms each way) moves only a small pose difference. Phase 3 rates the ghosting on 10 replies. If it shows, the fallback is service-rendered transition frames that blend motion latents from the idle frame the browser reports.

**Renderer.** `LiveCallVisual.tsx` gets a `portrait` branch: a canvas, plus `livePortraitRenderer.ts`, which owns the avatar websocket, a JPEG decode queue (`createImageBitmap`) and a draw loop.

**Clock.** For portrait calls the worklet posts `portrait_clock` every 20 ms with:
- the active segment's fields (`segment_id`, `output_id`, `generation_epoch`)
- `segment_played_samples`
- the AudioContext time of that count

The renderer keeps a short **history of segment transitions**: each `segment_started`, `segment_completed`, `underrun` and `resumed`, with its AudioContext time.

On each animation frame it:
1. Takes the **heard time** `t = now − output latency`, using `getOutputTimestamp` (or `outputLatency` where that is missing).
2. Looks up in the history which segment was playing at `t`. Subtracting latency from the active segment's count would go negative right after each `segment_started` and leave the previous segment's tail too early.
3. Estimates that segment's position at `t`: the last `portrait_clock` count, plus the elapsed time at the context rate.
    - The estimate never runs more than 20 ms past the last reported count.
    - It stops moving while the worklet is waiting for buffer (after an `underrun`, until `resumed`).
4. Converts the position to the segment's source rate.
5. Draws the newest frame for that segment whose `offset` is at or before that position.
6. Drops frames more than one frame-time behind.

**Gaps, underruns and cues.** Several things play no speech:
- clause-silence segments
- `pause_waiting_for_following_speech`
- cue segments (`enqueueCue`)
- an `underrun` until `resumed`

During any of them the renderer holds the last speaking frame. If the gap passes 250 ms, it crossfades (about 80 ms) into the idle loop. When the next speech segment starts, it crossfades back into that segment's first frame. Since the next phrase's carry is the previous phrase's last committed frames, a short gap shows continuous motion. A long gap passes through the idle loop, which stays near the rest pose (rated with the idle transitions).
- On `underrun` it freezes on the current frame, and resumes at `resumed`.
- `segment_cancelled` and `segment_interrupted` drop that segment's frames and crossfade to the idle loop.

**Start hold (D-5).**
- **What it measures:** the extra delay of the worklet's `started` event beyond the existing 0.4 s start buffer.
- **What it waits for:** only until frames covering the start of the output's first segment have arrived, never past a **250 ms cap**.
- **If the cap passes**, audio starts, the idle loop shows, and the renderer crossfades in when frames arrive.
- **Mid-reply**, audio is never paused to wait for video.
- **Diagnostics:** the hold is a new delivery-ledger event.

**Keeping the hold near zero.**
- **Speculative frames.** Speculative audio never goes through `_stream_phrase`. It is made in `_start_prefetch`'s own thread, started by `POST /api/live/speculation/tts-prefetch`. So it gets its own hooks:
    - **Routing to the call.** The prefetch request carries the call key from `hello`. Today `SpeculativeTtsPrefetchRequest` has no call or tenant. The route checks the key belongs to the caller's live call, then records it on the cache entry.
    - **The copy.** `_start_prefetch` runs on a plain thread, started from a sync route. So the route captures the call's portrait-stream sender at request time: its event loop and a bounded queue.
        - The prefetch thread copies each chunk while still holding `entry.condition`, before it notifies waiters. It sends the chunk as `spec_start{generation_id}` plus PCM blocks, each with its offset, through `loop.call_soon_threadsafe`.
        - When the queue is full, the speculative copy is dropped and the entry is marked unusable for the portrait.
        - Rendering starts from the rest pose and covers only the first one or two passes, to limit wasted GPU.
    - **Claims match the call.** Entries are process-wide (`_ENTRIES`) and claims match on text, so `_claim_entry` also requires a matching call key for entries that have one.
    - **Drops.** Every way an entry can be dropped sends `spec_drop{generation_id}`: pruning in `_prune_entries_locked`, `_cancel_entry`, an abandoned cold claim, and the prefetch cancel route. Today these drop silently, so each one gets an explicit hook.
    - **Binding at claim.**
        - At the **first** replayed chunk (it carries `speculation_generation_id`), `_stream_phrase` sends `spec_bind{generation_id, output_id, epoch, segment_id}`.
        - The service relabels the speculative frames it has already rendered with the output's ids, and they go out at once. That is what makes the hold zero.
        - The entry may still be generating while it is replayed, so the prefix length isn't known yet. While replaying, `_stream_phrase` **does not copy the replayed chunks**: the prefetch thread is already copying them.
        - When the replay ends it sends `spec_prefix_end{generation_id, samples}`. Copying of freshly synthesized audio starts at offset `samples`.
    - **Ordering.** Every PCM block has an offset header, so the service orders the prefix and the remainder by offset whichever thread delivered them first.
    - **Checking the binding.** The service checks `samples` against the speculative PCM it received. A mismatch, or a bind for a `generation_id` not in its stream (dropped, or never copied), means it renders the output from scratch.
- **The first pass.** It runs at about 0.5 s of audio, already close to the browser's 0.4 s start buffer.
- **Warm kernels.** `prepare` already ran when the call opened.
- **Early sending.** The first micro-batch is sent before the rest of the pass is decoded.

**Remote quality (D-6).**
- **Levels:**

  | Level | Size | Frame rate | JPEG quality | Approx. bandwidth |
  | --- | --- | --- | --- | --- |
  | L0 | 512 | 25 fps | 85 | ~8 Mbit/s |
  | L1 | 512 | 25 fps | 70 | ~5 Mbit/s |
  | L2 | 384 | 25 fps | 70 | ~3 Mbit/s |
  | L3 | 384 | 12.5 fps | 70 | ~1.5 Mbit/s |

  The figures are estimates for Phase 5 to confirm.
- **Encoding.** The service encodes only the level the call's client is on; the gateway never re-encodes.
- **Feedback.** The browser sends `frame_ack{segment_id, offset, late_count, decode_ms}` every 250 ms. Starlette can't report a socket's send backlog, so the gateway works out frames in flight from what it sent and what was acked. It steps the level down at once, and back up after 5 s of healthy acks.
- **Fallback.** If frames are still late at L3, the browser switches to the fallback renderer for that output.
- **Loopback** clients start at L0.

**Tests:**
- clock conversion across segments, a rate change, clause silences, underrun and resume, and output latency (with a fake worklet clock)
- the segment-transition lookup at `now − latency`
- clamping the extrapolation
- the hold cap
- binding at the first replayed chunk with no second copy of the prefix
- `spec_prefix_end` while the entry is still generating
- ordering prefix and remainder by offset across threads
- a mismatched length, and a bind for an unknown `generation_id`
- claims refused across calls
- every drop path sending `spec_drop`
- the gap rules: clause silence, waiting for the next phrase, cues, underrun, the 250 ms crossfade to idle
- the phrase-end deadline driven by `play_position`
- frames for cancelled outputs never drawn
- the crossfades
- level stepping driven by acks

### Phase 4: setup, emotion, cleanup

- **Setup.** The avatar packs panel (`web/src/features/setup/AvatarPacksPanel.tsx`) gets a "Portrait" option.
    - The user uploads or picks an image. `prepare` checks it: limits, a face found, cropped to 512×512.
    - A preview of a short sample line plays.
    - The user picks the fallback renderer.
- **Model status.** The panel shows whether the `live-portrait` bundle is installed and links to the Models tool when it isn't (D-4).
- **Emotion.** `portrait_emotion` sets FLOAT's label for the whole call. The per-character `LiveCallSpeechStyle.emotion` is the default where it names one of the seven labels. `auto` (speech-to-emotion) is offered only if Phase 0 shows its cost is acceptable.
- **Cleanup.** Deleting a pack or replacing its portrait removes the idle-loop asset once no pack uses the image, and calls `DELETE /portrait/cache/...` once no pack in the tenant uses it.

### Phase 5: hardening

- **Release gate scenarios.** Run the required live-voice scenarios with a portrait character, including `character-normal`, `hard-stop`, `correction-overlap`, `sustained-overlap`, `tts-failure`, `provider-reconnect`, `browser-reload` and `rapid-interruption-soak`.
- **New metrics:**
    - `first_audible_ms`: when the worklet's `started` fires, plus output latency
    - `start_hold_ms`
    - `av_offset_ms`: the drawn frame's offset against the heard position
    - `underrun_count`
    - `llm_tokens_per_second`
    - `portrait_degrade_count`
    - `portrait_admission_refused`
- **Paired harness.** The benchmark runs each scenario with the portrait off and on, and the gate compares the two.
- **Samples:** at least 40 replies per scenario in each of the on and off runs.
- **Thresholds:**
    - `start_hold_ms` ≤ 150 ms p50 (D-5). The 250 ms cap holds by design; p95 is recorded.
    - `av_offset_ms` within ±40 ms p95. It is measured per drawn frame, so there are thousands of samples.
    - each existing latency metric, and `llm_tokens_per_second`: the on run's p50 within 10% of the off run's, with bootstrap confidence intervals reported. p95 is recorded.
    - `underrun_count` no higher than off
- **Remote:**
    - Rerun on a remote client with throttled links: 20, 8 and 3 Mbit/s, each with 80 ms RTT. Record the level each settles at, how often it degrades, and the gateway's event-loop lag.
    - If L3 isn't enough, H.264 through NVENC, decoded in the browser with WebCodecs, is the later option.
- **Operations:** a diagnostics page entry, and the portrait service's startup, admission and failure modes in `OPERATIONS.md`.

## Files expected to change

| Area | Files |
| --- | --- |
| Spike | `scripts/portrait_spike.py` (Phase 0), recorded replies under `docs/measurements/` |
| Catalog and install | `app/models/catalog.json`, `app/models/catalog.py` (`direct` source, `pinned`, `portrait` kind), `platform/voice/model_catalog.py` (`requires_acceptance`), `platform/voice/model_install.py`, `platform/voice/model_packs.py` (bundle, `_pack_status`), runtime pack lock files |
| Service | `src/services/portrait/` (new), `app/composition/launcher/service_manager.py`, `app/config/launcher.py`, setup scripts and lock files |
| Avatar contract | `platform/characters/avatar_models.py`, `persistence/avatar_store.py`, `live_call.py`, generated web API types |
| Gateway | `platform/live_voice/transport/websocket.py` (`hello`, call key, avatar token, `_stream_phrase` copy hook, `output_end` and `play_position` forwarding, binding and prefix suppression), `transport/capabilities.py` (protocol version), a new `transport/avatar_websocket.py` (and its permission entry if the feature guard needs one), `speech/speculative_tts.py` (call key on the prefetch request and in `_claim_entry`, the copy hook in `_start_prefetch` under `entry.condition`, drop hooks), `speech/chat_speculative_tts.py` |
| Web | `LiveCallVisual.tsx`, a new `livePortraitRenderer.ts`, `live-voice-pcm-stream.worklet.ts` (`portrait_clock`, start hold), `live-voice-pcm-session.ts` (`hello` and its timeout, `output_end`), `live-voice-unified-audio-controller.ts` (`output_end`), `live-voice-delivery-ledger.ts`, `live-voice-release-observer.ts`, the speculation transports (`live-speculation-direct-gateway-transport.ts`: the call key), `AvatarPacksPanel.tsx` |
| Gate | `platform/live_voice/release_gate.py` (paired comparison, new metrics), `scripts/run_live_voice_performance_benchmark.py` |
| Docs | this file, `VOICE_MODEL_SERVICES.md` (the new service), `OPERATIONS.md` |

## Risks

| Risk | Effect | How we handle it |
| --- | --- | --- |
| Compute contention on one GPU (no MPS on Windows) | TTS underruns, slower first audio, slower LLM | Micro-batches, the priority pause, and admission of one stream. Phase 0 and the paired gate measure it |
| The hop scheduler, rest-pose start, or sliding audio features hurt quality | Jumps or wrong lip shapes | Phase 0 rates each against upstream's whole-clip output. Widen `R`, the buffer or `H₁` |
| Video stalls at phrase joins | The face freezes between phrases | Commit held frames at a deadline from the play position; the renderer moves to idle after 250 ms of a gap. Phase 0 measures the slack |
| A/V clock mistakes (segments, rates, latency) | Drift or bad lip-sync | Stamping by segment, `portrait_clock`, output-latency correction, and the `av_offset_ms` gate |
| Windows toolchain (Triton, TensorRT, old upstream pins) | Optimisations or the environment unavailable | fp16 eager is the baseline. Own environment if the pins clash |
| Host memory on Windows | The commit exhaustion seen with Fish | Report host commit in `/health` and refuse to load when headroom is short |
| Google Drive download flaky | Install fails | SHA-256-checked manual drop-in |
| Remote links too slow | Stutter | Levels L0–L3, then the fallback renderer |
| Speculative frames thrown away | Wasted GPU | First pass or two only. Dropped on cache expiry |
| A second call while one is streaming | No portrait for the second call | Admission refusal, the fallback renderer, and a reason shown |
| Licence: "research purposes only" wording | Use outside research may not be covered | Settled (Q-1): non-commercial is the term that matters. Unmodified upstream code is installed, not vendored |

## Owner decisions (settled 2026-10-29)

- **D-1 Licence: accepted.** Omnix is non-commercial, so the CC BY-NC-ND 4.0 terms are acceptable, including for the desktop releases. The catalog shows the licence and asks for acceptance at install, like every model; `direct` entries require it too. Neither the weights nor the code are shipped or modified: both are downloaded per install from upstream at pinned digests, and our behaviour lives in our own wrapper.
- **D-2 Weights: downloaded from the official sources, pinned.**
    - `float.pth` comes from the authors' Google Drive link through the new `direct` source, with a SHA-256 pin and a manual drop-in fallback.
    - The audio encoders come from Hugging Face. The face detector's weights are pinned too.
    - No third-party mirror is used.
- **D-3 Likeness consent: not required.**
- **D-4 Install: from the Models tool**, as the `live-portrait` bundle (its models plus the `portrait` runtime pack) through the existing catalog, acceptance and pack flows. The avatar packs panel only shows status and links there.
- **D-5 Start hold: as small as possible.**
    - Measured as the extra delay beyond the existing 0.4 s start buffer.
    - ≤ 150 ms p50 is a gate threshold. The 250 ms hard cap holds by design; p95 is recorded.
    - Zero when speculative frames cover the start.
- **D-6 Clients: both local and remote, from the first release.** The avatar socket is bound to the call by a server-issued token and replica affinity. Adaptive levels down to L3, then the fallback renderer.

- **Q-1 Conflicting licence statements: settled 2026-10-29.** Upstream's two licence statements disagree:
    - `LICENSE.md` is **CC BY-NC 4.0**: non-commercial, derivatives allowed, no research-only clause.
    - The README says **CC BY-NC-ND 4.0** and that the work "may use it only for research purposes".

  The owner's decision: **the non-commercial term is what matters**, and Omnix is non-commercial, so no further clearance is needed. Phase 1 install goes ahead. The catalog's terms text still shows both statements, and the weights and code are still neither modified nor redistributed.

## Validation

- **Unit:** the hop scheduler with a fake model; the catalog `direct` source and bundle; the service contract and admission; gateway copying, cancellation and token binding; renderer clock maths with a fake worklet.
- **Web:** `npm --prefix web run test` for the renderer, the worklet clock and the panel, and `npm --prefix web run build`.
- **Real model:** the Phase 0 spike numbers, then the paired live-voice release gate with the portrait off and on, recorded in `docs/measurements/`.
- **Each phase** ends with its tests passing on the final diff and this document's status updated.

## Review log

- **Round 1 (2026-10-29).** The independent review found:
    - frames stamped on one timeline per output, which the browser's per-segment clock doesn't match
    - a commit rule that didn't fit FLOAT's non-overlapping windows or its carry of audio features
    - video stalls at phrase joins
    - a first-frame target that contradicted itself, and gate metrics that couldn't see the hold
    - no compute arbitration
    - speculative frames keyed wrongly, and an avatar socket not bound to its call
    - a prepare cache that could be poisoned across tenants or images
    - wrong catalog and install facts
    - D-1 not covering vendored code
    - minor factual errors

  Revision 2 addresses all of them: per-segment stamps and `portrait_clock`; the hop scheduler with a full carry; phrase flush and tail; the hold defined against the start buffer; the paired gate; micro-batches, the priority pause and admission; speculative streams keyed by `generation_id`; the avatar token and affinity; cache keys of tenant plus image hash; the `direct` source, bundle and acceptance; no vendoring, plus Q-1; and corrected facts.
- **Round 2 (2026-10-29).** The review found:
    - `R` doesn't bound what a frame depends on, since FMT's receptive field covers the whole window
    - speculative PCM never reaches `_stream_phrase`
    - runtime packs would ship upstream code
    - no message to carry the avatar token before the first reply, and `id(websocket)` isn't unique
    - the renderer would switch segments early by the output latency
    - silence tails that don't match the browser's silences
    - the priority pause only covers part of the contention
    - admission breaks browser reload
    - Phase 0 targets not measurable at gate sample sizes
    - an idle loop that can't be forced to a pose
    - catalog details, and consistency gaps
    - a licence correction: `LICENSE.md` is CC BY-NC 4.0

  Revision 3 addresses them:
    - `R` and `H` chosen by measuring divergence, with LSE-C/D
    - copy, drop and bind hooks for speculation, with no second copy of the prefix
    - `float-code` as a `direct` entry and a dependencies-only runtime pack on the desktop torch base
    - a server `hello` with a random call key and token, using the affinity cookie
    - segment-transition history and clamped extrapolation
    - browser-reported `silence_queued` and holding phrase ends
    - pass-time bound, `finally`-sent `off`, and the unmanaged contention stated
    - a heartbeat lease with eviction on reload
    - N = 40 with bootstrap intervals on p50, and the load harness described
    - an idle loop near the rest pose, cut at the closest latents
    - catalog and file fixes
    - Q-1 updated
- **Round 3 (2026-10-29).** The final pass found these problems:
    - the speculative bind couldn't know the prefix length, and prefix and remainder could arrive out of order across threads
    - frames held at a phrase end had no deadline when the LLM is slow, and `output_end` had no sender
    - silence tails couldn't match lengths the worklet only learns later
    - leftover text contradicting revision 3

  Revision 4 addresses them:
    - bind at the first replayed chunk, then `spec_prefix_end`
    - offset headers on every PCM block, and the copy made under `entry.condition` through `call_soon_threadsafe`
    - claims restricted to the call
    - a phrase-end deadline from the browser's play position
    - `output_end` sent by the browser
    - silence tails removed, with gaps, waits, cues and underruns covered by holding the frame and then the idle loop
    - `float-code` digests checked at every start
    - a 1 s timeout waiting for `hello`
    - Phase 0 and Phase 5 statistics made consistent (p50 for per-reply metrics; p95 only for per-pass, per-cancel and per-frame timings)
    - stale text removed

  The reviewer's verdict on revision 3: Phase 0 ready, and Phases 1–2 sound after a passing Phase 0 once Q-1 is answered. Phase 3 needed exactly these fixes.
- **Round 4 (2026-10-29), confirmation.** M1–M4 resolved, with no new blocker or major problem. Verdict: **Phase 0 is ready to start, and Phases 1–3 are sound to proceed after a passing Phase 0. Phase 1 install waits on Q-1.** Four minor clarifications were applied:
    - the deadline's transport margin covers the ack interval plus RTT
    - `output_end` is sent from `finally`, with a test
    - D-5's wording matches Phase 5
    - a Phase 0 rating for clause-silence joins that used lookahead
