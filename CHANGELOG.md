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
- Web: long chat sessions open in seconds and render only the visible
  messages; the Jobs and Assets views load more on request; the image gallery
  shows 60 images at a time; Pixi and Live2D load only when an avatar is shown.
- Web: form fields, controls and labels are named for screen readers, and
  primary buttons are darker to meet contrast requirements.
- Web: gateway calls use a client generated from the OpenAPI contract, and
  chat, job, trading and voice stream messages are checked when they arrive;
  a malformed message is dropped or reported instead of breaking the view.

### Fixed

- Settings Control Center changes save again.
- Replaying an assistant response during a live voice call plays it instead of
  failing.
- Settings shows the Hermes sidecar as Ready when it is reachable.

### Removed

- The standalone OpenAI-compatible server (`src/openai_api.py`).
- Unreachable RPG and assist-core modules, and the legacy UI.

### Security

- Model-service calls require the service credential; outbound URLs are
  checked against SSRF rules; secrets live in the protected secret store.
