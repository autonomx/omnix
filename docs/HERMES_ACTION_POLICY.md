# Hermes Action Policy

Phase 19 defines the policy boundary before any future change path is wired.

Levels:

- read_only: can return existing status or diagnostics data.
- review_required: must show target, before value, after value, and risk before a later route can proceed.
- dangerous: reserved for high-risk items and not enabled.
- blocked: default for unknown names.

Current allowlist:

- get_house_status: read_only
- get_hermes_status: read_only
- get_hermes_diagnostics_schema: read_only

Rules:

1. Unknown names are blocked.
2. Browser controls must not run shell commands.
3. File, GitHub, OS, and model-setting changes remain out of scope.
4. Future change paths must remain behind the review surface.
5. The normal Chat path remains unchanged unless Agent Chat is explicitly enabled.
