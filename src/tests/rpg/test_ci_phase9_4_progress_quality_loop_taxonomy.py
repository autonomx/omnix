from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "docs" / "plans" / "rpg_phase9_4_progress_quality_loop_taxonomy.md"
BASELINE = ROOT / "docs" / "plans" / "rpg_phase9_1_endurance_baseline.md"
PHASE9_3_NOTE = ROOT / "docs" / "plans" / "rpg_phase9_3_completion_note.md"
PHASE9_2_GATE = ROOT / "src" / "tests" / "rpg" / "test_ci_phase9_2_completion_note.py"


def test_phase9_4_progress_quality_doc_records_required_categories():
    doc = DOC.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.4 records the deterministic progress-quality loop evidence envelope",
        "progress_quality_failure",
        "turn_execution_failure",
        "operator_evidence_gap",
        "Progress-quality failures must not be collapsed into generic turn execution failures",
        "false progress",
        "repeated no-op loops",
        "Phase 9.5 — endurance performance/evidence envelope.",
    ):
        assert expected in doc


def test_phase9_4_progress_quality_taxonomy_stays_aligned_with_phase9_baseline():
    baseline = BASELINE.read_text(encoding="utf-8")
    previous_note = PHASE9_3_NOTE.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    for category in (
        "progress_quality_failure",
        "turn_execution_failure",
        "operator_evidence_gap",
    ):
        assert category in baseline
        assert category in doc
    assert "Phase 9.4 — endurance progress-quality loop taxonomy guard" in previous_note
    assert "Phase 9.5 — endurance performance/evidence envelope." in doc


def test_phase9_4_progress_quality_classification_rules_preserve_runtime_authority():
    doc = DOC.read_text(encoding="utf-8")
    for expected in (
        "repeatedly reports no objective, quest, travel, combat, party, economy, or world-state movement",
        "rejected, invalid, or non-player-turn actions are counted as successful state changes",
        "turn crashes or cannot return a valid runtime result",
        "operator_evidence_gap",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in doc


def test_phase9_4_progress_quality_boundary_is_provider_free():
    doc = DOC.read_text(encoding="utf-8")
    forbidden = (
        "OpenAI API",
        "Anthropic API",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "LM Studio server",
    )
    for value in forbidden:
        assert value not in doc
    for expected in (
        "must not add:",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 1000-turn CI execution",
        "gameplay mutation",
    ):
        assert expected in doc


def test_phase9_4_is_covered_by_existing_architecture_gate_bridge():
    bridge = PHASE9_2_GATE.read_text(encoding="utf-8")
    for expected in (
        "PHASE9_4",
        "rpg_phase9_4_progress_quality_loop_taxonomy.md",
        "Phase 9.4 Progress-Quality Loop Taxonomy Guard",
        "progress_quality_failure",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in bridge
