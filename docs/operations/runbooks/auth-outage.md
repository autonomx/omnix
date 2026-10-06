# Sign-in outage (OIDC)

Applies when `OMNIX_AUTH_MODE` is `oidc` (or `local`). With sign-in off there
is nothing to sign in to.

## Symptoms

- `OmnixAuthUnavailable`: the gateway cannot reach its session store or
  identity provider (`authentication_unavailable`, HTTP 503).
- `OmnixAuthRejectionSpike`: many refused sign-ins.
- Users are sent to `/login` repeatedly.

## Dashboards and metrics

- Omnix overview: *Refused requests* by reason.
- `omnix_auth_rejections_total{reason}`: `authentication_unavailable`,
  `authentication_required`, `invalid_credential`, `csrf_failed`,
  `permission_denied`; `omnix_rate_limit_rejections_total{limit="login"}`.

## Diagnosis

1. `authentication_unavailable`: PostgreSQL (sessions) or the issuer is
   unreachable. Check `python -m app.persistence health`, then the issuer's
   discovery document at `OMNIX_OIDC_ISSUER/.well-known/openid-configuration`.
2. `authentication_required` spike after a deploy: sessions were dropped or
   `OMNIX_AUTH_COOKIE_SECURE` does not match the scheme the browser uses.
3. `csrf_failed`: a client is not echoing `omnix_csrf` in `X-Omnix-CSRF`.
4. Failed sign-ins and rotations are in `omnix_audit_events`.

## Remediation

- Restore the database or the identity provider. Do not switch
  `OMNIX_AUTH_MODE` to `disabled` on a networked install: startup refuses it
  outside development or tests.
- Local mode, lost credential: `python -m app.security rotate-install-credential`
  (signs everyone out) ([OPERATIONS: Sign-in and sessions](../../OPERATIONS.md#sign-in-and-sessions)).
- Rate limiting legitimate users: wait for the bucket to refill (it refills
  over a minute) rather than raising the limit during an attack.

## Verification

- A sign-in completes; `authentication_unavailable` stops increasing.
