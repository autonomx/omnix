from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "docs" / "plans" / "rpg_phase9_3_checkpoint_replay_taxonomy.md"
BASELINE = ROOT / "docs" / "plans" / "rpg_phase9_1_endurance_baseline.md"
ARTIFACT = ROOT / "docs" / "plans" / "rpg_phase9_2_endurance_artifact_contract.md"
PHASE9_2_GATE = ROOT / "src" / "tests" / "rpg" / "test_ci_phase9_2_completion_note.py"


def test_phase9_3_checkpoint_replay_taxonomy_doc_records_required_categories():
    doc = DOC.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.3 records the deterministic checkpoint and replay evidence envelope",
        "save_load_checkpoint_failure",
        "artifact_contract_failure",
        "operator_evidence_gap",
        "Checkpoint/replay failures must not be collapsed into generic turn execution failures",
        "If a save/load checkpoint hook fails, classify the result as `save_load_checkpoint_failure`.",
        "If checkpoint/replay evidence requires a live/provider or operator environment",
        "package/disk replay",
        "Phase 9.4 — endurance progress-quality loop taxonomy guard.",
    ):
        assert expected in doc


def test_phase9_3_taxonomy_stays_aligned_with_phase9_baseline_and_artifact_contract():
    baseline = BASELINE.read_text(encoding="utf-8")
    artifact = ARTIFACT.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    for category in (
        "save_load_checkpoint_failure",
        "artifact_contract_failure",
        "operator_evidence_gap",
    ):
        assert category in baseline
        assert category in doc
    assert "artifact_contract_failure" in artifact
    assert "operator_evidence_gap" in artifact
    assert "autoplay-summary.json" in artifact
    assert "autoplay-transcript.json" in artifact
    assert "autoplay-campaign-results.zip" in artifact


def test_phase9_3_checkpoint_replay_boundary_is_provider_free():
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
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in doc


def test_phase9_3_is_covered_by_existing_architecture_gate_bridge():
    bridge = PHASE9_2_GATE.read_text(encoding="utf-8")
    for expected in (
        "PHASE9_3",
        "rpg_phase9_3_checkpoint_replay_taxonomy.md",
        "Phase 9.3 Checkpoint and Replay Taxonomy Guard",
        "save_load_checkpoint_failure",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in bridge
