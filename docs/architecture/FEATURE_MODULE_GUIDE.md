# FeatureModule guide

Phase 2 makes `FeatureModule` the composition contract for optional Omnix capabilities. The catalog at `app.runtime.feature_catalog.FEATURE_CATALOG` is the only feature list.

A feature package exposes `feature.py` with one `FEATURE` value. Prefer `APIRouter` factories in `routers`; use `internal_routers` only for service-token or otherwise internal HTTP surfaces. Background ownership is declared with `background_workers`; durable job execution is declared with `job_handlers`; feature persistence is declared through repository specs.

Feature factories receive a `FeatureContext` containing immutable runtime configuration, capabilities, kernel services, and a feature logger. Do not import the gateway composition root from a feature. Do not patch `FastAPI.__init__`, job-store classes, or other package classes at import time.

Feature enablement is controlled by `OMNIX_FEATURES` and `OMNIX_FEATURES_DISABLED`. Startup fails if an enabled feature depends on a disabled feature. Disabling a feature must remove its HTTP routes and job handlers while keeping kernel health/readiness routes available.

The audiobook feature is the reference implementation: its HTTP router, websocket router, and background worker are owned by `app.audiobook.feature`. New migrations should preserve existing public URLs and add typed request/response models rather than changing endpoint paths.
