# Live Speech Realtime Usage

The HF-parity realtime live-speech router is available through a reviewable gateway entrypoint while the existing gateway remains unchanged:

```bash
PYTHONPATH=src python -m uvicorn app.gateway.live_speech_main:app --host 127.0.0.1 --port 8000
```

Routes exposed by this entrypoint:

- `GET /api/live-speech/protocol` — protocol and compatibility metadata.
- `WS /v1/realtime` — realtime speech session socket.

The route currently uses deterministic offline STT/TTS adapters by default. Production adapters can replace them behind the same contracts:

- `StreamingTranscriber`
- `StreamingSpeechSynthesizer`
- `EnergyVad`
- `CancelScope`

This entrypoint is intentionally separate from `app.gateway.main:app` so CI and review can validate the new route before it becomes part of the default shared gateway.
