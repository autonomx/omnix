from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_3_persistence_diagnostics_evidence_envelope.md"

PERSISTENCE_SECTIONS = (
    "save_path_evidence",
    "session_path_evidence",
    "data_path_evidence",
    "save_load_roundtrip_evidence",
    "replay_artifact_evidence",
    "package_disk_artifact_evidence",
    "artifact_bundle_members",
    "migration_compatibility_evidence",
    "backup_recovery_evidence",
    "corruption_recovery_evidence",
    "persistence_classification",
)

DIAGNOSTICS_SECTIONS = (
    "log_path_evidence",
    "error_report_evidence",
    "diagnostic_bundle_evidence",
    "operator_collection_steps",
    "failure_reproduction_steps",
    "redaction_sensitive_data_evidence",
    "player_safe_internal_separation",
    "diagnostics_classification",
)

CLASSIFICATIONS = (
    "persistence_diagnostics_evidence_gap",
    "save_path_gap",
    "session_path_gap",
    "data_path_gap",
    "save_load_roundtrip_gap",
    "replay_artifact_gap",
    "package_disk_artifact_gap",
    "artifact_bundle_gap",
    "migration_compatibility_gap",
    "backup_recovery_gap",
    "corruption_recovery_gap",
    "diagnostic_log_gap",
    "diagnostic_bundle_gap",
    "reproduction_steps_gap",
    "redaction_gap",
    "player_safe_internal_separation_gap",
    "persistence_diagnostics_ready",
)


def test_phase10_3_records_scope_and_required_sections():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.3 records the evidence envelope",
        "source/test/documentation only",
        "does not build a release package",
        "does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness",
        "Phase 10.4 — player-safe error handling evidence envelope",
    ):
        assert expected in plan
    for section in PERSISTENCE_SECTIONS + DIAGNOSTICS_SECTIONS:
        assert section in plan


def test_phase10_3_required_fields_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "git SHA and branch",
        "operating system and working directory",
        "save, session, data, report, and replay directory paths",
        "save/load roundtrip command or manual steps",
        "replay/package artifact paths and bundle members",
        "migration or schema compatibility notes",
        "backup, rollback, and recovery instructions",
        "corruption or missing-file recovery behavior",
        "log file paths and retention expectations",
        "error report paths and diagnostic bundle paths",
        "operator diagnostic collection steps",
        "failure reproduction steps",
        "sensitive-data redaction expectations",
        "separation between player-safe messages and internal diagnostics",
    ):
        assert expected in plan


def test_phase10_3_classifications_and_rules_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for classification in CLASSIFICATIONS:
        assert classification in plan
    for expected in (
        "Use `persistence_diagnostics_evidence_gap` when no concrete persistence or diagnostic artifact evidence is attached.",
        "Use `save_load_roundtrip_gap` when save/load roundtrip evidence is missing, failing, or not reproducible from the recorded steps.",
        "Use `redaction_gap` when diagnostic collection may expose secrets, tokens, provider keys, personal data, or unredacted local paths beyond the intended diagnostic scope.",
        "Use `persistence_diagnostics_ready` only when concrete evidence covers persistence paths, save/load roundtrip, replay/package artifacts, bundle members, migration compatibility, backup/recovery, corruption recovery, diagnostics, reproduction steps, redaction, and player-safe/internal separation without blocking gaps.",
    ):
        assert expected in plan


def test_phase10_3_no_evidence_maps_to_persistence_diagnostics_gap():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `persistence_diagnostics_evidence_gap`",
        "allowed changes: documentation and deterministic source guards only",
        "disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims",
        "does not attach save/load roundtrip evidence",
        "replay/package artifacts",
        "diagnostic bundles",
        "logs",
        "reproduction steps",
        "redaction evidence",
    ):
        assert expected in plan


def test_phase10_3_boundary_is_provider_free_and_non_mutating():
    plan = PLAN.read_text(encoding="utf-8")
    forbidden = (
        "OpenAI API",
        "Anthropic API",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
    )
    for value in forbidden:
        assert value not in plan
    for expected in (
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "external release claims without evidence",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in plan
