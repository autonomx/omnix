# Interactive RPG foreground-turn baseline

Status: deterministic Phase 0 evidence restored. Live-provider latency and dialogue-quality evidence remains local-only.

## Purpose

This baseline gives the interactive RPG roadmap a reproducible starting point for the Rusty Flagon dialogue path. It verifies the foreground orchestration contract without requiring an active LLM in GitHub Actions.

The deterministic benchmark is:

```text
src/tests/rpg/performance/foreground_turn_benchmark.py
```

It executes this scenario:

```text
Location: The Rusty Flagon
NPC: Bran
Player command: I ask Bran how business is doing.
```

The benchmark uses a deterministic provider stub and a temporary SQLite job store. It then repeats the same submission ID to verify idempotent recovery. No external endpoint, model, secret, or network connection is used.

## Run locally

From the repository root:

```powershell
$env:PYTHONPATH = "src"
python src/tests/rpg/performance/foreground_turn_benchmark.py
```

To retain the report:

```powershell
python src/tests/rpg/performance/foreground_turn_benchmark.py `
  --output resources/data/test-results/rpg-foreground-turn-baseline.json
```

The generated JSON is runtime evidence and should not be committed when it contains machine-specific timings.

## Provider-free invariant baseline

The deterministic run must report:

| Measurement | Required value |
|---|---:|
| Foreground `apply_turn` executions | 1 |
| Provider-boundary calls | 1 deterministic stub call |
| Session loads | 1 |
| Session saves | 1 |
| Foreground job records | 1 |
| Job transitions | create 1, running 1, complete 1, fail 0 |
| Idempotent replay executions | 0 additional executions |
| Interaction sequence | 1 |
| Simulation tick | 1 |
| Response contract | `rpg_turn_response_v2` |
| Response size | greater than 0 and at most 50,000 bytes |
| Browser-visible NPC line | Bran is present and answers the business question |

The report also records foreground orchestration time, serialization time, response bytes, job states, submission identity, interaction identity, and final browser-visible text. These timings are diagnostic only because CI hardware and the deterministic stub do not represent local model latency.

## Live-provider acceptance baseline

Live LLM validation must not run in GitHub Actions. It requires an active configured provider and explicit local opt-in through `OMNIX_RPG_LIVE_SMOKE=1`.

The original dialogue latency targets are:

| Metric | Target |
|---|---:|
| Median foreground dialogue latency | at most 1.5 seconds |
| p95 foreground dialogue latency | at most 2.5 seconds |
| Foreground response size | at most 50,000 bytes |
| Distinct command interactions | at least 3 |
| Same-submission replay | same interaction ID, no second execution |

The local smoke harness now exits unsuccessfully when the median or p95 target is missed. Provider-free tests may verify the evaluator with static latency samples, but they must never invoke an LLM.

## Interpretation

A passing deterministic benchmark proves the following narrow claims:

- the benchmarked foreground request executes once;
- the same submission is recovered rather than executed again;
- one canonical compact response can be constructed;
- the expected Bran dialogue is browser-visible;
- job, interaction, simulation, response-size, and serialization evidence is captured.

It does not prove real-provider latency, natural dialogue quality, GPU queue behavior, browser commit latency, or cross-process idempotency. Those remain separate implementation and local-operator acceptance items.
