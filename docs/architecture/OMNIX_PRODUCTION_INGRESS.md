# Production ingress and route ownership

Production serves the built web application and proxies gateway traffic through [the supported Nginx example](../../deploy/nginx/omnix.conf). Vite's `gateway-routing.ts` is a local development proxy. The browser uses relative paths and does not select production process roles.

The authoritative allowlist is [gateway-route-policy.json](../../deploy/gateway-route-policy.json). Both Vite and `scripts/render_gateway_ingress.py` consume it. Edit the policy, regenerate the example, and run the Python/web routing gates together.

| Route class | Target |
| --- | --- |
| Chat session create/read/update/delete, attachments, messages and message stream | API pool; PostgreSQL protects admission and transcript ownership |
| GET/HEAD job list/detail, `/events`, trading bars/quotes | API pool |
| Speech WebSocket/SSE | Worker by default; API pool only when every API uses the shared remote TTS endpoint |
| All unclassified API routes and writes, trading control, RPG control | Worker/control process |
| `/health`, `/ready` | Worker through the public ingress; probe each private API origin separately |
| Static paths | Built web app with SPA fallback |

`X-Omnix-Gateway-Affinity: worker` forces worker routing for existing clients. Otherwise API selection uses least connections. Selection happens once per request/upgrade; Nginx holds that upstream for the entire WebSocket/SSE connection. `proxy_next_upstream off` disables replay, including after a transport failure. Clients may explicitly retry only with the endpoint's durable idempotency contract.

Install `deploy/nginx/omnix.conf` within Nginx's `http` context, replace loopback upstreams and `/srv/omnix/web`, and run `nginx -t` before reloading. Build the web app with `npm --prefix src/apps/web run build`. This example listens on 8080; terminate HTTPS using the deployment's normal ingress configuration. Gateway listeners should be private to that ingress.

The example defaults to two API origins at 8001/8002 and worker 8000. Set the speech map's default to `1` only after configuring `OMNIX_TTS_URL` on every API process and verifying required-worker readiness. With no API replicas, route the API upstream to the worker. `OMNIX_GATEWAY_API_ORIGINS` is the runtime diagnostics/developer topology input; it does not dynamically rewrite Nginx configuration.

Open-source Nginx's example uses passive upstream health. Deployment supervision must probe private `/ready` endpoints before admitting/replacing replicas; `/health` alone does not establish PostgreSQL or execution authority. A worker losing ownership remains unready and must restart with a fresh identity. Healthy APIs retain request-serving responsibility subject to their own database/owner readiness. No alternate persistence authority is selected during outages.
