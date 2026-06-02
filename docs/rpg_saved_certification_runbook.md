# RPG saved certification operator runbook

This runbook explains how to produce, inspect, and verify Phase 7 saved certification artifacts for manual and autoplay RPG campaign runs. It is intentionally operator-facing: the deterministic CI gates validate the artifact contracts without requiring a live LLM/provider run, while developers can use the same artifact shapes after an optional local live-provider run.

## Scope and invariants

- Simulation/runtime state is authoritative. LLM/provider output is presentation/advisory only.
- Phase 7 saved certification helpers are provider-free, deterministic, idempotent, and non-mutating except for explicit artifact emission/write calls.
- Required PR CI does not run a live-provider 100-turn campaign. Live/manual/autoplay runs are optional local operator activity.
- Do not commit generated runtime outputs under `resources/data/test-results`.
- Saved certification diagnostics are source-backed and should be treated as the first place to inspect missing artifacts, digest drift, readiness blockers, or ZIP omissions.

## Local/manual/autoplay invocation pattern

A local operator run should produce a saved output directory containing the campaign report, transcript rows, and final/loadable state artifacts. The deterministic completion hook can then discover those artifacts and emit the saved certification payload.

Typical manual/autoplay completion path:

1. Run the local manual or autoplay scenario using the developer's configured environment.
2. Write artifacts into a disposable output directory under the local test-results root, for example `resources/data/test-results/<run-id>/`.
3. Ensure the output directory contains a report HTML file, transcript rows, a final saved state, and a loadable saved state.
4. Invoke or rely on the completion hook helper `emit_live_manual_saved_artifact_completion_hooks` from `src/tests/rpg/manual/emission_hooks.py`.
5. Inspect `phase7_100_turn_certification.json` and the appended report HTML diagnostics.
6. Use `write_and_verify_saved_artifact_bundle_zip` from `src/tests/rpg/manual/bundle_verification.py` when a manual-style results ZIP should be produced and verified.
7. Delete or archive generated runtime artifacts outside the repository before committing code.

Example provider-free helper invocation shape for an already-populated output directory:

```python
from pathlib import Path
from tests.rpg.manual.emission_hooks import emit_live_manual_saved_artifact_completion_hooks
from tests.rpg.manual.bundle_verification import write_and_verify_saved_artifact_bundle_zip

output_dir = Path("resources/data/test-results/local-phase7-run")

emitted = emit_live_manual_saved_artifact_completion_hooks({}, output_dir=output_dir)
verified = write_and_verify_saved_artifact_bundle_zip(output_dir=output_dir)

print(emitted["ok"], emitted["reason"])
print(verified["ok"], verified["reason"])
```

This example assumes the output directory already exists. It is safe for deterministic CI fixtures because it does not require a provider call; live-provider campaign generation remains optional local work outside required PR CI.

## Expected saved artifacts

The saved output directory should include these artifacts when a complete run is available:

- `phase7_100_turn_certification.json` — canonical machine-readable saved certification payload emitted by `emit_saved_100_turn_certification_artifacts`.
- Report HTML such as `campaign_report.html`, `autoplay_report.html`, `manual_report.html`, `html/campaign_report.html`, `html/autoplay_report.html`, or `html/manual_report.html`.
- Transcript rows such as `autoplay_transcript.json`, `manual_transcript.json`, `turn_rows.json`, or `transcript_rows.json`.
- Final saved state such as `final_session.json`, `final_state.json`, or `campaign_final_state.json`.
- Loadable saved state such as `loadable_session.json`, `loaded_session.json`, `saved_session.json`, or `loadable_state.json`.
- Results ZIP such as `manual-rpg-test-results.zip` when ZIP verification is requested.

The disk bundle verifier requires the certification payload, report HTML, transcript artifact, final state artifact, and loadable state artifact. The ZIP verifier requires the machine-readable certification payload, transcript artifact, final state artifact, and loadable state artifact. Report HTML must exist in the saved bundle; ZIP HTML inclusion is not the machine-readable requirement.

## Important JSON fields

The saved certification payload is the canonical artifact for automation and operator inspection. Important fields include:

