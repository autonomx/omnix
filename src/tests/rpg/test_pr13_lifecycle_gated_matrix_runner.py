from __future__ import annotations

import zipfile
from types import SimpleNamespace

from tests.rpg import interactive_intent_matrix as matrix
from tests.rpg.interactive_intent_matrix_lifecycle_gate import (
    COMBAT_HP_REPORT_NAME,
    apply_lifecycle_gate,
    build_combat_hp_report,
    matrix_output_zip_path,
    zip_matrix_output_root,
)


def _enemy_action_row(*, turn: int, hp_before: int, hp_after: int) -> dict:
    contract = {
        "schema": "enemy_damage_contract_v1",
        "source": "pr1_6_authoritative_player_combat_hp",
        "metadata_only": False,
        "player_state_mutated": True,
        "damage_applied": hp_before - hp_after,
        "player_hp_before": hp_before,
        "player_hp_after": hp_after,
        "player_damage_pending": False,
        "player_hp_delta": hp_after - hp_before,
        "nonlethal_guard": True,
        "authoritative_player_combat_hp": True,
        "survival_state_mutated": False,
    }
    return {
        "schema": "combat_log_entry_v1",
        "entry_id": f"combat:enemy:{turn}",
        "turn_index": turn,
        "round_index": turn,
        "phase": "enemy_action",
        "actor_id": "enemy:road_bandit",
        "actor_side": "enemy",
        "target_id": "player",
        "target_name": "player",
        "target_side": "player",
        "action_type": "counterattack",
        "hit": True,
        "damage_applied": hp_before - hp_after,
        "target_hp_before": hp_before,
        "target_hp_after": hp_after,
        "player_hp_before": hp_before,
        "player_hp_after": hp_after,
        "player_damage_pending": False,
        "player_hp_delta": hp_after - hp_before,
        "player_state_mutated": True,
        "authoritative_player_combat_hp": True,
        "survival_state_mutated": False,
        "source": "deterministic_enemy_damage_contract_v1",
        "enemy_damage_contract": contract,
    }


def _lifecycle_turn(
    *,
    turn: int,
    before: int,
    after: int,
    defeated: bool = False,
    player_hp_before: int | None = None,
    player_hp_after: int | None = None,
) -> dict:
    damage = before - after
    combat_log = [
        {
            "schema": "combat_log_entry_v1",
            "entry_id": f"combat:test:{turn}",
            "turn_index": turn,
            "round_index": turn,
            "phase": "player_action",
            "actor_id": "player",
            "actor_side": "player",
            "target_id": "enemy:road_bandit",
            "target_name": "bandit",
            "target_side": "enemy",
            "action_type": "attack",
            "hit": damage > 0 or defeated,
            "damage_applied": damage,
            "target_hp_before": before,
            "target_hp_after": after,
            "defeated": defeated,
            "combat_ended": defeated,
            "source": "deterministic_combat_delta_contract_v1",
        }
    ]
    if player_hp_before is not None and player_hp_after is not None:
        combat_log.append(_enemy_action_row(turn=turn, hp_before=player_hp_before, hp_after=player_hp_after))
    lifecycle = {
        "schema": "combat_lifecycle_v1",
        "source": "pr1_combat_lifecycle_foundation",
        "initiative": {
            "schema": "combat_initiative_v1",
            "order": ["player", "enemy:road_bandit"],
            "active_actor_id": "player",
            "next_actor_id": "" if defeated else ("player" if len(combat_log) > 1 else "enemy:road_bandit"),
            "round_index": turn,
            "turn_phase": "combat_complete" if defeated else ("player_turn_ready" if len(combat_log) > 1 else "awaiting_enemy_turn"),
        },
        "enemy_turn": {
            "schema": "enemy_turn_skeleton_v1",
            "pending": not defeated and len(combat_log) == 1,
            "resolved": len(combat_log) > 1,
            "actor_id": "" if defeated else "enemy:road_bandit",
            "reason": "combat_ended" if defeated else "test_fixture",
        },
        "combat_log": combat_log,
        "progression_hooks": {
            "schema": "combat_progression_hooks_v1",
            "xp_pending": defeated,
            "loot_pending": defeated,
            "resolved": False,
            "reason": "placeholder_for_phase1_xp_loot_resolution",
        },
    }
    if player_hp_before is not None and player_hp_after is not None:
        lifecycle["player_combat_hp"] = {
            "before": player_hp_before,
            "after": player_hp_after,
            "delta": player_hp_after - player_hp_before,
            "authoritative": True,
            "survival_state_mutated": False,
        }
    return {"turn_index": turn, "raw_result": {"combat_lifecycle": lifecycle}}


