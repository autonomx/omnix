# Desktop Companion Production Qualification

This runbook promotes Desktop Companion using real, content-free evidence from one exact runtime partition. It never treats fixtures or mixed-provider evidence as production qualification.

## Preconditions

- Deploy an exact commit from `main`.
- Keep `OMNIX_DESKTOP_COMPANION_KILL_SWITCH` unset or false.
- Keep normal rollout at `shadow` while collecting text evidence.
- Record the exact commit SHA, provider class, SHA-256 model identity, observation schema version, attention policy version, and remote/local provider status shown by the runtime evidence.
- Do not copy screenshots, visible screen text, prompts, transcripts, or generated commentary into qualification artifacts.

The default evidence store is:

```text
resources/data/desktop_companion_evaluations.json
```

Set `OMNIX_DESKTOP_COMPANION_EVALUATION_PATH` when the deployment uses a different path.

## Shadow qualification for text rollout

Collect at least twelve records for one exact partition. The records must cover:

- `static-screen`
- `typing`
- `rapid-browsing`
- `scene-change`
- `interruption`
- `screen-prompt-injection`

Generate a Markdown report:

```bash
PYTHONPATH=src python -m app.desktop_companion.qualification \
  --stage text \
  --exact-commit-sha <DEPLOYED_COMMIT_SHA> \
  --vision-provider <PROVIDER_CLASS> \
  --vision-model-hash <SHA256_MODEL_HASH> \
  --remote-provider false \
  --format markdown \
  --output resources/data/desktop-companion-text-qualification.md
```

Use `--remote-provider true` for an explicitly authorized remote provider.

Exit codes:

- `0` — the exact partition passes and is eligible for the requested rollout stage;
- `2` — evidence is insufficient; continue shadow collection without promotion;
- `3` — a safety or performance metric fails; keep rollout disabled and investigate.

A passing report is necessary but does not mutate settings. Promotion remains an explicit operator action.

## Text canary

After the text report passes:

1. Set the configured Desktop Companion stage to `text`.
2. Confirm the backend reports effective stage `text` for the exact partition.
3. Run bounded sessions with transient text comments.
4. Confirm floor conflicts retain at most one expiring candidate.
5. Confirm comments remain outside durable chat history.
6. Re-run the qualification report after any commit, model, provider, schema, or policy change.

Any partition identity change invalidates prior qualification for the new runtime.

## Speech qualification

Normal requested speech must remain degraded to text until speech-specific evidence passes. Enable the controlled deployment canary only while collecting evidence:

```text
OMNIX_DESKTOP_COMPANION_SPEECH_CANARY=1
```

Collect at least twelve speech-stage records and at least twelve completed or interrupted deliveries. Evidence must include the normal safety scenarios plus:

- `speech-completed`
- `interruption`
- `speech-stale`

Generate the speech report:

```bash
PYTHONPATH=src python -m app.desktop_companion.qualification \
  --stage speech \
  --exact-commit-sha <DEPLOYED_COMMIT_SHA> \
  --vision-provider <PROVIDER_CLASS> \
  --vision-model-hash <SHA256_MODEL_HASH> \
  --remote-provider false \
  --format markdown \
  --output resources/data/desktop-companion-speech-qualification.md
```

Disable the speech canary immediately after evidence collection. Normal speech may be enabled only when the speech report exits `0`.

## Failure handling

For `insufficient`:

- keep the current effective stage;
- collect only the missing scenarios or records in the same exact partition;
- do not combine evidence from another commit, model, provider class, or remote/local mode.

For `fail`:

- set rollout to `shadow` or `disabled`;
- use `OMNIX_DESKTOP_COMPANION_KILL_SWITCH=1` when immediate global shutdown is required;
- inspect only aggregate metric names, counts, rates, and latency;
- fix the runtime or policy and collect a new exact-build partition.

## Rollback

1. Set the configured stage to `shadow` or `disabled`.
2. Set the deployment kill switch when the browser must stop active Watch sessions immediately.
3. Disable the speech canary.
4. Preserve the failing content-free report for comparison.
5. Do not reuse evidence after the corrective commit changes the exact partition.

## Evidence deletion

Delete the configured evaluation JSON and generated qualification reports when evidence retention is no longer required. This removes aggregate records and identifiers; raw frames and commentary content are not part of these files.
