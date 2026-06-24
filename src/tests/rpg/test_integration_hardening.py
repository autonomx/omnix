from __future__ import annotations

from app.rpg.integration_hardening import (
    Phase16IntegrationInput,
    build_phase16_integration_report,
    strict_validate_snapshot,
    strict_validate_world_pack,
)
from app.rpg.replay_contracts import ReplaySnapshot
from app.rpg.world_director import DirectorState, StoryArc
from app.rpg.world_packs import LoreEntry, ModOverlay, WorldPack


def _complete_snapshot() -> ReplaySnapshot:
    return ReplaySnapshot(
        "turn-1",
        1,
        42,
        counters={"rng": 1},
        state={
            "world": {},
            "player": {},
            "party": {},
            "npcs": {},
            "quests": {},
            "map": {},
            "inventory": {},
            "combat": {},
            "memory": {},
        },
    )


def _valid_pack() -> WorldPack:
    return WorldPack(
        "rustlands",
        "Rustlands",
        regions=("vance",),
        lore=(LoreEntry("vance", "Vance", "A scarred city.", "world"),),
        overlays=(ModOverlay("ration", "item", {"item_id": "ration", "price_copper": 5}),),
    )


def test_phase16_report_composes_foundation_outputs() -> None:
    report = build_phase16_integration_report(
        Phase16IntegrationInput(
            narration="You count your pack and confirm the ration is still there.",
            action_kind="inventory",
            state_facts={"inventory": ["ration"]},
            snapshot=_complete_snapshot(),
            world_pack=_valid_pack(),
            director_state=DirectorState(arcs=(StoryArc("bandits", "Bandit Trail", threat="follow the tracks"),)),
            valid_actions=("check journal", "travel north"),
        )
    ).as_dict()

    assert report["fast_action"]["requires_heavy_llm"] is False
    assert "simulation_resolution" in report["path_report"]["blocking_tasks"]
    assert report["replay_issues"] == []
    assert report["world_pack_issues"] == []
    assert report["readiness_issues"] == []
    assert report["prompt_profiles"][0]["status"] == "phase16_audit"


def test_phase16_report_requests_safe_rewrite_without_state_mutation() -> None:
    report = build_phase16_integration_report(
        Phase16IntegrationInput(
            narration="You can't shake the feeling. You can't shake the feeling.",
            action_kind="look",
            state_facts={"location": "Rusty Flagon"},
            snapshot=_complete_snapshot(),
            world_pack=_valid_pack(),
            director_state=DirectorState(),
            valid_actions=("look",),
        )
    ).as_dict()

    assert "narration_rewrite_required" in report["readiness_issues"]
    assert report["rewrite_contract"]["rewrite_requested"] is True
    assert report["rewrite_contract"]["state_facts"] == {"location": "Rusty Flagon"}


def test_strict_snapshot_requires_full_runtime_state_groups() -> None:
    snapshot = ReplaySnapshot(
        "partial",
        1,
        7,
        counters={},
        state={"world": {}, "player": {}, "quests": {}, "map": {}, "inventory": {}},
    )

    issues = strict_validate_snapshot(snapshot)

    assert "missing_state:party" in issues
    assert "missing_state:npcs" in issues
    assert "missing_state:combat" in issues
    assert "missing_state:memory" in issues
    assert "missing_rng_counters" in issues


def test_strict_world_pack_rejects_nested_forbidden_overlay_keys() -> None:
    pack = WorldPack(
        "bad",
        "Bad Pack",
        regions=("vance",),
        overlays=(ModOverlay("bad-overlay", "quest_hook", {"nested": {"currency": 10}}),),
    )

    assert "forbidden_overlay_path:bad-overlay:payload.nested.currency" in strict_validate_world_pack(pack)
