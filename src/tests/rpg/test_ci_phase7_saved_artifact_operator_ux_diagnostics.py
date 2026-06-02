from __future__ import annotations

import json
from pathlib import Path

from tests.rpg.manual.artifact_discovery import (
    discover_artifact_group,
    expanded_artifact_candidates,
)


ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = ROOT / "docs" / "rpg_saved_certification_runbook.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
SOURCE = "deterministic_phase7_saved_artifact_operator_ux_diagnostics_gate"
GATE_NAME = "RPG CI Phase 7 saved artifact operator UX diagnostics gate"
GATE_COMMAND = "python -m pytest src/tests/rpg/test_ci_phase7_saved_artifact_operator_ux_diagnostics.py -q --tb=short"


NESTED_LAYOUT_EXAMPLES = (
    "reports/campaign_report.html",
    "reports/campaign_report.json",
    "transcripts/autoplay_transcript.json",
    "states/final_session.json",
    "states/loadable_session.json",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_contains(text: str, expected: str, *, source: str = SOURCE) -> None:
    assert expected in text, {"missing": expected, "source": source}


def test_ci_phase7_saved_artifact_operator_ux_runbook_documents_hardened_discovery_paths():
    runbook = _read(RUNBOOK)

    for expected in (
        "src/tests/rpg/manual/artifact_discovery.py",
        "expanded_artifact_candidates",
        "discover_artifact_group",
        "read_json_artifact_group",
        "deterministic_phase7_real_artifact_discovery_hardening_gate",
        "deterministic_phase7_saved_artifact_operator_ux_diagnostics_gate",
        "Duplicate candidates are not silently ignored",
        "Provider-free CI does not run live autoplay",
        "does not require generated `resources/data/test-results` outputs to exist",
    ):
        _assert_contains(runbook, expected)

    for expected in NESTED_LAYOUT_EXAMPLES:
        _assert_contains(runbook, expected)

    for expected in (
        "artifacts/reports/",
        "artifacts/html/",
        "artifacts/transcripts/",
        "artifacts/states/",
        "missing_artifact_group",
        "ambiguous_artifact_group_candidates",
        "selected_path",
        "matches",
    ):
        _assert_contains(runbook, expected)


def test_ci_phase7_saved_artifact_operator_ux_nested_candidates_match_operator_examples():
    candidates = expanded_artifact_candidates(
        (
            "campaign_report.html",
            "campaign_report.json",
            "autoplay_transcript.json",
            "final_session.json",
            "loadable_session.json",
        )
    )

    for expected in NESTED_LAYOUT_EXAMPLES:
        assert expected in candidates, {"missing_candidate": expected, "source": SOURCE}


def test_ci_phase7_saved_artifact_operator_ux_discovery_reports_nested_and_ambiguous_candidates(tmp_path):
    (tmp_path / "campaign_report.html").write_text("<html>root</html>", encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "campaign_report.html").write_text("<html>nested</html>", encoding="utf-8")

    discovered = discover_artifact_group(
        output_dir=tmp_path,
        group="report_html",
        names=("campaign_report.html",),
        required=True,
        source=SOURCE,
    )

    assert discovered["ok"] is True
    assert discovered["selected_path"] == "campaign_report.html"
    assert discovered["matches"][:2] == ["campaign_report.html", "reports/campaign_report.html"]
    assert discovered["blockers"] == []
    assert discovered["source"] == SOURCE
    ambiguous = [
        diagnostic
        for diagnostic in discovered["diagnostics"]
        if diagnostic.get("kind") == "ambiguous_artifact_group_candidates"
    ]
    assert ambiguous == [
        {
            "kind": "ambiguous_artifact_group_candidates",
            "source": SOURCE,
            "group": "report_html",
            "selected_path": "campaign_report.html",
            "matches": ["campaign_report.html", "reports/campaign_report.html"],
        }
    ]


def test_ci_phase7_saved_artifact_operator_ux_partial_outputs_emit_source_backed_blockers(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "campaign_report.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    discovered = discover_artifact_group(
        output_dir=tmp_path,
        group="loadable_state",
        names=("loadable_session.json", "loadable_state.json"),
        required=True,
        source=SOURCE,
    )

    assert discovered["ok"] is False
    assert discovered["reason"] == "phase7_artifact_group_missing"
    assert discovered["selected_path"] == ""
    assert discovered["matches"] == []
    assert discovered["source"] == SOURCE
    assert discovered["blockers"] == [
        {
            "kind": "missing_artifact_group",
            "source": SOURCE,
            "group": "loadable_state",
            "output_dir": str(tmp_path),
            "candidates": discovered["candidates"],
        }
    ]


def test_ci_phase7_saved_artifact_operator_ux_workflow_gate_is_ordered_after_discovery_hardening():
    workflow = _read(WORKFLOW)
    runbook = _read(RUNBOOK)

    _assert_contains(workflow, GATE_NAME)
    _assert_contains(workflow, GATE_COMMAND)
    _assert_contains(runbook, GATE_NAME)
    _assert_contains(runbook, GATE_COMMAND)

    previous_gate = "RPG CI Phase 7 real artifact discovery hardening gate"
    next_gate = "RPG CI runtime facade manifest gate"
    assert workflow.index(previous_gate) < workflow.index(GATE_NAME) < workflow.index(next_gate)


def test_ci_phase7_saved_artifact_operator_ux_ready_contract():
    runbook = _read(RUNBOOK)
    workflow = _read(WORKFLOW)
    blockers = []

    for expected in NESTED_LAYOUT_EXAMPLES:
        if expected not in runbook:
            blockers.append({"kind": "missing_nested_layout_example", "path": expected, "source": SOURCE})
    if "ambiguous_artifact_group_candidates" not in runbook:
        blockers.append({"kind": "missing_ambiguity_diagnostic_guidance", "source": SOURCE})
    if "Provider-free CI does not run live autoplay" not in runbook:
        blockers.append({"kind": "missing_provider_free_live_autoplay_boundary", "source": SOURCE})
    if GATE_NAME not in workflow:
        blockers.append({"kind": "workflow_missing_operator_ux_gate", "source": SOURCE})
    if "resources/data/test-results" in workflow and "upload-artifact" not in workflow:
        blockers.append({"kind": "workflow_requires_generated_test_results", "source": SOURCE})

    readiness = {
        "ok": not blockers,
        "reason": "phase7_saved_artifact_operator_ux_diagnostics_ready"
        if not blockers
        else "phase7_saved_artifact_operator_ux_diagnostics_not_ready",
        "blockers": blockers,
        "source": SOURCE,
    }

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_saved_artifact_operator_ux_diagnostics_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == SOURCE
