# RPG AI RPG Parity Phase 19 — World Runtime

Phase 19 wires the deterministic world graph foundation into report-facing runtime metadata.

## Landed

- Added `src/app/rpg/world_runtime.py`.
- Parses runtime map/world state into the Phase 3 `RpgRegionGraph` contract.
- Reports known safe instant-travel eligibility.
- Exposes map debug payloads for current location, known exits, stubs, locations, and route count.
- Checks save/load state groups needed by map/travel features.
- Added tests for safe travel, stub expansion blocking, and map parsing.

## Verification

Pending GitHub Actions for the Phase 19 PR.
