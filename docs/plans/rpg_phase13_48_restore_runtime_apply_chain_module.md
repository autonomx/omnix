# Phase 13.48 — restore runtime apply-chain module

## Context

The autoplay loader imports `tests.rpg.autoplay.runtime_apply_chain_probe` during CLI startup, but the module file was missing from `rpg`. That caused the CLI to fail before the run could start.

## Change

This hotfix restores the module with a defensive artifact writer and adds a direct import test.

The restored module writes `autoplay-runtime-apply-chain-probe.json` with source `autoplay_runtime_apply_chain_probe_v1` so the import path is stable and the run is unblocked.

## Notes

This is a startup hotfix. It does not claim to resolve the runtime recursion or performance issue. Deeper apply-chain wrapping can be reintroduced after the harness starts reliably.
