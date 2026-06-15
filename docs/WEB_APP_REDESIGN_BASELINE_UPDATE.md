# Omnix Web App Redesign Baseline Update

This note corrects the current-branch baseline after the redesign phases landed on the `rpg` branch.

## Current baseline

The redesign is no longer an early scaffold with placeholder workspaces or hand-rolled browser routing. The current `rpg` branch baseline is:

- The canonical 15-module registry is present.
- TanStack Router owns the web shell route tree.
- Mantine and Omnix design tokens back the app shell and shared primitives.
- Platform workspaces exist for Providers, Models, Jobs, Assets, Reports, Settings, and Diagnostics.
- Feature workspaces exist for RPG, Chatbot, Storyteller, Podcast, Voice / TTS, Voice Cloning, STT, and Image Generation.
- The shared event client owns reconnect, status, listener rebinding, pending reconnect cancellation, and a test/future auth-aware transport seam.
- The gateway exposes `/events` as the browser-facing live SSE stream and keeps `/api/jobs/events` as bounded history/compatibility output.
- The classic browser UI is retired; backend compatibility routes remain intentionally.

## Remaining nuance

The scheduler is implemented as resource-aware v1: local `gpu:*` jobs are mutually exclusive, CPU jobs respect configured worker limits, and network/cloud jobs are not blocked behind local GPU work. Full VRAM accounting, model residency tracking, load/evict transitions, and safe GPU co-residency remain future scheduler work.

Data preservation is mixed by data family: image assets have explicit shared-asset import diagnostics, RPG sessions/checkpoints remain readable through replay/persistence adapters, settings and reports remain gateway-readable, and voice/STT/TTS/podcast/generated media should use read-through compatibility until explicit importers are added.

## Roadmap wording to avoid

Do not describe the current branch as having placeholder module workspaces or hand-rolled routing. Those statements describe an earlier baseline and should be treated as stale if encountered in older roadmap text.
