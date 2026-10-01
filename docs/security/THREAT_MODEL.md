# Omnix threat model

Status: 2026-10-01, WP-4.11. Method: STRIDE per component. Each threat
lists the mitigation in place (with its work package) and what remains.
Update this file when a component, trust boundary or mitigation changes.

## Scope and assets

Omnix runs as a local single-user install (sign-in off, the default today)
or as a multi-user deployment (sign-in on, several workspaces, separate
database roles, possibly several hosts).

Assets, most sensitive first:

1. Provider and tool credentials: model API keys, OAuth tokens, trading
   keys.
2. Workspace data: chats, memory, characters, documents, agent runs and
   artifacts, trading state.
3. Authority: approvals, capability execution, trading controls, agent
   workspace mutation.
4. Availability of the gateway, workers and model services.
5. Integrity of the audit trail.

## Trust boundaries

| Boundary | From → to | Authentication |
|---|---|---|
| B1 | Browser → ingress/gateway | session cookie + CSRF, or OIDC bearer (when sign-in is on); Origin/Host checks |
| B2 | Gateway ↔ internal services (workers, sidecars) | service token on internal routes |
| B3 | Agent process (Pi) → broker and model gateway | run token (`OmnixRun`) |
| B4 | Omnix → PostgreSQL | database role; row-level security per workspace |
| B5 | Omnix → blob store | S3 credentials or local filesystem |
| B6 | Omnix → model services, tool APIs, trading providers | provider credentials; outbound URL policy |
| B7 | Agent sandbox → host and network | process or container isolation (WP-4.7 pending) |

## Components

### Browser (web app)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | A forged request from another site uses the session | `SameSite=Strict` cookie, CSRF header on unsafe methods, Origin check (WP-4.1, request guard) | — |
| T | Injected script tampers with the UI | React escaping; the gateway sends CSP and `nosniff` (WP-4.10); the ingress CSP for the app is WP-11.3 | App CSP pending WP-11.3 |
| I | Clickjacking reads or drives the UI | `X-Frame-Options: DENY`, `frame-ancestors 'none'` (WP-4.10) | — |
| E | A viewer reaches admin actions in the UI | Server-side permission checks on every route (WP-4.3); the UI hides nothing the server allows | — |

### Ingress (Nginx)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | A spoofed `X-Forwarded-For`/`Host` | Allowed hosts; forwarding headers trusted only from the ingress | — |
| D | Request floods | Per-process rate limits on sign-in and approvals (WP-4.10); global ingress limits | Ingress limits are WP-11.3 |

### Gateway API

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | Unauthenticated access when sign-in is on | Deny-by-default authentication middleware; auto-enumerated test over every route (WP-4.1) | Sign-in stays off by default by owner decision |
| S | Session theft or replay | Random 256-bit tokens hashed at rest, sliding and absolute expiry, revocation on logout (WP-4.1) | — |
| T | Cross-workspace writes | Request tenant bound per request (WP-4.2); repositories filter by workspace; RLS (WP-4.4) | — |
| R | Denying a sensitive action | Append-only audit trail for approvals, executions, settings, trading control, administration, sign-in (WP-4.8) | Retention path WP-5.2 |
| I | Reading another workspace's data | Permission guard (WP-4.3), tenant binding (WP-4.2), RLS (WP-4.4); the test isolates two users at the API | — |
| I | Error and path disclosure | Content-free audit details; secrets kept out of logs (canary test) | `storage_path` still in asset responses; error envelope WP-10.5 |
| D | Login brute force | 5 attempts per minute per address (WP-4.10) | — |
| E | A member approves their own risky action | `tools:approve`/`agent:approve` required; service, system and agent principals never approve; self-approval capped by risk (WP-4.5) | Default cap is `high` while sign-in is off |
| E | API docs reveal the attack surface | `/docs`, `/redoc`, `/openapi.json` need `admin:docs` outside development (WP-4.10) | — |

