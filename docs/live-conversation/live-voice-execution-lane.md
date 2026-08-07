# Live voice execution lane

The live-call pipeline can use an opt-in provider/model and TTS lane without changing the selected model for ordinary text chat.

## Modes

The default mode is `session`, which preserves the chat session's provider and model.

```powershell
$env:OMNIX_LIVE_VOICE_EXECUTION_MODE="session"
```

Dedicated mode resolves both authoritative live turns and side-effect-free speculative turns through the same configured provider/model:

```powershell
$env:OMNIX_LIVE_VOICE_EXECUTION_MODE="dedicated"
$env:OMNIX_LIVE_VOICE_PROVIDER_ID="lmstudio"
$env:OMNIX_LIVE_VOICE_MODEL_ID="qwen-live-fast"
```

The model must already be available through the configured provider. The lane does not download, load, or silently replace models. Missing providers or models fail through the existing provider error path.

## Dedicated TTS

Accepted live speech, response continuations, and speculative first clauses share an accepted-first scheduler:

1. accepted interactive speech;
2. continuation of an audible response;
3. unaccepted speculative first-clause work.

An accepted request can cancel an active unaccepted speculative stream at the provider's next yielded chunk. A speculative stream that becomes authoritative is promoted in place and its buffered PCM can be replayed without a second generation.

The shared TTS provider remains the default. A separately instantiated live-call provider is opt-in:

```powershell
$env:OMNIX_LIVE_TTS_DEDICATED="true"
$env:OMNIX_LIVE_TTS_PROVIDER_NAME="faster-qwen3-tts"
```

A dedicated Faster Qwen instance requires enough additional VRAM for a second provider instance. On a single 24 GB GPU, use the shared provider with the accepted-first logical lane unless measurements show the extra instance fits without degrading STT or LLM latency.

## Runtime status

The gateway exposes the resolved configuration and scheduler state at:

```text
GET /api/live/voice/execution-lane
```

Diagnostics include `execution_lane` or `live_execution_lane` for normal chat routing, speculation, speculative TTS, and live-call provider resolution.

## Latency measurement

The primary perceived-latency metric is:

```text
speech_end_to_first_playback_ms
```

It is calculated from the immutable live turn timeline rather than inferred from STT finalization. Promotion still requires clean hardware measurements; enabling a dedicated lane does not itself prove the 500 ms target.

## Native speech-to-speech compatibility

The client turn coordinator and execution-lane boundary deliberately separate turn ownership from the text LLM and TTS implementations. A future native duplex speech adapter can implement the same lifecycle—start, update, commit, cancel, playback—without returning to DOM transcript reads or application-wide fetch interception.
