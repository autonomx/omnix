# Omnix Assistant Workspace — Live Voice WebSocket Wiring

This slice reconnects the chat assistant Live Voice panel to the browser/WebSocket STT path used by the existing local voice stack.

## What changed

- Adds a typed `StreamingSttWebSocketClient` for `/ws/transcribe`.
- Streams browser microphone frames to the STT WebSocket as base64 PCM16 audio.
- Downsamples captured browser audio to 16 kHz before sending to the STT server.
- Updates the Live Voice panel status from real WebSocket state instead of static demo text.
- Writes partial and final transcripts into the Live Voice transcript panel.
- Pushes final transcripts into the chat composer and submits them as chat messages.
- Keeps the added Tool Execution sidebar next to the Live Voice panel.

## Runtime behavior

The default STT WebSocket endpoint is derived from the current page host:

- `http://host` -> `ws://host:8000/ws/transcribe`
- `https://host` -> `wss://host:8000/ws/transcribe`

The client sends messages in the same shape as the legacy local voice code:

```json
{ "type": "audio", "data": "<base64-pcm16>" }
```

When local voice activity settles, the client sends:

```json
{ "type": "final" }
```

The server may respond with:

- `ready`
- `text`
- `done`
- `error`

`text` updates the live transcript draft row. `done` commits the transcript, fills the chat composer, and queues the chat request.
