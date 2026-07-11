# RPG Response Generation Roadmap Completion Note

Source roadmap: `docs/RPG_RESPONSE_GENERATION_ROADMAP.md`  
Implementation branch: `agent/rpg-response-generation-0-10`  
Pull request: `#1325`

## Completion status

The Phase 0-10 implementation is complete at the code and provider-free regression level.

The completed system includes:

- one canonical response-generation and publication pipeline;
- strict typed claim, visibility, speaker, proposal, mutation, and player-agency gates;
- current-turn-first context compilation and local evidence retrieval;
- bounded Hermes proposal-only recovery;
- ephemeral-by-default soft truth with deterministic promotion and replay-safe persistence;
- authoritative prompt/model profiles resolved before generation;
- validation-before-delivery sentence and audio-unit boundaries;
- canonical runtime, world-scene, creator-route, and early-return turn publication;
- developer traces, deterministic regression fixtures, replay checks, and bounded endurance evidence.

## GitHub Actions provider boundary

Hosted GitHub runners do not have access to the configured LM Studio or another live RPG prose provider. Therefore GitHub Actions intentionally runs only provider-free evidence:

- `RPG Phase 0 architecture compliance`;
- deterministic backend, web, response-generation, and narration-queue regressions;
- continuous 1000-turn public `apply_turn()` endurance;
- the `RPG deterministic PR gates` aggregate check.

Live-LLM autoplay is not run, simulated, or silently downgraded inside GitHub Actions. A source guard under `src/tests/rpg/response_generation/test_ci_provider_boundaries.py` enforces this boundary.

## Provider-backed local validation

Run live autoplay only in an environment where the configured provider is available.

Example PowerShell invocation from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m tests.rpg.autoplay_llm_campaign `
  --autoplay-profile smoke_100 `
  --turns 100 `
  --session-id response-generation-live-100 `
  --scenario-seed tavern_story_seed `
  --random-seed 1101 `
  --player-agent scripted `
  --strategy goal_directed_quest_runner `
  --narration-mode deferred `
  --background-llm-mode combined `
  --checkpoint-every 20 `
  --checkpoint-mode blocking `
  --artifact-detail summary `
  --transcript-detail auto `
  --fail-on-runtime-error `
  --fail-on-compatibility-turn-runtime `
  --output-dir resources/data/test-results/rpg-response-generation-live-100
```

Validate the resulting provider-backed summary separately:

```powershell
python scripts/validate_rpg_response_autoplay_summary.py `
  --summary resources/data/test-results/rpg-response-generation-live-100/autoplay-summary.json `
  --expected-turns 100 `
  --report resources/data/test-results/rpg-response-generation-live-100/gate.json
```

The labeled live-model benchmark remains informational and opt-in:

```powershell
$env:OMNIX_RPG_RESPONSE_LIVE_BENCHMARK = "1"
python scripts/rpg_response_generation_live_benchmark.py `
  --observations <live-observations.json> `
  --output <live-benchmark-report.json>
```

## Release interpretation

Provider-free implementation and deterministic safety gates are required for merge. Provider-backed prose quality and live-model latency evidence are environment-specific operational evidence and must not be fabricated by CI when no live provider exists.
