# API transport exceptions

The OpenAPI contract covers browser-facing JSON HTTP routes. The following transports are intentionally outside ordinary request/response schema generation:

- WebSocket endpoints used for live voice, realtime chat, streaming STT/TTS, and audiobook streaming.
- Server-Sent Events endpoints whose payload is an event stream rather than a single JSON response.
- Internal service-token orchestration routes mounted through `FeatureModule.internal_routers`.

A route must not use `include_in_schema=False` merely because it is experimental. Browser-facing JSON routes require typed request and response models.
