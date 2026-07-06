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
| IGW-2 | Authoritative shared image asset persistence | In progress |
| IGW-3 | Browser-safe binary image asset endpoint | Planned |
| IGW-4 | Filtered and bounded jobs/assets APIs | Planned |
| IGW-5 | Live job synchronization with SSE and bounded polling fallback | Planned |
| IGW-6 | Latest Result selection and preview surface | Planned |
| IGW-7 | Image Jobs progress, failure, cancel, retry, and result actions | Planned |
| IGW-8 | Image Assets thumbnail grid, search, filters, and selection | Planned |
| IGW-9 | Request redesign, presets, style, and advanced controls | Planned |
| IGW-10 | Runtime/provider readiness and actionable disabled states | Planned |
| IGW-11 | Legacy queue/manifest consolidation and compatibility migration | Planned |
| IGW-12 | End-to-end verification, accessibility, and release cleanup | Planned |

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

The roadmap is complete only when this smoke flow passes:

1. Submit an image prompt.
2. Receive a queued shared job without blocking on generation.
3. Observe running and completed states without refreshing.
4. Persist a shared image asset linked to the source job.
5. Load the image through an asset-ID file endpoint.
6. Show it in Latest Result.
7. Show it in Image Assets.
8. Reload the workspace and preserve the result.
