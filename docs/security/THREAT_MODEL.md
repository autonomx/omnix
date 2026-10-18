# Omnix threat model

Status: 2026-10-03, WP-4.11. Method: STRIDE per component. Each threat
lists the mitigation in place (with its work package) and what remains.
Update this file when a component, trust boundary or mitigation changes.

## Scope and assets

Omnix runs as a local install (sign-in on by default since 2026-10-06; the
owner is signed in from the launcher) or as a multi-user deployment (several workspaces, separate
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
| B7 | Agent sandbox → host and network | Docker sandbox for every run that can change its workspace; internal network reaching only the broker relay (WP-4.7) |

## Components

### Browser (web app)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | A forged request from another site uses the session | `SameSite=Strict` cookie, CSRF header on unsafe methods, Origin check (WP-4.1, request guard) | — |
| T | Injected script tampers with the UI | React escaping; the gateway sends CSP and `nosniff` (WP-4.10); the ingress serves the app with `script-src 'self'` (WP-11.3) | The Vite development server sends no CSP |
| I | Clickjacking reads or drives the UI | `X-Frame-Options: DENY`, `frame-ancestors 'none'` (WP-4.10) | — |
| E | A viewer reaches admin actions in the UI | Server-side permission checks on every route (WP-4.3); the UI hides nothing the server allows | — |

### Ingress (Nginx)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | A spoofed `X-Forwarded-For`/`Host` | Allowed hosts; forwarding headers trusted only from the ingress | — |
| D | Request floods | Per-process rate limits on sign-in and approvals (WP-4.10); ingress request rates and body sizes (WP-11.3) | — |

### Gateway API

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | Unauthenticated access | Sign-in on by default; deny-by-default authentication middleware; auto-enumerated test over every route (WP-4.1) | `OMNIX_AUTH_MODE=disabled` is refused outside test or loopback development |
| S | Account takeover through sign-up or Google | Accounts never merged by email (sign-up does not verify email); Google identities link only from the signed-in account; passwords scrypt-hashed, at least 12 characters; unknown email and wrong password answer alike after a full scrypt run; sign-in, sign-up and guest creation rate-limited; invites single-use and expiring (WP-4.1) | An address can be registered by someone who does not own it; its owner then uses Google from a different account or asks an admin |
| E | A guest or new account reaches more than its own workspace | Each new account gets its own workspace; guests hold the restricted `guest` role (no tools, agents, research runs, orders or voice cloning); private-network provider URLs need `OMNIX_ALLOWED_PRIVATE_NETWORKS` once sign-in is on | Guest workspaces are kept after the guest's session ends |
| S | Session theft or replay | Random 256-bit tokens hashed at rest, sliding and absolute expiry, revocation on logout; over HTTPS a `Secure` `__Host-` cookie; users list their sessions and sign out the others after re-authenticating; sign-out clears browser storage (WP-4.1, WP-4.11) | — |
| T | Cross-workspace writes | Request tenant bound per request (WP-4.2); repositories filter by workspace; RLS (WP-4.4) | — |
| R | Denying a sensitive action | Append-only audit trail for approvals, executions, settings, trading control, administration, sign-in (WP-4.8) | Retention path WP-5.2 |
| I | Reading another workspace's data | Permission guard (WP-4.3), tenant binding (WP-4.2), RLS (WP-4.4); the test isolates two users at the API | — |
| I | Error and path disclosure | Errors answer problem+json with a request id and no internals (WP-10.5); asset APIs name files by id and URL, never by storage path (WP-4.10); content-free audit details; secrets kept out of logs (canary test) | Operator diagnostics (migration previews, model cache status) still show paths to administrators |
| D | Login brute force | 5 attempts per minute per address (WP-4.10) | — |
| E | A member approves their own risky action | `tools:approve`/`agent:approve` required; service, system and agent principals never approve; self-approval capped by risk (WP-4.5) | Default cap is `high` while sign-in is off |
| E | API docs reveal the attack surface | `/docs`, `/redoc`, `/openapi.json` need `admin:docs` outside development (WP-4.10) | — |

### Agent runtime (broker, model gateway, Pi)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | Another local process calls the broker as an agent | Run tokens (HMAC, run-bound, 15-minute TTL, owner and capability bound) on every agent route (WP-4.6) | — |
| T | An agent edits files outside its workspace | Issued path roots, guard extension, workspace authorization; mutating runs in a read-only container that mounts only the workspace; in-place folders must be allow-listed (WP-4.7) | An operator may allow unsandboxed runs (`OMNIX_AGENT_ALLOW_UNSANDBOXED`): audited, every command needs approval |
| R | An agent action without a record | Capability executions and approvals audited (WP-4.8) | — |
| I | A shell tool reads the run token | Token removed from `process.env` before tools run; never in argv; never forwarded to children (WP-4.6) | — |
| D | Unbounded tool use | Server-side tool budget per capability execution (WP-4.5), step/wall-time limits, container memory/CPU/pid limits and a global concurrent-run limit across processes (WP-4.7) | — |
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

See [AGENT_SANDBOX.md](AGENT_SANDBOX.md). Runs that can change their workspace
run in a read-only, capability-free container with resource limits and a
private home, on an internal network whose only reachable endpoint is the
broker relay; their workspace previews run there too. Safe validation commands
are approved automatically only inside it. Without Docker such a run fails
closed unless the operator allows unsandboxed runs (audited; every command
asks). At most `OMNIX_AGENT_MAX_CONCURRENT_RUNS` agents run at once.

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| I | An agent exfiltrates workspace data over the network | Internal Docker network; the relay forwards only the gateway's broker and model-gateway ports; the run token is accepted only for that run's routes (WP-4.6/4.7) | Data can still leave through governed capabilities the run was issued (e.g. a web search query) |
| E | Sandboxed agent code calls the rest of the gateway (approves its own run, loosens tool policy), which without sign-in would act as the local owner | The relay forwards HTTP only on the agent-runtime routes and refuses every other path and upgrade; the gateway refuses relayed requests outside those routes (`x-omnix-sandbox-relay`) | — |
| E | Agent-edited code runs on the host (dev server, test runner) | Commands and the workspace preview run inside the sandbox | On Windows hosts, host-installed native dependencies (node_modules, virtualenvs) do not run in the Linux sandbox; projects need a sandbox image with their toolchain or the unsandboxed override |
| T | An agent reads the person's home (SSH keys, tokens) | Home is a per-run directory (`/tmp/home` in the container) | — |

## Data classification

Each class of data Omnix holds and the rules that protect it. Personal data
stays in the workspace that created it.

| Class | Examples | Where | At rest | In transit | Access | Retention | In logs |
|---|---|---|---|---|---|---|---|
| Secrets | Provider and tool API keys, OAuth tokens, service token, run-token key, install credential | OS secret store (DPAPI, keychain) or environment; verifiers only as scrypt/SHA-256 | Encrypted by the OS store; never in PostgreSQL or files | TLS to providers; never in URLs | Owner and admin (settings); processes by role | Until rotated or disconnected ([runbook](../operations/runbooks/secret-rotation.md)) | Never (canary test) |
| Personal content | Chats, memory, characters, documents, voice samples and clones, generated audio and images, agent workspaces | PostgreSQL and the blob store | Not encrypted by Omnix: deployments use disk or volume encryption (ASVS V6.1.1 fail) | TLS at the ingress | Workspace members by permission; RLS per workspace | Until the user deletes it; job and event rows per the retention table (OPERATIONS: Retention) | Ids, not content; exceptions are the audiobook classification log and opt-in live-call transcripts (ASVS V7.1.2 fail) |
| Authority records | Audit events, approvals, capability executions, agent evidence | PostgreSQL, append-only | As personal content | As personal content | Admins read; nobody updates or deletes at runtime | 365 days (audit), evidence kept with its run | — |
| Account data | Users, memberships, sessions, OIDC identities | PostgreSQL | Session ids and codes as digests | TLS at the ingress | The user and admins | Expired sessions 7 days | Hashed user id |
| Operational | Metrics, traces, job metadata, logs | Prometheus, Jaeger, PostgreSQL, log files | Not encrypted | Internal network | Operators | Per the retention table; logs rotated | — |
| Trading | Market data, strategy state, paper orders | PostgreSQL | As personal content | TLS to providers | `trading:*` permissions | Strategy events 180 days when enabled | — |

## Open items

- WP-4.1: sign-in on by default (owner decision: later).
- The 20 ASVS Level 2 failures in [ASVS_L2_CHECKLIST.md](ASVS_L2_CHECKLIST.md#failures), each with its reason.