### Agent runtime (broker, model gateway, Pi)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | Another local process calls the broker as an agent | Run tokens (HMAC, run-bound, 15-minute TTL, owner and capability bound) on every agent route (WP-4.6) | — |
| T | An agent edits files outside its workspace | Issued path roots, guard extension, workspace authorization (existing); sandbox by default is WP-4.7 | WP-4.7 pending (owner decision on defaults) |
| R | An agent action without a record | Capability executions and approvals audited (WP-4.8) | — |
| I | A shell tool reads the run token | Token removed from `process.env` before tools run; never in argv; never forwarded to children (WP-4.6) | — |
| D | Unbounded tool use | Server-side tool budget per capability execution (WP-4.5) and step/wall-time limits | Global concurrency limit is WP-4.7 |
| E | An agent approves its own request | Agent principals carry `agent_run` (no approve) (WP-4.6); approvals bound to principals (WP-4.5) | — |
| E | Prompt injection widens authority | Profiles are ceilings; capabilities issued per run; executor fails closed on unknown adapters (WP-4.5) | Model behaviour itself remains untrusted by design |

### Workers, scheduler, job workers

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | A rogue process claims jobs | Database roles; lease tokens fence stale workers (WP-6.1) | — |
| T | A job runs in the wrong workspace | Workers push the job's workspace tenant; RLS (WP-4.2, WP-4.4) | — |
| D | Duplicate or stuck work | Exactly-once claims, lease expiry and reclaim, drain on shutdown (WP-6.1, WP-6.7) | — |

### Model services and outbound providers

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | A configured endpoint redirects to an internal service (SSRF) | Outbound URL policy at save and connect time: link-local and metadata always blocked, private networks controlled (WP-4.10) | Short DNS TOCTOU window; private networks open while sign-in is off |
| T | Starting a model server kills an unrelated process | llama.cpp stops only its own server and refuses a busy port (WP-4.10) | — |
| I | API keys leak | DPAPI provider store, environment authoritative, never in PostgreSQL (existing) | — |

### PostgreSQL

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| T | Application bug writes another workspace | Forced RLS on all 178 tenant tables, runtime role without `BYPASSRLS` (WP-4.4) | Superuser installs bypass RLS (documented) |
| R | Audit rows are rewritten | Append-only trigger; runtime role loses UPDATE/DELETE (WP-4.8) | — |
| I | A query forgets its workspace filter | RLS; CI runs the suite as the restricted role (WP-4.4) | — |
| D | Lock contention or runaway queries | Statement and lock timeouts per connection (existing) | — |

### Blob store

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| T | Blob content replaced | SHA-256 checksums verified on read (WP-5.8) | — |
| I | Direct blob access | Every request is SigV4-signed; downloads use presigned URLs that expire (WP-5.8) | Bucket privacy is operator configuration |

### Secrets

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| I | Plaintext credentials on disk | Secret store (DPAPI, keychain, read-only env); no plaintext backend (WP-4.9) | — |
| I | Secrets in logs | Log canary test; audit details drop secret keys (WP-4.8, WP-4.11) | — |

### Hermes sidecar and assistant-tool integrations

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | A forged sidecar request | Service token on internal routes (B2) | — |
| E | A tool runs without consent | Single fail-closed executor, approval policy, principal-bound approvals, rate-limited approve/execute (WP-4.5, WP-4.10) | — |

### Trading providers

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| E | Research or an agent places orders | Trading writes require `trading:control`; paper orders only `trading:paper:order`; AI analysis is research-only (WP-4.3, repository policy) | — |
| R | Disputed control changes | Trading control and paper orders audited (WP-4.8) | — |

### Agent sandbox

Pending WP-4.7: Docker isolation by default for mutating profiles, broker-only
egress, global run limits. Today the agent runs supervised in a worktree, with
path roots enforced by the guard extension and the broker.

## Open items

- WP-4.7: sandbox by default, egress control, global concurrency. It
  changes defaults for existing local installs and waits for the owner.
- WP-4.1: sign-in on by default (owner decision: later).
- WP-4.10: remove `storage_path` from asset responses; error envelope
  (WP-10.5).
- WP-11.3: ingress CSP for the web app and global rate limits.
- ASVS L2 checklist (`docs/security/ASVS_L2_CHECKLIST.md`): to be written once
  WP-4.7 is settled.
