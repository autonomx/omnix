# Changelog

All notable changes to Omnix are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Omnix uses
[Semantic Versioning](https://semver.org/): the version in `pyproject.toml` is
the release version, and `src/apps/web/package.json` and the root
`package.json` carry the same number. Work-package detail is in
[docs/roadmap/PROGRESS.md](docs/roadmap/PROGRESS.md).

## [Unreleased]

The enterprise architecture refactor (`refactor-audit`), roadmap phases 0–10.

### Added

- PostgreSQL as the single authority for sessions, jobs, settings, agent runs
  and trading state, with forward migrations, row-level security per
  workspace, and a migration role separate from the runtime role.
- Durable job workers per resource class, PostgreSQL device permits for GPU
  work, a scheduler with background ownership, and an outbox for run events.
- Sign-in (`OMNIX_AUTH_MODE=local` or `oidc`), workspaces and roles,
  permission checks on gateway routes, CSRF protection, rate limits and security
  headers. Sign-in stays off unless configured.
- Multiple API replicas behind an ingress, rolling restarts with draining,
  and a multihost topology test.
- Structured logging with request and job ids that follow a request into its
  jobs and model-service calls; Prometheus metrics at `/metrics`; service
  objectives, alert rules and a Grafana dashboard (`deploy/observability/`);
  runbooks (`docs/operations/runbooks/`); one documented diagnostics schema.
- Problem-details error responses (`application/problem+json`) with a request
  id and a machine code.
- Optional OpenTelemetry tracing (`OMNIX_OTEL_ENABLED=true`, packages in
  `requirements/tracing.lock.txt`): request, httpx and psycopg spans plus job,
  RPG turn, live speech and agent step spans, with the trace id in log lines.
- `scripts/backup_omnix.py` and `scripts/restore_rehearsal.py`, with a nightly
  restore rehearsal.
- Memory v2 switch: curated memory can move from Memory v1 to Memory v2
  (`python -m app.assistant_memory_v2.shadow_runner`, then
  `python -m app.assistant_memory_v2.cutover activate`). After the switch,
  saving, approving, editing, pinning, archiving and forgetting memories work
  as before but live in v2; Chat puts pinned memories first and then the
  memories most relevant to the turn. Rollback is possible until the first
  memory change under v2.
- Web: a failing workspace shows an error panel with Try again (or Reload when
  a newer build replaced its code) instead of a blank app, and browser errors
  are reported to `POST /api/client-errors`.
- Web: an accessibility check (axe) runs on every workspace in the end-to-end
  tests.

### Changed

- Gateway errors no longer return provider, driver or database error text;
  the cause is logged under the request id.
- Errors that used to be swallowed silently are logged at debug level.
- Structured outputs from model calls go through one gateway with contracts,
  retries and deadlines.
- Web: styles use one colour palette (`design/tokens.css`, 259 colours instead
  of 6,685 literals) and cascade layers instead of `!important`; a few
  accent colours shift slightly.
- Web: long chat sessions open in seconds and render only the visible
  messages; the Jobs and Assets views load more on request; the image gallery
  shows 60 images at a time; Pixi and Live2D load only when an avatar is shown.
- Web: form fields, controls and labels are named for screen readers, and
  primary buttons are darker to meet contrast requirements.
- Web: Chat's live voice, Live Chat, session sidebar, composer tools, research
  progress and avatar are React components; Live Chat is a view in Chat's
  navigation. Storyteller tool panels update when the story changes instead
  of polling the page.
- Web: gateway calls use a client generated from the OpenAPI contract, and
  chat, job, trading and voice stream messages are checked when they arrive;
  a malformed message is dropped or reported instead of breaking the view.
- Web: Chat, Storyteller, Audiobook, the trading chart panel and the live
  voice controller are split into hooks and components, and functions over
  250 lines fail lint. Chat sends messages with research, agent mode, desktop
  sharing or a local folder through the context route by an explicit call.
- Web: the open chat session, audiobook project and trading instrument are in
  the address bar, so a view can be linked to and survives a reload.
- Web: polling pauses while the tab is hidden and never overlaps a slow
  request; Chat follows its reply job through server events when they are
  available.
- Web: an address that matches no workspace shows a not-found page instead of
  opening Chat.

### Fixed

- Settings Control Center changes save again.
- Replaying an assistant response during a live voice call plays it instead of
  failing.
- Settings shows the Hermes sidecar as Ready when it is reachable.
- The stream-audio button on chat replies streams the reply instead of
  reporting that no response is ready.
- Immersive Live Chat shows the chat's messages, and opens one dialog.
- A live voice error no longer replaces what you were saying in the
  transcript.
- Typing in Chat no longer re-renders the conversation, and the Live Chat
  message list and Storyteller library no longer rebuild on every render.
- Storyteller, Podcast, Voice Cloning and STT say what could not be loaded
  when the gateway fails, instead of showing empty lists; Settings shows a
  failed load on every category.

### Removed

- The standalone OpenAI-compatible server (`src/openai_api.py`).
- Unreachable RPG and assist-core modules, and the legacy UI.

### Security

- Model-service calls require the service credential; outbound URLs are
  checked against SSRF rules; secrets live in the protected secret store.
