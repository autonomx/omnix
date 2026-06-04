from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "docs" / "plans" / "rpg_phase9_5_performance_evidence_envelope.md"
BASELINE = ROOT / "docs" / "plans" / "rpg_phase9_1_endurance_baseline.md"
ARTIFACT = ROOT / "docs" / "plans" / "rpg_phase9_2_endurance_artifact_contract.md"
PROGRESS = ROOT / "docs" / "plans" / "rpg_phase9_4_progress_quality_loop_taxonomy.md"
PHASE9_2_GATE = ROOT / "src" / "tests" / "rpg" / "test_ci_phase9_2_completion_note.py"

REQUIRED_PERFORMANCE_LABELS = (
    "blocking_turn_time_ms",
    "human_equivalent_turn_time_ms",
    "autoplay_wall_clock_ms",
    "final_drain_ms",
    "background_jobs_started",
    "background_jobs_completed",
    "background_jobs_pending_at_shutdown",
    "production_resource_limits",
    "performance_budget_failure",
    "operator_evidence_gap",
)


def test_phase9_5_performance_doc_records_required_categories_and_labels():
    doc = DOC.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.5 records the deterministic performance evidence envelope",
        "performance_budget_failure",
        "operator_evidence_gap",
        "progress_quality_failure",
        "blocking or human-equivalent turn time",
        "autoplay wall-clock time",
        "final drain timing and background job drain behavior",
        "CI source guards may verify",
        "do not prove live 1000-turn performance",
        "Phase 9.6 — targeted endurance hardening from concrete evidence.",
    ):
        assert expected in doc
    for label in REQUIRED_PERFORMANCE_LABELS:
        assert f"`{label}`" in doc


def test_phase9_5_performance_taxonomy_stays_aligned_with_prior_phase9_docs():
    baseline = BASELINE.read_text(encoding="utf-8")
    artifact = ARTIFACT.read_text(encoding="utf-8")
    progress = PROGRESS.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    for category in (
        "performance_budget_failure",
        "operator_evidence_gap",
        "progress_quality_failure",
    ):
        assert category in baseline
        assert category in doc
    assert "autoplay-summary.json" in artifact
    assert "autoplay-transcript.json" in artifact
    assert "autoplay-campaign-results.zip" in artifact
    assert "progress_quality_failure" in progress
    assert "Phase 9.5 — endurance performance/evidence envelope" in progress


def test_phase9_5_performance_classification_rules_preserve_runtime_authority():
    doc = DOC.read_text(encoding="utf-8")
    for expected in (
        "If blocking or human-equivalent turn time exceeds the current budget",
        "If autoplay wall-clock, final drain, or background job drain behavior exceeds the current budget",
        "If timing evidence is absent because no live/provider or operator artifact was supplied",
        "repeated no-op loops or false progress",
        "operator_evidence_gap",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in doc


def test_phase9_5_performance_boundary_is_provider_free():
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


def test_phase9_5_is_covered_by_existing_architecture_gate_bridge():
    bridge = PHASE9_2_GATE.read_text(encoding="utf-8")
    for expected in (
        "PHASE9_5",
        "rpg_phase9_5_performance_evidence_envelope.md",
        "Phase 9.5 Performance Evidence Envelope",
        "performance_budget_failure",
        "operator_evidence_gap",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in bridge