- `certification_result` — the Phase 7 certification result, status, blockers, warnings, readiness data, and state/checkpoint digest comparison.
- `certification_contract` — the deterministic contract for the certification path.
- `normalized_artifact` — normalized saved artifact data consumed by the certifier.
- `report_diagnostics` — source-backed diagnostics rendered into the saved report HTML.
- `emission_hook_source` — source constant for the completion hook that discovered and emitted artifacts.
- `emission_hook_diagnostics` — source-backed discovery and emission diagnostics.
- `emission_hook_blockers` — blockers detected while building the saved certification payload from manual/autoplay artifacts.
- `artifact_writer_source` — source constant for the artifact writer that emitted `phase7_100_turn_certification.json`.

Digest-related fields may also appear when final/loadable/expected checkpoint or state digests are available. Digest mismatch blockers must not be ignored.

## Source constants and helpers

Keep operator guidance aligned with these deterministic source constants and helper names:

- `deterministic_phase7_saved_certification_artifact_writer_gate` — `emit_saved_100_turn_certification_artifacts` in `src/tests/rpg/manual/certification_artifacts.py`.
- `deterministic_phase7_live_manual_saved_artifact_emission_hooks_gate` — `emit_live_manual_saved_artifact_completion_hooks` in `src/tests/rpg/manual/emission_hooks.py`.
- `deterministic_phase7_saved_artifact_bundle_zip_verification_gate` — `write_and_verify_saved_artifact_bundle_zip` in `src/tests/rpg/manual/bundle_verification.py`.
- `deterministic_phase7_saved_certification_operator_runbook_gate` — this runbook's source guard test in `src/tests/rpg/test_ci_phase7_saved_certification_operator_runbook.py`.

These constants are intentionally repeated here so source guards catch stale operator instructions when helper names, artifact filenames, or workflow gate names change.

## Diagnostics and blockers to inspect

Common source-backed diagnostics/blockers include:

- `skipped_emission` — emission hook was disabled; no saved certification artifacts should be expected from that invocation.
- `missing_output_directory` — manual/autoplay output directory was absent; emission remains non-mutating.
- `missing_report_html` — report HTML could not be discovered for appended diagnostics.
- `missing_transcript_artifacts` — transcript rows were not found.
- `missing_state_checkpoint_artifacts` — final and/or loadable state artifacts were not found.
- `certification_payload_emission_blocker` — progress/state certification produced blockers that were threaded into emission diagnostics.
- `missing_bundle_output_directory` — bundle verification target directory was absent.
- `missing_bundle_artifact` — a required disk bundle artifact group was absent.
- `missing_results_zip` — ZIP verification target was absent.
- `unreadable_or_empty_results_zip` — ZIP existed but could not be read or contained no entries.
- `missing_zip_artifact` — a required machine-readable artifact group was absent from the ZIP.
- readiness blockers/warnings — Phase 7 readiness reported incomplete turns, report/transcript budget issues, loop risk, or missing progress signals.
- certification blockers/warnings — full 100-turn certification failed due to turn count, readiness critical blockers, missing severity counts, or digest mismatch.
- checkpoint/state digest mismatches — final/loadable/expected checkpoint or state digests diverged.

A complete saved certification path should make these diagnostics visible in both `phase7_100_turn_certification.json` and the appended report HTML when a report file is present.

## Deterministic CI versus optional live-provider run

Required PR CI should run only deterministic, provider-free tests. The Phase 7 saved certification gates use tiny fixtures that mimic real output directories, reports, transcripts, and saved states. They verify helper contracts, source constants, artifact names, report diagnostics, emission hook behavior, and bundle/ZIP inclusion.

Live-provider 100-turn autoplay is useful for operator confidence, but it remains optional local validation. Its outputs should be inspected through the same saved certification payload and diagnostics instead of being committed to the repository.

## Current deterministic gates

The Phase 7 saved certification path is guarded by these workflow gates:

- `RPG CI Phase 7 saved certification artifact writer gate`
- `RPG CI Phase 7 saved autoplay digest source gate`
- `RPG CI Phase 7 real saved state certification gate`
- `RPG CI Phase 7 real autoplay progress metrics gate`
- `RPG CI Phase 7 saved certification report diagnostics gate`
- `RPG CI Phase 7 live manual saved artifact emission hooks gate`
- `RPG CI Phase 7 saved artifact bundle ZIP verification gate`
- `RPG CI Phase 7 saved certification operator runbook gate`

Run the runbook guard directly with:

```bash
python -m pytest src/tests/rpg/test_ci_phase7_saved_certification_operator_runbook.py -q --tb=short
```

The runbook guard keeps this document aligned with current helper names, artifact filenames, source constants, workflow gate names, diagnostic names, and expected JSON field names.
