# RPG Phase 9.2 Endurance Artifact Contract Guard

Phase 9.2 guards the deterministic artifact contract for the endurance harness compatibility runner.

Latest source-of-truth SHA before this Phase 9.2 slice:

- `ee1e20d37aae0592125f7e2c0b27212e085cb6d6`

## Scope

This slice is source/test only. It does not run a live/provider 1000-turn campaign in CI.

The guarded compatibility runner is:

- `run_autoplay_campaign(args)` in `src/tests/rpg/autoplay_llm_campaign.py`

The runner remains a CI-safe compatibility surface for artifact contract validation. It must not require provider, LLM, local server, or production operator resources to prove the artifact shape.

## Required output files

`run_autoplay_campaign(args)` writes these files under `args.output_dir`:

- `autoplay-summary.json`
- `autoplay-transcript.json`
- `autoplay-campaign-results.zip`

## Required summary fields

`autoplay-summary.json` must include these top-level fields:

- `ok`
- `turns_executed`
- `health`
- `transcript_rows`
- `artifact_paths`

`artifact_paths` must expose paths for:

- `summary`
- `transcript`
- `zip`

## Required ZIP members

`autoplay-campaign-results.zip` must include:

- `summary.json`
- `autoplay-transcript.json`

## Deterministic CI boundary

The Phase 9.2 guard verifies the compatibility runner artifact contract using deterministic test doubles. It may exercise `run_autoplay_campaign(args)` in-process, but it must not require:

- live/provider calls;
- LLM calls;
- network calls;
- local model servers;
- a real 1000-turn campaign;
- gameplay command mutation outside the existing runtime validation path.

## Failure taxonomy mapping

Failures in this contract map to the Phase 9.1 taxonomy category:

- `artifact_contract_failure`

If the contract cannot be verified because it depends on live/manual evidence, classify the gap as:

- `operator_evidence_gap`

## Stop condition

Phase 9.2 is complete when CI guards prove that the compatibility runner still produces the summary, transcript, and ZIP artifact contract without provider or live endurance execution.

## Recommended next slice

After Phase 9.2, continue with:

- Phase 9.3 — endurance checkpoint and replay taxonomy guard.
