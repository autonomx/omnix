# Production ingress and route ownership

Production serves the built web application and proxies gateway traffic through [the supported Nginx example](../../deploy/nginx/omnix.conf). Vite's `gateway-routing.ts` is a local development proxy. The browser uses relative paths and does not select production process roles.

The authoritative allowlist is [gateway-route-policy.json](../../deploy/gateway-route-policy.json). Both Vite and `scripts/render_gateway_ingress.py` consume it. Edit the policy, regenerate the example, and run the Python/web routing gates together.

| Route class | Target |
| --- | --- |
| Chat session create/read/update/delete, attachments, and non-streaming messages | API pool; PostgreSQL protects admission and transcript ownership |
| Message stream and `/api/tts/live-call/websocket` | Worker unless shared remote TTS and a call-affinity key are present; then consistent hash to the same API replica |
| GET/HEAD job list/detail, `/events`, trading bars/quotes | API pool |
| Speech WebSocket/SSE | Worker by default; API pool only when every API uses the shared remote TTS endpoint |
| All unclassified API routes and writes, trading control, RPG control | Worker/control process |
| `/health`, `/ready` | Worker through the public ingress; probe each private API origin separately |
| Static paths | Built web app with SPA fallback |

`X-Omnix-Gateway-Affinity: worker` is a worker-routing override for the Vite development proxy only: the policy's `external_worker_affinity` is `false`, so the ingress ignores the header and strips it before proxying (set it to `true` only for an ingress that serves authenticated operators). Live-call chat requests carry `X-Omnix-Call-Id`; the persistent browser WebSocket carries the same key in the `omnix_call_affinity` cookie. When remote TTS is enabled and the key is present, Nginx and the Vite development proxy consistently hash it so the chat stream and WebSocket reach the same API replica. Live traffic without the key stays on the worker. Other API requests use least connections. Selection happens once per request/upgrade; Nginx holds that upstream for the entire WebSocket/SSE connection. `proxy_next_upstream off` disables replay, including after a transport failure. Clients may explicitly retry only with the endpoint's durable idempotency contract.

Install `deploy/nginx/omnix.conf` within Nginx's `http` context, replace loopback upstreams, the certificate paths (`/etc/nginx/tls/omnix.crt` and `.key`) and `/srv/omnix/web`, and run `nginx -t` before reloading. Build the web app with `npm --prefix web run build`. The example serves HTTPS on 443 (TLS 1.2 and 1.3) and redirects port 80. Gateway listeners should be private to that ingress. The container image (`omnix-web`, WP-11.1) carries the same routes for the Compose network: `deploy/docker/nginx/omnix.conf` on 8080, or `omnix-tls.conf` (HTTPS on 8443, redirect from 8080) mounted over it with the certificate files.

All variants are rendered from the policy by `scripts/render_gateway_ingress.py` and add:

- the SPA's security headers on static responses: a Content-Security-Policy that allows only same-origin scripts (no `eval`; Pixi runs through `pixi.js/unsafe-eval`'s precompiled path), same-origin connections and `blob:` media, no framing, plus `nosniff`, `no-referrer`, `X-Frame-Options: DENY`, the gateway's Permissions-Policy, and HSTS on HTTPS listeners. Gateway responses keep the gateway's own headers;
- caching: content-hashed `/assets/` for a year (`immutable`), `index.html` revalidated on every load;
- per-client rate limits (`limit_req`, 429): `/api/auth/` at 10 requests a minute (burst 10) and the rest of the API at 50 a second (burst 400). Behind another proxy, configure `real_ip` so the limit applies to the client rather than the proxy;
- body limits (`body_limits`): 64 MB by default, 1 MB for sign-in, 200 MB for audiobook sources and 512 MB for RPG world bundles, at least the gateway's own limits (a test keeps them aligned);
- `server_tokens off`.

`scripts/check_web_image.py <image>` runs a built web image and checks `nginx -t`, the headers, caching, the sign-in body limit and rate limit (`--browser` also loads the app in Chromium and fails on any CSP violation); the images workflow runs it.

OIDC deployments can use the gateway's own sign-in (`OMNIX_AUTH_MODE=oidc`) or put [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/) in front of this ingress. oauth2-proxy then admits only signed-in users to the whole site. The gateway does not read oauth2-proxy's identity headers, so per-user permissions still need in-app OIDC sign-in; with the same identity provider, that second sign-in completes without another prompt.

The example defaults to two API origins at 8001/8002 and worker 8000. Set the speech map's default to `1` only after configuring `OMNIX_TTS_URL` on every API process and verifying required-worker readiness. This enables live-call WebSocket and live chat call-ID routing to the affinity-hashed API pool. With no API replicas, route the API upstream to the worker. `OMNIX_GATEWAY_API_ORIGINS` is the runtime diagnostics/developer topology input; it does not dynamically rewrite Nginx configuration.

Open-source Nginx's example uses passive upstream health. Deployment supervision must probe private `/ready` endpoints before admitting/replacing replicas; `/health` alone does not establish PostgreSQL or execution authority. A worker losing ownership remains unready and must restart with a fresh identity. Healthy APIs retain request-serving responsibility subject to their own database/owner readiness. No alternate persistence authority is selected during outages.
