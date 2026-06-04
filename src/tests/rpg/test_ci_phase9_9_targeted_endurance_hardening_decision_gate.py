from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase9_9_targeted_endurance_hardening_decision_gate.md"

EVIDENCE_SOURCES = (
    "autoplay-summary.json",
    "autoplay-transcript.json",
    "autoplay-campaign-results.zip",
    "save/load checkpoint artifacts",
    "package/disk replay artifacts",
    "operator evidence summary",
    "timing/performance evidence summary",
    "long-run continuity review",
    "progress-quality review",
    "CI failure logs with source-backed failure output",
)

DECISION_STATES = (
    "operator_evidence_gap",
    "documentation_only_followup",
    "harness_contract_fix",
    "artifact_contract_fix",
    "checkpoint_replay_fix",
    "progress_quality_fix",
    "performance_budget_fix",
    "world_continuity_fix",
    "provider_boundary_fix",
    "runtime_authority_fix",
)

DECISION_RULES = (
    "Use `operator_evidence_gap` when no concrete evidence is attached.",
    "Use `documentation_only_followup` when evidence identifies a documentation, runbook, or taxonomy clarification",
    "Use `harness_contract_fix` only when evidence shows a harness entrypoint",
    "Use `artifact_contract_fix` only when evidence shows malformed, missing, or inconsistent summary, transcript, ZIP, or artifact path contracts.",
    "Use `checkpoint_replay_fix` only when evidence shows failed save/load checkpoint validation, replay mismatch, or package/disk replay mismatch.",
    "Use `progress_quality_fix` only when evidence shows weak progress, false progress, repeated no-op loops, invalid action success claims",
    "Use `performance_budget_fix` only when evidence shows timing, final-drain, background-job, or resource-budget failures.",
    "Use `world_continuity_fix` only when evidence shows continuity drift across combat, NPC memory, party, travel, time, weather, quest, reward, economy, inventory, save/load, or replay state.",
    "Use `provider_boundary_fix` only when evidence shows unsupported provider-facing state claims",
    "Use `runtime_authority_fix` only when evidence shows runtime wrapper authority was bypassed",
)


def test_phase9_9_records_scope_and_no_evidence_decision():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.9 records the decision gate",
        "source/test/documentation only",
        "does not run a live/provider 100-turn or 1000-turn campaign in CI",
        "does not change runtime behavior",
        "No live/operator artifact bundle was attached for this slice",
        "must classify the current hardening decision as `operator_evidence_gap`",
        "Phase 10 — production packaging, stability, and release readiness",
    ):
        assert expected in plan


def test_phase9_9_requires_concrete_evidence_before_hardening():
    plan = PLAN.read_text(encoding="utf-8")
    for evidence in EVIDENCE_SOURCES:
        assert evidence in plan
    for expected in (
        "must cite at least one concrete evidence source before changing runtime",
        "harness",
        "gameplay",
        "save/load",
        "replay",
        "UI",
        "provider-boundary code",
    ):
        assert expected in plan


def test_phase9_9_decision_states_and_rules_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for state in DECISION_STATES:
        assert state in plan
    for rule in DECISION_RULES:
        assert rule in plan


def test_phase9_9_no_evidence_allows_only_docs_and_guards():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "decision: `operator_evidence_gap`",
        "allowed changes: documentation and deterministic source guards only",
        "disallowed changes: runtime behavior, gameplay mutation, UI authority, provider calls, LLM calls, live endurance execution in CI, and command execution path changes",
        "no attached live/operator artifact bundle",
        "no attached checkpoint/replay package",
        "no attached continuity review",
        "no attached performance evidence",
        "no failing CI log",
    ):
        assert expected in plan


def test_phase9_9_boundary_is_provider_free_and_non_mutating():
    plan = PLAN.read_text(encoding="utf-8")
    forbidden = (
        "OpenAI API",
        "Anthropic API",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "LM Studio server",
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
        "command execution paths outside existing runtime validation",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in plan
