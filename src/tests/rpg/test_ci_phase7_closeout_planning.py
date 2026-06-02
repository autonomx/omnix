from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLOSEOUT_PLAN = ROOT / "docs" / "plans" / "rpg_phase7_closeout_plan.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
SOURCE = "deterministic_phase7_closeout_planning_gate"
GATE_NAME = "RPG CI Phase 7 closeout planning gate"
GATE_COMMAND = "python -m pytest src/tests/rpg/test_ci_phase7_closeout_planning.py -q --tb=short"


REQUIRED_PHASE7_COVERAGE = (
    "replay checkpoint digests and restore validation",
    "replay turn sequence validation through canonical runtime command helpers",
    "package/disk save-load replay roundtrip validation",
    "100-turn readiness analysis",
    "100-turn certification payloads and report rendering",
    "saved certification JSON emission",
    "saved/loadable state digest comparison",
    "saved output progress metrics extraction",
    "report diagnostics visibility",
    "live/manual completion-path saved artifact emission hooks",
    "saved artifact disk bundle and ZIP verification",
    "end-to-end deterministic saved 100-turn fixture certification",
    "real completion path smoke integration",
    "hardened flat/nested artifact discovery",
    "operator-facing nested layout, duplicate, and partial-output diagnostics",
)


REQUIRED_RISK_ROUTES = (
    "Full live-provider 100-turn campaign execution is not required in PR CI.",
    "Long multi-turn campaign replay is not exhaustive.",
    "Combat replay coverage is not full campaign-grade.",
    "Quest reward replay coverage is not full campaign-grade.",
    "NPC memory replay and file-backed profiles remain pending.",
    "Party/companion replay is not full campaign-grade.",
    "Full package/disk replay of an actual 100-turn campaign remains incomplete.",
    "Real saved/loadable campaign state diff validation in live completion paths needs more evidence.",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_contains(text: str, expected: str, *, source: str = SOURCE) -> None:
    assert expected in text, {"missing": expected, "source": source}


def test_ci_phase7_closeout_plan_records_provider_free_closeout_boundary():
    text = _read(CLOSEOUT_PLAN)

    for expected in (
        "RPG Phase 7 closeout plan",
        SOURCE,
        "materially complete for provider-free PR gate coverage",
        "not a claim that a full live-provider 100-turn campaign has been completed in required PR CI",
        "Required PR CI remains deterministic and provider-free",
        "Live/manual/autoplay campaign evidence remains optional local validation",
        "Move to Phase 8 UI/UX production pass",
    ):
        _assert_contains(text, expected)


def test_ci_phase7_closeout_plan_lists_completed_phase7_coverage():
    text = _read(CLOSEOUT_PLAN)

    for expected in REQUIRED_PHASE7_COVERAGE:
        _assert_contains(text, expected)


def test_ci_phase7_closeout_plan_routes_remaining_risks_forward():
    text = _read(CLOSEOUT_PLAN)

    for expected in REQUIRED_RISK_ROUTES:
        _assert_contains(text, expected)

    for expected in (
        "Phase 8/10 manual validation or a future explicit live-evidence slice",
        "Phase 9 endurance systems",
        "Phase 8 combat UI/state visibility or Phase 9 endurance",
        "Phase 8 objective/journal UI and later deterministic replay expansion",
        "Phase 5 NPC profiles/memory or Phase 8/9 follow-up",
        "Phase 8 party UI and later replay expansion",
        "Phase 9 endurance and Phase 10 packaging/stability",
        "Future live/manual evidence slice if needed",
    ):
        _assert_contains(text, expected)


def test_ci_phase7_closeout_plan_preserves_architecture_boundaries():
    text = _read(CLOSEOUT_PLAN)

    for expected in (
        "Simulation/runtime remains authoritative.",
        "LLM/provider output remains presentation/advisory only.",
        "Deterministic diagnostics remain provider-free and source-backed.",
        "Rejected commands must not be treated as successful state changes.",
        "Digest mismatches, replay drift, persistence drift, readiness blockers",
        "Generated runtime outputs under `resources/data/test-results` must not be committed.",
    ):
        _assert_contains(text, expected)


def test_ci_phase7_closeout_workflow_gate_is_ordered_before_manifest():
    workflow = _read(WORKFLOW)

    _assert_contains(workflow, GATE_NAME)
    _assert_contains(workflow, GATE_COMMAND)

    previous_gate = "RPG CI Phase 7 saved artifact operator UX diagnostics gate"
    next_gate = "RPG CI runtime facade manifest gate"
    assert workflow.index(previous_gate) < workflow.index(GATE_NAME) < workflow.index(next_gate)


def test_ci_phase7_closeout_ready_contract():
    closeout = _read(CLOSEOUT_PLAN)
    workflow = _read(WORKFLOW)
    blockers = []

    for expected in REQUIRED_RISK_ROUTES:
        if expected not in closeout:
            blockers.append({"kind": "missing_remaining_risk_route", "risk": expected, "source": SOURCE})
    if "Move to Phase 8 UI/UX production pass" not in closeout:
        blockers.append({"kind": "missing_phase8_entry_recommendation", "source": SOURCE})
    if "full live-provider 100-turn campaign" not in closeout:
        blockers.append({"kind": "missing_live_provider_boundary", "source": SOURCE})
    if GATE_NAME not in workflow:
        blockers.append({"kind": "workflow_missing_phase7_closeout_gate", "source": SOURCE})

    readiness = {
        "ok": not blockers,
        "reason": "phase7_closeout_planning_ready" if not blockers else "phase7_closeout_planning_not_ready",
        "blockers": blockers,
        "source": SOURCE,
    }

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_closeout_planning_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == SOURCE
