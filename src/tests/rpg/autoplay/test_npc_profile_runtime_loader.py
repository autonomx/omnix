import json

from tests.rpg.autoplay.npc_profile_runtime_loader import (
    load_profiles_into_row_runtime,
    npc_ids_for_profile_loading,
    summarize_profile_loads,
)


def test_npc_ids_for_profile_loading_uses_present_npcs_canonicalized():
    ids = npc_ids_for_profile_loading(
        {
            "scene": {"nearby_npcs": ["npc:bran"]},
            "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
        }
    )

    assert ids == ["Bran"]


def test_load_profiles_into_row_runtime_attaches_loaded_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("RPG_NPC_PROFILE_ROOT", str(tmp_path))
    (tmp_path / "bran.json").write_text(
        json.dumps(
            {
                "format_version": "npc_evolution_profile_v1",
                "npc_id": "Bran",
                "evolution": {
                    "arc_stage": "trusting",
                    "axes": {"trust": 4},
                    "memories": [],
                    "future_hooks": [],
                    "signals_applied": [],
                },
            }
        ),
        encoding="utf-8",
    )
    row = {}

    result = load_profiles_into_row_runtime(
        row=row,
        simulation_state={
            "scene": {"nearby_npcs": ["Bran"]},
            "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
        },
    )

    assert result["loaded_count"] == 1
    assert row["runtime_state"]["npc_evolution"]["loaded_profiles"]["Bran"]["profile"]["arc_stage"] == "trusting"


def test_load_profiles_into_row_runtime_preserves_deferred_advisory_state(tmp_path, monkeypatch):
    monkeypatch.setenv("RPG_NPC_PROFILE_ROOT", str(tmp_path))
    (tmp_path / "bran.json").write_text(
        json.dumps(
            {
                "format_version": "npc_evolution_profile_v1",
                "npc_id": "Bran",
                "evolution": {
                    "arc_stage": "trusting",
                    "axes": {"trust": 4},
                    "memories": [],
                    "future_hooks": [],
                    "signals_applied": [],
                },
            }
        ),
        encoding="utf-8",
    )
    row = {
        "runtime_state": {
            "deferred_advisory": {
                "candidates": [
                    {
                        "candidate_id": "adv:1:relationship_delta:a",
                        "kind": "relationship_delta",
                        "turn_index": 1,
                        "status": "pending",
                    }
                ],
                "accepted": [],
                "rejected": [],
            }
        }
    }

    result = load_profiles_into_row_runtime(
        row=row,
        simulation_state={
            "scene": {"nearby_npcs": ["Bran"]},
            "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
        },
    )

    assert result["loaded_count"] == 1
    assert row["runtime_state"]["npc_evolution"]["loaded_profiles"]["Bran"]["profile"]["arc_stage"] == "trusting"
    assert row["runtime_state"]["deferred_advisory"]["candidates"][0]["candidate_id"] == "adv:1:relationship_delta:a"


def test_summarize_profile_loads():
    summary = summarize_profile_loads(
        [
            {
                "npc_profile_load_result": {
                    "loaded": {"Bran": {"profile": {}}},
                    "missing": [],
                    "errors": [],
                }
            }
        ]
    )

    assert summary["ok"] is True
    assert summary["turns_with_profiles"] == 1
    assert summary["loaded_npc_ids"] == ["Bran"]


def test_summarize_profile_loads_reads_prebackground_profile_load_result():
    summary = summarize_profile_loads(
        [
            {
                "prebackground_profile_load_result": {
                    "loaded": {"Bran": {"profile": {}}},
                    "missing": [],
                    "errors": [],
                }
            }
        ]
    )

    assert summary["ok"] is True
    assert summary["turns_with_profiles"] == 1
    assert summary["loaded_npc_ids"] == ["Bran"]