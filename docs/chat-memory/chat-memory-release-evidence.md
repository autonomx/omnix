# Chat memory repository release evidence

Status: complete on `rpg`.

Release date: 2026-07-08.

Current release baseline after the staged rollout: `d4de5d1233db8d9cb382153a8683e3bff7bc2746`.

This document records repository implementation and rollout-gate evidence. It does not claim that every feature flag is enabled in a production deployment. Hermes synchronization remains optional and should stay disabled unless its controlled pilot is intentionally adopted.

## Required verification contract

Every implementation and rollout pull request was merged only after both required GitHub Actions workflows completed successfully on the exact pull-request head:

- `RPG Phase 0 architecture compliance`
- `RPG deterministic PR gates`

All merges used squash merge with an expected head SHA.

## MEM implementation evidence

| Phase | Pull request | Exact verified head | Squash merge SHA |
|---|---:|---|---|
| MEM-0 | #1258 | `0188a096b4c9b8fbce8f95752eb47b6c73f70bce` | `523492481395ffc5e0e3a5c3b41bd9c1a764c9e0` |
| MEM-1 | #1259 | `328afaef4fcd077c0b06c2e2830fa6c386883b74` | `41fca0f672b35ccc477f86bdcba399bab27ace19` |
| MEM-2 | #1260 | `8e065139473f9ccc5372483382aa11ff9ece80c9` | `b65b535a0cfe2b5f7567e521158049bb5659201a` |
| MEM-3 | #1261 | `604206490b0913552b8135bc9f074c49f0db17c4` | `ee0dcace3c54aed3ae6ef829fb136c1d5fce04c9` |
| MEM-4 | #1262 | `9955270410b6b39023945541b5fc8024b1fad9e0` | `83717f6e523292bff7edf90c75dc57142dc4c4c2` |
| MEM-5 | #1263 | `bd859d3395b4c74af8fe9335876cbe25c020dceb` | `0334c4b52b2d69eb251a08200103430293a5e607` |
| MEM-6 | #1264 | `4332e8fa7ec0fa9ad6af68ae2e0cec2e4ed6b725` | `dcd616cbb53fda632a439b293bda48b2eff2327b` |
| MEM-7 | #1265 | `17fde1740ec2d9c70c9ef116ed403dafe790a2e0` | `051ad37f9b3f9ebe2beed7b348f17cf1bb23f00d` |
| MEM-8 | #1266 | `00f90ad3ea772b38d25ec3307268a957781cf6a4` | `4475a14c8fffdeb4f3f50413864521f5a46722c8` |
| MEM-9 | #1267 | `2232a2a506d98292f371579c2ce9d5c0544fbd47` | `20f40d9135e3efc0d93129b8cbe6dd7d841c7499` |
| MEM-10 | #1268 | `0b44a1f8508a48101edd26e4fc31975b03768618` | `90da140c7a7b7ec53fa9997702b20e2811c03305` |
| MEM-11 | #1269 | `37218c5babf9f27b5103780074efbf2e38b8822a` | `2de5f6ba46fe4fe01540ba50991c7064dae43906` |
| MEM-12 | #1270 | `6810716bcf9ec6d76eeaa174092ce877d65aaff1` | `321ddc3653999e0ed11ddb4958e18fdf7bfcaf03` |
| MEM-13 | #1271 | `38d7ff870b77cba8a60dd48081c3d4d7d5e37cc1` | `ef9c4fa7e5c39925767b2390c8009a4fd3e23f95` |
| MEM-14 | #1272 | `5f9810f313ece492d022b14d6d8d0e86470ee378` | `69c3a321d63ee38f8208f82c229a7a3dd7bddee8` |
| MEM-15 | #1273 | `91954b6566e0c2503b0b9429d3bb3dafb34d2af0` | `aefdc5e4d8d7bab43110b8806e760540382875ec` |

## Staged rollout-gate evidence

| Stage | Boundary | Pull request | Exact verified head | Workflow runs: architecture / deterministic | Squash merge SHA |
|---|---|---:|---|---|---|
| 1 | SQLite Chat storage only | #1274 | `a672b340d71583fcf29eaaf1345116f26f8a0376` | `28965567670` / `28965567698` | `ce44a70f79a9f13d8b000cbe64d0029d685838d1` |
| 2 | Explicit approved memory | #1275 | `0941545c8b52a0ed371478a49e64d9965ab7aeb4` | `28965797506` / `28965797528` | `189552aedfd671ba15ae9160f03850cc3271c783` |
| 3 | Pending suggestions | #1276 | `d326f57749640be838ad0aed3709930cfc2183b2` | `28967878663` / `28967878671` | `e37a88a5d2a30101d55d0ab26915e8cd85edbfcc` |
| 4 | Scoped historical recall | #1277 | `8baef8b37d255059d9201e9c0c4685810d5fe531` | `28969650603` / `28969650598` | `191c5bb5080e639d3b5b4887738bdf1b7098900f` |
| 5 | Long-session compaction | #1278 | `e06526191162e193abad8740c84aab52d4086e9e` | `28970016120` / `28970016197` | `5e9161af773ca486cc91770b20f8f47659891ffb` |
| 6 | Optional Hermes adapter | #1279 | `962b884383a1a33678a240b9a03e18d98dc96e3d` | `28971861821` / `28971861823` | `d4de5d1233db8d9cb382153a8683e3bff7bc2746` |

## Rollout runbooks and preflights

| Stage | Runbook | Preflight |
|---|---|---|
| 1 | `stage-1-sqlite-rollout.md` | `scripts/chat_memory_stage1_preflight.py` |
| 2 | `stage-2-explicit-memory-rollout.md` | `scripts/chat_memory_stage2_preflight.py` |
| 3 | `stage-3-pending-suggestions-rollout.md` | `scripts/chat_memory_stage3_preflight.py` |
| 4 | `stage-4-history-recall-rollout.md` | `scripts/chat_memory_stage4_preflight.py` |
| 5 | `stage-5-long-session-compaction-rollout.md` | `scripts/chat_memory_stage5_preflight.py` |
| 6 | `stage-6-hermes-adapter-rollout.md` | `scripts/chat_memory_stage6_preflight.py` |

The runbooks are under `docs/chat-memory/`. Every preflight operates on temporary or explicitly selected stores and is designed not to mutate configured production data.

## Recommended operational posture

The fully verified native stack is Stages 1 through 5:

```text
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1
OMNIX_CHAT_HISTORY_RECALL_ENABLED=1
OMNIX_CHAT_COMPACTION_ENABLED=1
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

Enable Hermes only for a controlled pilot after backing up the selected Hermes directory and running the Stage 6 preflight.

## Rollback posture

- Each capability remains independently feature-gated.
- Disabling a capability retains native records, migrated Chat history, snapshots, summaries, and indexes unless an explicit destructive operation is requested.
- Forget remains intentionally irreversible for active memory content and frozen snapshot copies.
- Missing FTS5 or Hermes storage degrades without failing ordinary Chat.
- Pending or failed compaction keeps the complete current-session transcript available.
- SQLite-to-JSON writer alternation is not a safe rollback after new SQLite-only messages accumulate; reconcile stores first.

## Repository release conclusion

MEM-0 through MEM-15 and rollout Stages 1 through 6 are complete on `rpg`. The repository contains implementation, adversarial coverage, staged preflights, rollout guidance, rollback guidance, and exact-head merge evidence. Production flag adoption remains an operational deployment decision rather than a repository completion requirement.
