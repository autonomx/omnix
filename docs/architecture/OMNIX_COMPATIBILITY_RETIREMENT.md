# Compatibility retirement

[compatibility-inventory.json](compatibility-inventory.json) records every `src/app/**/*_compat.py`: purpose, direct production imports, importing tests, disposition and deletion prerequisite. Run `python scripts/inventory_compatibility.py` after reviewing a dependency change. Import inventory is static evidence; domain integration tests cover indirect factory consumers too. The architecture allowlist gate rejects an unreviewed new compatibility filename.

| Category | Disposition |
| --- | --- |
| A — stable adapter | PostgreSQL implementations translating existing domain contracts; inline job admission normalization; supported Flux/Diffusers stack adaptation. Keep behavior, migrate names/imports coherently when useful. |
| B — migration shim | RPG gateway payload facades and document/configuration/image/RPG adapters. Migrate consumers to typed domain services while preserving payload normalization, secret boundaries and atomicity, then delete wrappers. |
| C — dead code | Delete only after import/caller/test verification. No module in the reviewed inventory is currently classified C: all have production consumers. |

`app.shared` and the `app.persistence.runtime_install` callback installer have been removed. Settings use the typed settings service with revision checks; provider secrets use the secret store. Application code has no `SETTINGS_FILE`, `SESSIONS_FILE`, or `SECRETS_FILE` fallback. `app.runtime_document_services` remains a frozen composition of document operations still used by RPG, image, assistant-tool, and house-state adapters; it does not register callbacks or provide settings/session fallbacks.

Production defaults for chat, jobs, assets, characters/avatar, memory, provider refresh, evaluation, research and narrative use explicit `runtime_composition` factories. Remaining compatibility modules and their production/test callers are listed in the generated inventory. Legacy implementations keep their identities for explicitly selected test/import processes; their presence does not confer production authority.

Retire remaining shims by moving each listed production caller to its owning typed service or repository, then remove the adapter only after import, serialization/normalization, transaction and tenant regressions pass. Do not delete a working stable adapter merely because its historical filename contains `compat`.
