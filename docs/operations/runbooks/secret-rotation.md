# Secret rotation

Rotate on a schedule, and at once after a suspected leak. Every rotation is
audited in `omnix_audit_events` where Omnix performs it.

## Install credential (local sign-in)

1. `python -m app.security rotate-install-credential` (interactive console).
2. Every local session ends; sign in again with the new credential
   (`python -m app.security show-install-credential`) or the launcher.

## Service token (`OMNIX_SERVICE_TOKEN`)

Shared by the gateway, workers and model services (TTS, STT, image); at least
32 random bytes, URL-safe.

1. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Set it on every process (or let the launcher provision protected storage).
3. Restart the model services and then every gateway and worker
   ([Rolling upgrade](rolling-upgrade.md)). Processes with different tokens
   refuse each other (401 `invalid_service_token`) until all are restarted.

## Run-token key (`OMNIX_RUN_TOKEN_KEY`)

Signs agent run tokens. It comes from the launcher's service token unless set.
Set the same new value (at least 32 characters) on every gateway and worker
and restart them together. Tokens signed with the old key stop working, so
rotate when no agent run is active, or restart the runs that were.

## Provider keys

LLM, search, market-data and integration keys live in the protected secret
store (`OMNIX_SECRET_STORE`) or the environment, never in PostgreSQL or files
([OPERATIONS: Secrets](../../OPERATIONS.md#secrets-and-networked-integrations)). Replace the
key at the provider, update it through the settings UI or the environment, and
check the provider's calls: `omnix_provider_calls_total{client=...}` stops
returning `4xx`.

## Verification

- Old credentials are refused; `omnix_auth_rejections_total` and
  provider `4xx` counts show no ongoing failures from processes you missed.
