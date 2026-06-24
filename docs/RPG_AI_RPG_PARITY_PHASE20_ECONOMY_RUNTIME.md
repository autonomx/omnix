# RPG AI RPG Parity Phase 20 — Economy Runtime

Phase 20 wires deterministic shop and service helpers into report-facing runtime action metadata.

## Landed

- Added `src/app/rpg/economy_runtime.py`.
- Resolves report-facing buy-item actions through deterministic merchant stock and wallet rules.
- Resolves service authorization through deterministic payment or exception rules.
- Reports wallet-before, wallet-after, stock-after, service reason, and issues.
- Added smoke tests for item purchase and service gating.

## Verification

Pending GitHub Actions for the Phase 20 PR.
