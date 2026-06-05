from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_4_player_safe_error_handling_evidence_envelope.md"

SECTIONS = (
    "startup_error_evidence",
    "configuration_error_evidence",
    "provider_error_evidence",
    "save_load_error_evidence",
    "persistence_error_evidence",
    "network_error_evidence",
    "resource_error_evidence",
    "unknown_error_evidence",
    "safe_message_evidence",
    "recovery_action_evidence",
    "diagnostic_reference_evidence",
    "internal_detail_separation_evidence",
    "support_bundle_evidence",
    "player_safe_error_classification",
)

CLASSIFICATIONS = (
    "player_safe_error_evidence_gap",
    "startup_error_message_gap",
    "configuration_error_message_gap",
    "provider_error_message_gap",
    "save_load_error_message_gap",
    "persistence_error_message_gap",
    "network_error_message_gap",
    "resource_error_message_gap",
    "unknown_error_message_gap",
    "recovery_action_gap",
    "diagnostic_reference_gap",
    "internal_detail_leak_gap",
    "support_bundle_gap",
    "player_safe_error_ready",
)


def test_phase10_4_records_scope_and_required_sections():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.4 records the evidence envelope",
        "source/test/documentation only",
        "does not build a release package",
        "does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness",
        "Phase 10.5 — release candidate packaging contract",
    ):
        assert expected in plan
    for section in SECTIONS:
        assert section in plan


def test_phase10_4_required_fields_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "git SHA and branch",
        "operating system and launch context",
        "triggered error category",
        "player-facing message text",
        "recovery action text",
        "support or diagnostic reference shown to the player",
        "internal diagnostic location and artifact path",
        "log correlation identifier if present",
        "provider keys, tokens, secrets, local absolute paths, and raw stack traces are not exposed to the player",
        "internal diagnostics remain available to operators",
    ):
        assert expected in plan


def test_phase10_4_classifications_and_rules_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for classification in CLASSIFICATIONS:
        assert classification in plan
    for expected in (
        "Use `player_safe_error_evidence_gap` when no concrete player-safe error handling evidence is attached.",
        "Use a category-specific `*_error_message_gap` when the corresponding failure category lacks a safe player-facing message.",
        "Use `recovery_action_gap` when the player-facing message does not include a reasonable next action or recovery instruction.",
        "Use `internal_detail_leak_gap` when player-facing output exposes provider keys, tokens, secrets, raw stack traces, unredacted local absolute paths, or internal debug details beyond the intended diagnostic scope.",
        "Use `player_safe_error_ready` only when concrete evidence covers startup, configuration, provider, save/load, persistence, network, resource, and unknown failures with safe messages, recovery actions, diagnostic references, internal-detail separation, and usable support bundle guidance without blocking gaps.",
    ):
        assert expected in plan


def test_phase10_4_no_evidence_maps_to_player_safe_error_gap():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `player_safe_error_evidence_gap`",
        "allowed changes: documentation and deterministic source guards only",
        "disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims",
        "does not attach concrete startup, configuration, provider, save/load, persistence, network, resource, or unknown error evidence",
    ):
        assert expected in plan


def test_phase10_4_boundary_is_provider_free_and_non_mutating():
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
