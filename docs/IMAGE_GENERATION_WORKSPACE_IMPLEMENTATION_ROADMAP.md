# Image Generation Workspace implementation roadmap

## Goal

Deliver a production-ready local-first image generation workspace where a submitted request becomes a durable shared job, runs through the configured image provider, persists a shared image asset, appears immediately in **Latest Result**, and remains available in **Image Assets** after reload.

## Canonical flow

```text
Image request form
  -> POST /api/jobs (image.generate)
  -> durable SQLite job
  -> background image executor
  -> app.image.service.generate_image
  -> shared AssetRecord
  -> completed job output_refs.asset_id
  -> job event stream
  -> Latest Result + Image Assets
```

The browser must use `asset_id` for previews and downloads. It must never depend on a local filesystem path.

## Phases

| Phase | Scope | Status |
| --- | --- | --- |
| IGW-0 | Canonical image request/output contracts and provider normalization | Complete - PR #1219 |
| IGW-1 | Shared background `image.generate` executor | Complete - PR #1220 |
| IGW-2 | Authoritative shared image asset persistence | Complete - PR #1221 |
| IGW-3 | Browser-safe binary image asset endpoint | Complete - PR #1222 |
| IGW-4 | Filtered and bounded jobs/assets APIs | Complete - PR #1223 |
| IGW-5 | Live job synchronization with SSE and bounded polling fallback | Complete - PR #1224 |
| IGW-6 | Latest Result selection and preview surface | Complete - PR #1225 |
| IGW-7 | Image Jobs progress, failure, cancel, retry, and result actions | Complete - PR #1226 |
| IGW-8 | Image Assets thumbnail grid, search, filters, and selection | Complete - PR #1227 |
| IGW-9 | Request redesign, presets, style, and advanced controls | Complete - PR #1228 |
| IGW-10 | Runtime/provider readiness and actionable disabled states | Complete - PR #1229 |
| IGW-11 | Legacy queue/manifest consolidation and compatibility migration | Complete - PR #1231 |
| IGW-12 | End-to-end verification, accessibility, and release cleanup | Complete - PR #1233 |

## Status

The Image Generation Workspace roadmap is complete. New work should be handled as focused maintenance or provider-specific follow-up rather than extending this roadmap.

## IGW-12 completion evidence

- Verified implementation head: `cced009d7bdbc0272fc70a80e60d9a4f6a37fc5d`
- Squash merge SHA: `efac3ecfa9048d187c0f1d0f785b177b67acd1bf`
- Both required pull-request workflows passed on the exact implementation head.
- The release smoke verifies queued shared submission, background execution, completed job events, shared asset persistence, asset-ID preview and download delivery, and persistence after stores are reopened.
- Latest Result uses a polite live region and descriptive open/download labels.
- Image Assets announces filtered result counts and avoids duplicate thumbnail names for assistive technology.

## Verification boundary

CI uses a deterministic image-provider response and does not load a GPU image model. A deployment using FLUX or another local provider must still run the same smoke flow against that configured runtime before release, but no browser, job, persistence, or asset-contract changes are expected for that check.

## IGW-0 contract

### Input payload

- `prompt`: required non-empty text
- `negative_prompt`: optional text
- `provider_id`: facade-facing provider identifier such as `image:flux_klein`
- `width`, `height`: 128-4096, multiples of 64
- `style`: optional presentation hint
- `seed`: optional non-negative integer
- `steps`: optional positive integer
- `guidance_scale`: optional non-negative number
- `unload_after_generation`: explicit per-job override
- `no_cache`: explicit cache bypass

### Output reference

A completed image job emits a small metadata-only output reference containing:

- `type = image`
- `asset_id`
- `title`
- `mime_type`
- `width`, `height`
- `provider_id`
- optional `seed`

Image bytes and data URLs are forbidden in shared job list projections.

## Release acceptance

The verified smoke flow covers:

1. Submit an image prompt.
2. Receive a queued shared job without blocking on generation.
3. Observe running and completed states through job events.
4. Persist a shared image asset linked to the source job.
5. Load the image through an asset-ID file endpoint.
6. Expose the result to Latest Result through the bounded asset projection.
7. Expose the result to Image Assets through the bounded asset projection.
8. Reopen the durable job and asset stores and preserve the result.
