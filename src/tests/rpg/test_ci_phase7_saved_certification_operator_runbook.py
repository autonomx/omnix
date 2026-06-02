from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = ROOT / "docs" / "rpg_saved_certification_runbook.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
SOURCE = "deterministic_phase7_saved_certification_operator_runbook_gate"
GATE_NAME = "RPG CI Phase 7 saved certification operator runbook gate"
GATE_COMMAND = "python -m pytest src/tests/rpg/test_ci_phase7_saved_certification_operator_runbook.py -q --tb=short"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_contains(text: str, expected: str) -> None:
    assert expected in text, f"{expected!r} missing from runbook"


def test_ci_phase7_saved_certification_operator_runbook_documents_invocation_and_artifacts():
    text = _read(RUNBOOK)

    for expected in (
        "RPG saved certification operator runbook",
        "emit_live_manual_saved_artifact_completion_hooks",
        "write_and_verify_saved_artifact_bundle_zip",
        "emit_saved_100_turn_certification_artifacts",
        "phase7_100_turn_certification.json",
        "campaign_report.html",
        "autoplay_report.html",
        "manual_report.html",
        "autoplay_transcript.json",
        "manual_transcript.json",
        "turn_rows.json",
        "transcript_rows.json",
        "final_session.json",
        "final_state.json",
        "campaign_final_state.json",
        "loadable_session.json",
        "loaded_session.json",
        "saved_session.json",
        "loadable_state.json",
        "manual-rpg-test-results.zip",
        "resources/data/test-results",
    ):
        _assert_contains(text, expected)


def test_ci_phase7_saved_certification_operator_runbook_documents_payload_fields_and_diagnostics():
    text = _read(RUNBOOK)

    for expected in (
        "certification_result",
        "certification_contract",
        "normalized_artifact",
        "report_diagnostics",
        "emission_hook_source",
        "emission_hook_diagnostics",
        "emission_hook_blockers",
        "artifact_writer_source",
        "skipped_emission",
        "missing_output_directory",
        "missing_report_html",
        "missing_transcript_artifacts",
        "missing_state_checkpoint_artifacts",
        "certification_payload_emission_blocker",
        "missing_bundle_output_directory",
        "missing_bundle_artifact",
        "missing_results_zip",
        "unreadable_or_empty_results_zip",
        "missing_zip_artifact",
        "readiness blockers/warnings",
        "certification blockers/warnings",
        "checkpoint/state digest mismatches",
    ):
        _assert_contains(text, expected)


def test_ci_phase7_saved_certification_operator_runbook_matches_helper_constants():
    from tests.rpg.manual.bundle_verification import REQUIRED_BUNDLE_GROUPS, REQUIRED_ZIP_GROUPS
    from tests.rpg.manual.bundle_verification import SOURCE as BUNDLE_SOURCE
    from tests.rpg.manual.certification_artifacts import CERTIFICATION_PAYLOAD_FILENAME
    from tests.rpg.manual.certification_artifacts import SOURCE as WRITER_SOURCE
    from tests.rpg.manual.emission_hooks import REPORT_HTML_FILENAMES
    from tests.rpg.manual.emission_hooks import SOURCE as EMISSION_SOURCE
    from tests.rpg.manual.progress_metrics_certification import TRANSCRIPT_FILENAMES
    from tests.rpg.manual.saved_state_certification import FINAL_STATE_FILENAMES, LOADABLE_STATE_FILENAMES

    text = _read(RUNBOOK)

    for expected in (
        CERTIFICATION_PAYLOAD_FILENAME,
        WRITER_SOURCE,
        EMISSION_SOURCE,
        BUNDLE_SOURCE,
    ):
        _assert_contains(text, expected)

    for filename in REPORT_HTML_FILENAMES:
        _assert_contains(text, filename)
    for filename in TRANSCRIPT_FILENAMES:
        _assert_contains(text, filename)
    for filename in FINAL_STATE_FILENAMES:
        _assert_contains(text, filename)
    for filename in LOADABLE_STATE_FILENAMES:
        _assert_contains(text, filename)

    assert "report_html" in REQUIRED_BUNDLE_GROUPS
    assert "report_html" not in REQUIRED_ZIP_GROUPS
    _assert_contains(text, "Report HTML must exist in the saved bundle")
    _assert_contains(text, "ZIP HTML inclusion is not the machine-readable requirement")


def test_ci_phase7_saved_certification_operator_runbook_workflow_gate_is_ordered():
    workflow = _read(WORKFLOW)
    runbook = _read(RUNBOOK)

    _assert_contains(workflow, GATE_NAME)
    _assert_contains(workflow, GATE_COMMAND)
    _assert_contains(runbook, GATE_NAME)
    _assert_contains(runbook, GATE_COMMAND)

    previous_gate = "RPG CI Phase 7 saved artifact bundle ZIP verification gate"
    next_gate = "RPG CI runtime facade manifest gate"
    assert workflow.index(previous_gate) < workflow.index(GATE_NAME) < workflow.index(next_gate)


def test_ci_phase7_saved_certification_operator_runbook_readiness_contract():
    workflow = _read(WORKFLOW)
    runbook = _read(RUNBOOK)
    blockers = []

    if "provider-free" not in runbook:
        blockers.append({"kind": "runbook_missing_provider_free_invariant", "source": SOURCE})
    if "optional local validation" not in runbook:
        blockers.append({"kind": "runbook_missing_live_provider_optional_guidance", "source": SOURCE})
    if "Do not commit generated runtime outputs" not in runbook:
        blockers.append({"kind": "runbook_missing_runtime_artifact_commit_warning", "source": SOURCE})
    if GATE_NAME not in workflow:
        blockers.append({"kind": "workflow_missing_runbook_gate", "source": SOURCE})

    readiness = {
        "ok": not blockers,
        "reason": "phase7_saved_certification_operator_runbook_ready"
        if not blockers
        else "phase7_saved_certification_operator_runbook_not_ready",
        "blockers": blockers,
        "source": SOURCE,
    }

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_saved_certification_operator_runbook_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == SOURCE
