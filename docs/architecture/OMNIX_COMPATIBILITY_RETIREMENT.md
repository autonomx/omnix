# Compatibility retirement

[compatibility-inventory.json](compatibility-inventory.json) records every `src/app/**/*_compat.py`: purpose, direct production imports, importing tests, disposition and deletion prerequisite. Run `python scripts/inventory_compatibility.py` after reviewing a dependency change. Import inventory is static evidence; domain integration tests cover indirect factory consumers too. The architecture allowlist gate rejects an unreviewed new compatibility filename.

| Category | Disposition |
| --- | --- |
| A — stable adapter | PostgreSQL implementations translating existing domain contracts; inline job admission normalization; supported Flux/Diffusers stack adaptation. Keep behavior, migrate names/imports coherently when useful. |
| B — migration shim | RPG gateway payload facades and document/configuration/image/RPG callbacks. Migrate consumers to typed domain services while preserving payload normalization, secret boundaries and atomicity, then delete wrappers. |
| C — dead code | Delete only after import/caller/test verification. No module in the reviewed inventory is currently classified C: all have production consumers. |

`runtime_install.py` now verifies PostgreSQL and registers only the explicit shared settings/session/voice document callbacks. It no longer changes imported feature classes/functions, patches `sys.modules`, replaces `sqlite3.connect`, or suppresses a legacy manifest through assignment. Its remaining callback contract is a migration shim, retained for `shared.py` callers and covered by runtime retirement/document integration tests.

Production defaults for chat, jobs, assets, characters/avatar, memory, provider refresh, evaluation, research and narrative use explicit `runtime_composition` factories. Document-style consumers call the frozen `DocumentServices` container. Legacy implementations keep their identities for explicitly selected test/import processes; their presence does not confer production authority. Existing job/chat decorators apply to the explicitly selected PostgreSQL implementation at factory assembly, rather than replacing a feature's exported class.

Retire remaining shims in this order: inject a typed settings/session service into `shared.py`; remove its callback registration and the installer; move assistant configuration and RPG/image document consumers to typed repositories; migrate gateway payload facade imports. Each deletion requires targeted import, serialization/normalization, transaction and tenant regression tests. Do not delete a working stable adapter merely because its historical filename contains `compat`.
