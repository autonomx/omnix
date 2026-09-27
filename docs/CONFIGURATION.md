# Omnix configuration

This file is generated from `app.config.registry`. Values are intentionally never emitted.

| Variable | Type | Default | Owner | Description |
| --- | --- | --- | --- | --- |
| `OMNIX_BIND_HOST` | host | `127.0.0.1` | kernel | Gateway bind host. |
| `OMNIX_GATEWAY_PORT` | integer | `8001` | kernel | Gateway port. |
| `OMNIX_DATABASE_URL` | url | — | kernel | Runtime PostgreSQL role URL. |
| `OMNIX_MIGRATION_DATABASE_URL` | url | — | kernel | DDL/migration PostgreSQL role URL. |
| `OMNIX_REQUIRE_ROLE_SEPARATION` | boolean | `false` | kernel | Require distinct runtime and migration roles. |
| `OMNIX_ENV` | string | `development` | kernel | Deployment environment. |
| `OMNIX_SOFTWARE_REVISION` | string | `unversioned` | kernel | Build/software revision. |
| `OMNIX_FEATURES` | list | `all` | kernel | Enabled optional feature ids. |
| `OMNIX_FEATURES_DISABLED` | list | — | kernel | Disabled optional feature ids. |
| `OMNIX_GATEWAY_BACKGROUND_ROLE` | enum | `worker` | kernel | Gateway process role. |
| `OMNIX_GATEWAY_REQUIRED_WORKERS` | list | — | kernel | Required worker ids. |
| `OMNIX_TTS_URL` | url | — | voice | TTS worker endpoint. |
| `OMNIX_STT_URL` | url | — | voice | STT worker endpoint. |
| `OMNIX_IMAGE_URL` | url | — | image | Image worker endpoint. |
