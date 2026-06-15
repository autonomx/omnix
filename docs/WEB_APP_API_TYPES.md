# Omnix Web API Types

Last updated: 2026-06-14

Phase 6 wires the web app to generated API types from the thin FastAPI gateway.
Phase 13 begins enforcing drift checks now that the gateway has representative
platform APIs for jobs, providers, assets, prompts, replay, settings, reports,
and diagnostics.

## Generate Types

From the repository root:

```powershell
npm.cmd --workspace @omnix/web run api:generate
```

This command:

1. Exports the gateway OpenAPI schema from `app.gateway.main:app`.
2. Writes `apps/web/src/api/generated/openapi.json`.
3. Runs `openapi-typescript`.
4. Writes `apps/web/src/api/generated/types.ts`.

## Check Drift

From the repository root:

```powershell
npm.cmd --workspace @omnix/web run api:check
```

This command regenerates the schema and TypeScript types, then fails if
`apps/web/src/api/generated/openapi.json` or
`apps/web/src/api/generated/types.ts` differ from the checked-in versions.

## Import Convention

Feature code should import generated API shapes from:

```ts
import type { GatewayApiPaths } from '../api/client';
```

Use the correct relative path for the importing module. The raw generated file
remains under `apps/web/src/api/generated/types.ts`. Later phases can add
endpoint-specific helpers around these generated shapes, but new gateway
request/response interfaces should not be hand-maintained in feature modules.

## Zod Boundary

Zod remains for runtime trust boundaries only:

- form inputs;
- uploads and file metadata;
- URL/search params;
- local storage;
- SSE/event payloads;
- optimistic UI drafts before a backend response exists.

Generated OpenAPI types are the source for typed gateway HTTP request and
response shapes. The local drift check is now available as `api:check`; CI can
wire this command directly once the current generated files have been refreshed
after Phase 13 endpoint additions.
