from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "docs" / "plans" / "rpg_phase8_34_runtime_authority_audit.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_34_audit_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow


def test_phase8_34_audit_note_records_authority_boundaries():
    audit = AUDIT.read_text(encoding="utf-8")
    for expected in (
        "UI runtime-authority boundary audit",
        "source-backed and provider-free",
        "does not add gameplay commands",
        "Shared panel chrome is presentation-only.",
        "Suggested actions are hints only",
        "Survival inspector actions may use command bridge hooks",
        "RpgCommandBridge.submitCommand",
        "runtime_validated_commands_only",
        "app.rpg.session.runtime_part27",
        "app.rpg.session.runtime_part23",
        "Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff.",
    ):
        assert expected in audit
