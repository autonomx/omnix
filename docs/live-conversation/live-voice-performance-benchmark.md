# Local live-voice hardware benchmark

This benchmark drives the real local Omnix live-call stack with five committed WAV interactions and measures the existing release diagnostics.

## What it exercises

```text
interaction-1.wav ... interaction-5.wav
  -> programmable Chromium microphone MediaStream
  -> Omnix browser capture/resampling
  -> Nemotron transcript + Parakeet Realtime EOU
  -> LLM speculation + accepted chat request
  -> configured LLM provider
  -> Faster Qwen3 TTS
  -> live PCM WebSocket
  -> AudioWorklet playback
  -> resources/logs diagnostics
```

The next WAV starts only after the preceding assistant response has entered and exited the speaking state, so the fixture does not accidentally become a barge-in test.

## Prerequisites

Run the normal local services first. The benchmark does not start or stop GPU services because doing so would change the measured hardware state.

Required:

- Vite web app at `http://127.0.0.1:5173`
- Omnix gateway and Faster Qwen3 TTS
- Nemotron + Parakeet EOU STT at `http://127.0.0.1:5201`
- configured LLM provider available to the gateway
- Python Playwright + Chromium

Default live-STT browser configuration:

```powershell
$env:VITE_ASSISTANT_STT_URL="http://127.0.0.1:5201?language=en&authority=auto&endpoint_threshold=0.5"
$env:VITE_LIVE_SPECULATION_ENABLED="true"
$env:VITE_LIVE_TTS_SPECULATION_ENABLED="false"
npm run web:dev
```

If Chromium is not installed:

```powershell
python -m playwright install chromium
```

## Run locally

```powershell
python scripts/run_live_voice_performance_benchmark.py --headed
```

Headless Chromium is the default; omit `--headed` when a visible browser is unnecessary.

The benchmark should preflight the web app, the STT `/authorityz` readiness endpoint on port 5201, and `/api/tts/live-call/capabilities` before opening Chromium.

## Result files

Each run gets an isolated directory:

```text
resources/logs/benchmarks/YYYYMMDD-HHMMSS-<git-sha>/
  manifest.json
  report.json
  report.md
  live-call-streaming.run.log
  tts-streaming.run.log
```

## Correctness gates

A clean run should require:

- exactly five driven WAV interactions
- exactly five completed release-metric turns
- the expected live LLM provider
- negotiated STT provider `nemotron_parakeet_eou`
- no AudioWorklet underruns
- speculative TTS behavior matching the requested benchmark mode
- no browser-driver failure

Optional hard latency limits apply to `speech_end_to_first_playback_ms`:

```powershell
python scripts/run_live_voice_performance_benchmark.py `
  --max-median-ms 1500 `
  --max-p95-ms 2000
```

## Metrics

The report groups existing `release_metric` events by voice turn and calculates median/p95/min/max for STT finalize, speech-end to authoritative final, final to first LLM token, first token to first audio, final to first playback, first PCM to first playback, and speech-end to first playback.

It also reports LLM speculative reuse, provider first-text latency, first-phrase TTS lane wait, provider-to-first-raw-PCM latency, speculative TTS starts, and AudioWorklet underruns.

## Future self-hosted CI

The local runner remains the unit of execution. A future self-hosted Windows/RTX 4090 workflow only needs to start the same Omnix services, invoke the runner, and upload the generated benchmark directory as a workflow artifact.
