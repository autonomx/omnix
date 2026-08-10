# Local live-voice hardware benchmark

This benchmark replaces the manual cycle of speaking five test turns, copying logs, and calculating latency by hand. It runs on the real local Omnix stack and is intentionally suitable for a future self-hosted GitHub Actions runner.

## What it exercises

The browser test drives the same live-call path as a real user:

```text
interaction-1.wav ... interaction-5.wav (in order)
  -> programmable Chromium microphone MediaStream
  -> Omnix browser capture/resampling
  -> Kyutai adapter / authoritative endpointing
  -> LLM speculation + accepted chat request
  -> configured LLM provider (expected: Cerebras)
  -> Faster Qwen3 TTS
  -> live PCM WebSocket
  -> AudioWorklet playback
  -> resources/logs diagnostics
```

The five WAVs are injected one at a time. The next WAV does not start until the preceding assistant response has entered and then exited the `speaking` playback state. This prevents the test fixture from accidentally becoming a barge-in test.

## Prerequisites

Run the normal local services first. The benchmark does not start or stop GPU services because doing so would change the hardware state being measured.

Required local services/configuration:

- Vite web app at `http://127.0.0.1:5173`
- Omnix gateway and Faster Qwen3 TTS reachable through the web app
- Kyutai adapter at `http://127.0.0.1:5202`
- Kyutai `authority=test`, normally with endpoint threshold `0.75`
- LLM provider configured as `cerebras`
- Cerebras credential available to the already-running gateway (local protected provider secret, or `CEREBRAS_API_KEY` in the gateway process environment)
- Python Playwright + Chromium installed

For the current latency A/B configuration, start Vite with:

```powershell
$env:VITE_ASSISTANT_STT_URL="http://127.0.0.1:5202?language=en&authority=test&endpoint_threshold=0.75&fallback=http%3A%2F%2F127.0.0.1%3A5201"
$env:VITE_LIVE_SPECULATION_ENABLED="true"
$env:VITE_LIVE_TTS_SPECULATION_ENABLED="false"
npm run web:dev
```

If Playwright Chromium is not installed:

```powershell
python -m playwright install chromium
```

## Run locally

From the repository root:

```powershell
python scripts/run_live_voice_performance_benchmark.py --headed
```

Headless Chromium is the default; omit `--headed` when a visible browser is unnecessary:

```powershell
python scripts/run_live_voice_performance_benchmark.py
```

The runner performs three preflight checks before opening Chromium:

1. `/chatbot` is reachable.
2. Kyutai `/authorityz?language=en&mode=test` is reachable.
3. `/api/tts/live-call/capabilities` is reachable.

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

The two `.run.log` files contain only records from the benchmark time window, so previous manual calls in the normal rolling logs do not contaminate the result.

## Default gates

The first version is measurement-first. It fails on correctness/safety problems:

- not exactly five driven WAV interactions
- not exactly five completed release-metric turns
- live LLM routing is not Cerebras
- no Kyutai STT diagnostics are observed
- any AudioWorklet underrun is observed
- speculative TTS starts while the benchmark expects it disabled
- the browser driver itself fails

It reports, but does not yet hard-code, a production latency threshold. This is intentional because the LLM provider has changed to Cerebras and the first clean hardware run should establish the new baseline.

Optional hard limits can be supplied immediately:

```powershell
python scripts/run_live_voice_performance_benchmark.py `
  --max-median-ms 1500 `
  --max-p95-ms 2000
```

The limits apply to `speech_end_to_first_playback_ms`.

To benchmark a configuration where speculative TTS is enabled:

```powershell
python scripts/run_live_voice_performance_benchmark.py --expect-tts-speculation enabled
```

Or use `--expect-tts-speculation any` when that feature is not part of the experiment.

## Metrics

The report groups the existing `release_metric` events by voice turn and calculates median/p95/min/max for:

- STT finalize
- speech end -> authoritative final
- final -> first LLM token
- first token -> first audio
- final -> first playback
- first PCM -> first playback
- speech end -> first playback

It additionally reports:

- LLM speculative reuse count
- LLM provider first-text latency
- first-phrase (`p0`) Qwen lane wait
- p0 provider -> first raw PCM
- p0 raw PCM -> audible block
- p0 route -> first transport frame
- speculative-TTS start count
- AudioWorklet underruns

## Why the microphone is programmable

Chromium's `--use-file-for-fake-audio-capture` flag accepts only one fixed file for the browser process. Concatenating all five interactions into one WAV would make the silence between turns depend on assistant response length and would turn long responses into unintended barge-ins.

Instead, the test installs a pre-page `getUserMedia` override backed by a WebAudio `MediaStreamDestination`. The application receives a normal microphone `MediaStream`, but Playwright can inject one WAV at a time and wait for the full assistant playback cycle before injecting the next file.

## Future self-hosted GitHub Actions use

The local runner is deliberately the unit of execution. A future self-hosted Windows/RTX 4090 workflow only needs to:

1. start the same Omnix services with `CEREBRAS_API_KEY` from the GitHub `dev` environment,
2. invoke `python scripts/run_live_voice_performance_benchmark.py`, and
3. upload `resources/logs/benchmarks/<run-id>` as the workflow artifact.

The performance measurement logic therefore remains identical between a manual local run and the eventual GitHub Actions hardware run.
