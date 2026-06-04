from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "docs" / "plans" / "rpg_phase8_32_panel_contract_inventory.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_32_inventory_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow


def test_phase8_32_inventory_note_records_contract_consolidation():
    inventory = INVENTORY.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.32 records the current provider-free panel contract inventory",
        "The shared layout registry defines nine deterministic panel slots",
        "The current Phase 8 chrome metadata families are:",
        "These metadata families are now considered consolidated for Phase 8.",
        "Do not add another metadata-only family in Phase 8",
        "No provider or LLM calls are part of the panel layout/chrome contract.",
        "Runtime and simulation remain authoritative for gameplay truth.",
        "Phase 8.33 — Browser smoke coverage for registered panels.",
        "Phase 8.34 — UI runtime-authority boundary audit.",
        "Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff.",
    ):
        assert expected in inventory