def _matrix_result(turns: list[dict], *, passed: int = 8) -> dict:
    return {
        "summary": {"passed": passed, "failed": [], "output_root": ""},
        "results": [
            {
                "scenario": SimpleNamespace(scenario_id=matrix.COMBAT_MATRIX_SCENARIO_ID),
                "result": {"turns": turns},
                "validation": {"ok": True, "failures": []},
            }
        ],
    }


def _resolved_combat_turns() -> list[dict]:
    return [
        _lifecycle_turn(turn=2, before=4, after=3, player_hp_before=10, player_hp_after=9),
        _lifecycle_turn(turn=3, before=3, after=2, player_hp_before=9, player_hp_after=8),
        _lifecycle_turn(turn=4, before=2, after=1, player_hp_before=8, player_hp_after=7),
        _lifecycle_turn(turn=5, before=1, after=0, defeated=True),
    ]


def test_pr13_lifecycle_gate_passes_valid_combat_matrix_result():
    result = apply_lifecycle_gate(_matrix_result(_resolved_combat_turns()))

    gate = result["summary"]["combat_lifecycle_gate"]
    assert gate["ok"] is True
    assert gate["failures"] == []
    assert result["summary"]["failed"] == []
    assert result["summary"]["passed"] == 8


def test_pr13_lifecycle_gate_marks_matrix_failed_when_lifecycle_missing():
    result = apply_lifecycle_gate(_matrix_result([{"turn_index": 2, "raw_result": {}}]))

    gate = result["summary"]["combat_lifecycle_gate"]
    assert gate["ok"] is False
    assert any("missing combat_lifecycle_v1" in failure for failure in gate["failures"])
    assert result["summary"]["failed"]
    assert result["summary"]["passed"] == 7


def test_pr13_lifecycle_gate_preserves_non_combat_matrix_results():
    result = {
        "summary": {"passed": 8, "failed": [], "output_root": ""},
        "results": [
            {
                "scenario": SimpleNamespace(scenario_id="commerce_food_purchase"),
                "result": {"turns": [{"turn_index": 1}]},
                "validation": {"ok": True, "failures": []},
            }
        ],
    }

    gated = apply_lifecycle_gate(result)

    assert gated["summary"]["combat_lifecycle_gate"]["ok"] is True
    assert gated["summary"]["combat_lifecycle_gate"]["failures"] == []
    assert gated["summary"]["failed"] == []
    assert gated["summary"]["passed"] == 8


def test_pr17_builds_combat_hp_report_from_matrix_result():
    report = build_combat_hp_report(_matrix_result(_resolved_combat_turns()))

    assert report["format_version"] == "interactive_intent_matrix_combat_hp_report_v1"
    assert report["row_count"] == 4
    assert report["player_hp_sequence"] == [
        {"turn_index": 2, "before": 10, "after": 9, "delta": -1},
        {"turn_index": 3, "before": 9, "after": 8, "delta": -1},
        {"turn_index": 4, "before": 8, "after": 7, "delta": -1},
    ]
    assert report["enemy_hp_sequence"][-1] == {"turn_index": 5, "before": 1, "after": 0, "damage": 1}
    assert report["rows"][0]["enemy_action"]["player_state_mutated"] is True
    assert report["rows"][0]["enemy_action"]["survival_state_mutated"] is False


def test_pr132_zips_matrix_output_root_next_to_output_directory(tmp_path):
    output_root = tmp_path / "interactive-intent-matrix"
    scenario_dir = output_root / "combat_basic_attack"
    scenario_dir.mkdir(parents=True)
    (output_root / "interactive-intent-matrix-summary.json").write_text("{}", encoding="utf-8")
    (output_root / COMBAT_HP_REPORT_NAME).write_text("{}", encoding="utf-8")
    (scenario_dir / "interactive-transcript.json").write_text("[]", encoding="utf-8")

    zip_path = zip_matrix_output_root(output_root)

    assert zip_path == tmp_path / "interactive-intent-matrix.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "interactive-intent-matrix-summary.json" in names
    assert COMBAT_HP_REPORT_NAME in names
    assert "combat_basic_attack/interactive-transcript.json" in names


def test_pr133_matrix_output_zip_path_is_known_before_zip_creation(tmp_path):
    output_root = tmp_path / "interactive-intent-matrix"

    assert matrix_output_zip_path(output_root) == tmp_path / "interactive-intent-matrix.zip"
