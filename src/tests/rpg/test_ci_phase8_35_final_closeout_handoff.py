from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HANDOFF = ROOT / "docs" / "plans" / "rpg_phase8_final_closeout_handoff.md"
CLOSEOUT = ROOT / "docs" / "plans" / "rpg_phase8_closeout_plan.md"
INVENTORY = ROOT / "docs" / "plans" / "rpg_phase8_32_panel_contract_inventory.md"
SMOKE = ROOT / "docs" / "plans" / "rpg_phase8_33_browser_smoke_coverage.md"
AUTHORITY = ROOT / "docs" / "plans" / "rpg_phase8_34_runtime_authority_audit.md"


def test_phase8_35_final_handoff_marks_phase8_complete_and_bounded():
    handoff = HANDOFF.read_text(encoding="utf-8")
    for expected in (
        "Phase 8 is complete as a provider-free UI/UX foundation pass.",
        "The bounded Phase 8 closeout checklist is complete:",
        "Phase 8.31 — closeout plan.",
        "Phase 8.32 — panel contract inventory and consolidation.",
        "Phase 8.33 — browser smoke coverage for registered panels.",
        "Phase 8.34 — UI runtime-authority boundary audit.",
        "Phase 8.35 — final closeout note and Phase 9 handoff.",
        "Do not add more Phase 8 slices unless a required gate exposes a concrete regression",
    ):
        assert expected in handoff


def test_phase8_35_final_handoff_links_prior_closeout_artifacts():
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert CLOSEOUT.exists()
    assert INVENTORY.exists()
    assert SMOKE.exists()
    assert AUTHORITY.exists()
    for expected in (
        "deterministic panel layout registry",
        "shared panel chrome coverage",
        "registered panel inventory",
        "shared chrome metadata consolidation",
        "source-backed smoke coverage expectations",
        "escaped dynamic rendering expectations",
        "UI runtime-authority boundary audit",
    ):
        assert expected in handoff


def test_phase8_35_final_handoff_preserves_runtime_authority_boundary():
    handoff = HANDOFF.read_text(encoding="utf-8")
    for expected in (
        "Simulation/runtime remains authoritative for gameplay truth.",
        "Registered UI panels remain presentation-oriented.",
        "Suggested actions remain hints until runtime validates a command.",
        "Survival inspector command hooks remain runtime-validated command intents.",
        "Rejected or non-player-turn actions must not be treated as successful state changes.",
        "app.rpg.session.runtime_part27",
        "app.rpg.session.runtime_part23",
    ):
        assert expected in handoff


def test_phase8_35_final_handoff_defines_phase9_entry():
    handoff = HANDOFF.read_text(encoding="utf-8")
    for expected in (
        "Phase 9 — 1000-turn endurance systems",
        "Phase 9.1 — endurance harness baseline and failure taxonomy",
        "establish the current 1000-turn target harness entry point",
        "define deterministic failure categories for endurance runs",
        "record what is CI-gated versus operator/manual evidence",
        "preserve runtime authority and provider boundaries",
        "avoid adding UI polish unless required by an endurance failure",
    ):
        assert expected in handoff


def test_phase8_35_final_handoff_routes_remaining_risks_forward():
    handoff = HANDOFF.read_text(encoding="utf-8")
    for expected in (
        "Phase 8 was not a full visual/gameplay UI overhaul.",
        "deeper visual design system/component framework work",
        "live/manual campaign UI evidence",
        "full playable-sequence persistence",
        "long multi-turn replay coverage",
        "NPC file-backed profiles/persona/memory polish",
        "production packaging and 1000-turn endurance hardening",
        "routed into a new explicit UI phase with a bounded checklist",
        "handled as a targeted fix required by Phase 9 endurance evidence",
    ):
        assert expected in handoff
