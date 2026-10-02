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
- `scripts/backup_omnix.py` and `scripts/restore_rehearsal.py`, with a nightly
  restore rehearsal.

### Changed

- Gateway errors no longer return provider, driver or database error text;
  the cause is logged under the request id.
- Errors that used to be swallowed silently are logged at debug level.
- Structured outputs from model calls go through one gateway with contracts,
  retries and deadlines.

### Removed

- The standalone OpenAI-compatible server (`src/openai_api.py`).
- Unreachable RPG and assist-core modules, and the legacy UI.

### Security

- Model-service calls require the service credential; outbound URLs are
  checked against SSRF rules; secrets live in the protected secret store.
