from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase9_8_long_run_continuity_evidence_envelope.md"

CONTINUITY_CATEGORIES = (
    "combat_continuity",
    "npc_memory_continuity",
    "party_continuity",
    "travel_continuity",
    "time_continuity",
    "weather_continuity",
    "quest_continuity",
    "reward_continuity",
    "economy_inventory_continuity",
    "save_load_continuity",
    "replay_continuity",
    "progress_quality_continuity",
    "provider_boundary_continuity",
    "runtime_authority_continuity",
    "taxonomy_classification",
)

TAXONOMY = (
    "harness_entrypoint_failure",
    "runtime_authority_failure",
    "turn_execution_failure",
    "save_load_checkpoint_failure",
    "artifact_contract_failure",
    "progress_quality_failure",
    "performance_budget_failure",
    "provider_boundary_failure",
    "world_continuity_failure",
    "operator_evidence_gap",
)

DRIFT_RULES = (
    "combat state or reward drift should classify as `world_continuity_failure`",
    "NPC memory, relationship, or persona drift should classify as `world_continuity_failure`",
    "party membership drift should classify as `world_continuity_failure`",
    "travel, location, route, time, season, or weather drift should classify as `world_continuity_failure`",
    "quest, objective, reward, XP, currency, item, or inventory drift should classify as `world_continuity_failure`",
    "save/load or replay mismatch should classify as `save_load_checkpoint_failure`",
    "malformed or missing artifact references should classify as `artifact_contract_failure`",
    "repeated no-op loops, false progress, or invalid action success claims should classify as `progress_quality_failure`",
    "unsupported provider-facing state claims should classify as `provider_boundary_failure` or `runtime_authority_failure`",
)

MISSING_EVIDENCE_RULES = (
    "missing transcript evidence should classify as `operator_evidence_gap`",
    "missing reviewed turn range should classify as `operator_evidence_gap`",
    "missing save/load checkpoint or replay evidence should classify as `operator_evidence_gap`",
    "missing continuity category review notes should classify as `operator_evidence_gap`",
    "missing artifact bundle references should classify as `operator_evidence_gap`",
)


def test_phase9_8_continuity_envelope_records_scope_and_stop_condition():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.8 records the deterministic evidence envelope",
        "source/test/documentation only",
        "does not run a live/provider 100-turn or 1000-turn campaign in CI",
        "does not change runtime behavior",
        "CI source guards can prove that the continuity evidence envelope exists",
        "they do not prove live 1000-turn continuity",
        "Phase 9.9 — targeted endurance hardening from concrete evidence",
    ):
        assert expected in plan


def test_phase9_8_required_continuity_categories_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for category in CONTINUITY_CATEGORIES:
        assert category in plan
    for expected in (
        "run metadata reference",
        "source artifact bundle reference",
        "reviewed turn range",
        "transcript excerpts or row references for each continuity category",
        "starting and ending location state",
        "travel transitions and blocked-route handling",
        "time/day/season/weather observations",
        "combat entry, action, defeat, reward, and exit observations",
        "NPC memory or relationship observations",
        "party join, leave, and membership observations",
        "quest objective, completion, failure, and journal observations",
        "reward, XP, currency, item, and inventory observations",
        "save/load checkpoint artifact references",
        "replay or package/disk replay artifact references",
        "rejected, invalid, or non-player-turn action handling",
        "provider-boundary or unsupported state-claim observations",
    ):
        assert expected in plan


def test_phase9_8_continuity_drift_maps_to_taxonomy_categories():
    plan = PLAN.read_text(encoding="utf-8")
    for rule in DRIFT_RULES:
        assert rule in plan
    for category in TAXONOMY:
        assert category in plan


def test_phase9_8_missing_evidence_maps_to_operator_evidence_gap():
    plan = PLAN.read_text(encoding="utf-8")
    for rule in MISSING_EVIDENCE_RULES:
        assert rule in plan
    for expected in (
        "Do not treat absent continuity evidence as a passing result",
        "Do not infer long-run continuity from CI source guards",
        "If the run completes but continuity evidence is incomplete",
        "classify the gap explicitly as `operator_evidence_gap`",
    ):
        assert expected in plan


def test_phase9_8_boundary_is_provider_free_and_non_mutating():
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
