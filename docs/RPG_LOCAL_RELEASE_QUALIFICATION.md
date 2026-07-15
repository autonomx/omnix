# RPG Local Release Qualification

Status: operator-run evidence required after provider-free GitHub checks pass.

## Purpose

GitHub Actions validates deterministic architecture, persistence, regression, web, and endurance contracts without contacting a live model provider. This procedure combines the remaining machine-specific evidence into one final local report:

1. live turn latency, response, and idempotent replay evidence;
2. category-complete dialogue-quality evidence from the configured provider;
3. browser commit-to-visible timing evidence.

The aggregate report is local operational evidence. Do not commit prompts, provider responses, private campaign state, secrets, or raw session payloads.

## Prerequisites

- PostgreSQL and the Omnix gateway are running.
- The intended local LLM provider is configured and healthy.
- A disposable or backed-up RPG session is available for the latency smoke. The dialogue matrix creates and archives an isolated fixture session for each known case.
- Browser timing samples have been exported as JSON under either a `samples` or `reports` array.

## Generate evidence

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "src"
$env:OMNIX_RPG_LIVE_SMOKE = "1"

python scripts/rpg_interactive_live_smoke.py `
  --session-id "<session-id>" `
  --output resources/data/reports/rpg-live-smoke-local.json

python -m app.rpg.local_dialogue_quality_smoke `
  --output resources/data/reports/rpg-dialogue-quality-local.json
```

Export at least three distinct browser interaction timing samples to:

```text
resources/data/reports/rpg-browser-timing-local.json
```

Accepted sample shape:

```json
{
  "samples": [
    {
      "interactionId": "interaction:1",
      "client": {
        "commitToVisibleMs": 24.0,
        "requestToVisibleMs": 1200.0
      }
    }
  ]
}
```

## Build the final qualification report

```powershell
python scripts/rpg_interactive_local_acceptance.py `
  --live-smoke-report resources/data/reports/rpg-live-smoke-local.json `
  --dialogue-quality-report resources/data/reports/rpg-dialogue-quality-local.json `
  --browser-timing-report resources/data/reports/rpg-browser-timing-local.json `
  --output resources/data/reports/rpg-local-release-acceptance.json
```

The command exits with:

- `0` when all three evidence surfaces pass;
- `1` when evidence is valid JSON but one or more release gates fail;
- `2` when an input cannot be read or has an invalid structure.

## Acceptance boundary

The aggregate must show:

- the live smoke report passed its response, replay, distinct-interaction, median, and p95 gates;
- the dialogue-quality report passed all configured category and privacy gates;
- at least three browser samples are present;
- every sample has an interaction identity and commit-to-visible timing;
- browser commit-to-visible time is at most 50 milliseconds.

Provider-free GitHub checks remain mandatory. This local report supplements them; it does not replace exact-head CI evidence.
