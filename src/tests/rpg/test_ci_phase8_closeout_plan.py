from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase8_closeout_plan.md"


def test_phase8_closeout_plan_caps_remaining_phase8_work():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 8 has reached closeout planning after Phase 8.30.",
        "Phase 8 should no longer accept open-ended metadata-only polish slices.",
        "Remaining Phase 8 work is capped at four final slices.",
        "Phase 8.32 — Panel contract inventory and consolidation",
        "Phase 8.33 — Browser smoke coverage for registered panels",
        "Phase 8.34 — UI runtime-authority boundary audit",
        "Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff",
        "Do not add more Phase 8 metadata-only families after Phase 8.31.",
        "move to Phase 9 unless a required gate exposes a concrete blocker",
        "Phase 9 — 1000-turn endurance systems",
    ):
        assert expected in plan


def test_phase8_closeout_plan_preserves_runtime_authority_and_provider_free_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Do not claim full visual/gameplay UI completion",
        "provider-free foundation pass",
        "Do not add provider/LLM calls",
        "gameplay mutation",
        "new command execution paths",
        "command submission still routes through existing runtime validation paths only",
        "Preserve wrapper authority for turn and combat action runtime modules.",
        "remaining UI/product risks are routed forward without blocking endurance work",
    ):
        assert expected in plan
