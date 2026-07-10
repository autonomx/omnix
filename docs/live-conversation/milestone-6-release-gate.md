# Milestone 6 — Live Conversation Release Gate

Status: repository implementation complete; production hardware evidence must be collected on the target Windows/Chrome runtime before enablement.

## Purpose

Milestones 1–5 established authoritative turn lifecycle, playback-aware context, adaptive floor timing, overlap classification, and optional non-authoritative acknowledgements. Milestone 6 makes release evidence explicit and machine-evaluable.

The gate never assumes that passing unit tests proves microphone, STT, provider, TTS, speaker, echo-cancellation, or browser timing. Missing evidence produces `insufficient`, not `pass`.

## Measured latency boundaries

The browser observer records content-free diagnostics for:

| Metric | Boundary | Default p95 limit |
|---|---|---:|
| `stt_finalize_ms` | final requested → final transcript | 1,500 ms |
| `final_to_first_token_ms` | final transcript → first provider text chunk | 5,000 ms |
| `first_token_to_first_audio_ms` | first provider text chunk → first TTS audio frame | 3,500 ms |
| `interruption_to_silence_ms` | confirmed interruption event → stopped audio session | 500 ms |

Quality trials record whether these failures occurred:

- `false_interruption`
- `missed_interruption`
- `backchannel_false_positive`

Default rate limits are 5%, 10%, and 5% respectively. At least five latency observations per boundary and ten labelled trials per quality metric are required by the default gate.

## Required runtime scenarios

Every scenario must produce at least one release diagnostic during the selected evaluation window:

1. `system-normal`
2. `character-normal`
3. `memory-off`
4. `private-call`
5. `hard-stop`
6. `correction-overlap`
7. `question-overlap`
8. `sustained-overlap`
9. `backchannel`
10. `assistant-echo`
11. `background-noise`
12. `provider-reconnect`
13. `stt-failure`
14. `tts-failure`
15. `browser-reload`
16. `rapid-interruption-soak`

Set the active scenario in the browser console before a run:

```js
localStorage.setItem('omnix.liveCall.releaseScenario', 'system-normal')
```

The observer writes only metric names, durations, scenario labels, correlation IDs, and transcript lengths under the existing diagnostics privacy policy. It does not add transcript text to release evidence.

## Labelling quality trials

After each intentional quality trial, dispatch one content-free label in the browser console:

```js
window.dispatchEvent(new CustomEvent('omnix:assistant-voice-release-quality', {
  detail: {
    qualityName: 'false_interruption',
    occurred: false,
    scenario: 'background-noise',
  },
}))
```

Use the same event with `missed_interruption` or `backchannel_false_positive`. `occurred: true` means the defect happened in that trial.

## Evaluation

Gateway endpoint:

```text
GET /api/tts/live-call/diagnostics/release-gate?hours=24
```

Deterministic payload evaluator for tests or imported evidence:

```text
POST /api/tts/live-call/diagnostics/release-gate/evaluate
```

Local CLI:

```bash
python -m app.gateway.live_voice_release_gate_cli --hours 24
```

Exit codes:

- `0`: all thresholds and scenario requirements pass
- `1`: one or more thresholds fail
- `2`: evidence is incomplete

## Execution procedure

1. Start the normal Omnix gateway, STT service, provider, and TTS service.
2. Use the target Windows machine, Chrome build, microphone, speakers, GPU, and local models.
3. Clear or archive the prior `live-call-streaming.log` when starting a clean evidence window.
4. Run every required scenario with the appropriate scenario label.
5. Collect at least five valid observations for every latency boundary.
6. Label at least ten trials for each quality metric.
7. Run the CLI and preserve its JSON output with the release evidence.
8. Do not enable a production rollout unless the result is `pass`.

## Failure injection expectations

- Provider reconnect: terminate or restart the active local provider connection and verify recovery or bounded failure.
- STT failure: stop the STT service during capture and verify the call remains recoverable.
- TTS failure: stop the TTS service after provider text begins and verify text completion remains usable.
- Browser reload: reload during partial audio and verify stale completion cannot publish.
- Rapid-interruption soak: repeatedly interrupt long responses and verify only one authoritative assistant turn remains active.

## Rollback

This milestone adds observation and evaluation only. Diagnostics remain nonblocking and failures are swallowed by the existing reporter. Rollback consists of reverting the observer import and release-gate routes; chat, STT, provider generation, and TTS do not depend on the evaluator.

The release gate does not enable Character Mode, memory, Hermes, or Live Agent features by itself.
