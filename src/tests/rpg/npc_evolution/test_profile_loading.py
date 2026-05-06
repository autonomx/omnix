import json

from app.rpg.npc_evolution.profile_store import (
    attach_loaded_profiles_to_runtime_state,
    load_npc_evolution_profiles_for_runtime,
)


def test_load_npc_evolution_profiles_for_runtime_loads_bounded_projection(tmp_path):
    profile_path = tmp_path / "bran.json"
    profile_path.write_text(
        json.dumps(
            {
                "format_version": "npc_evolution_profile_v1",
                "npc_id": "Bran",
                "evolution": {
                    "arc_stage": "trusting",
                    "axes": {"trust": 4},
                    "memories": [
                        {"signal_id": f"m{i}", "summary": f"memory {i}"}
                        for i in range(12)
                    ],
                    "future_hooks": [
                        {"signal_id": f"h{i}", "summary": f"hook {i}"}
                        for i in range(12)
                    ],
                    "signals_applied": [{"signal_id": "s1"}],
                },
            }
        ),
        encoding="utf-8",
    )

    result = load_npc_evolution_profiles_for_runtime(npc_ids=["Bran"], root=tmp_path)

    assert result["ok"] is True
    assert result["loaded_count"] == 1
    projection = result["loaded"]["Bran"]["profile"]
    assert projection["arc_stage"] == "trusting"
    assert projection["axes"]["trust"] == 4
    assert len(projection["memories"]) == 8
    assert len(projection["future_hooks"]) == 8


def test_attach_loaded_profiles_to_runtime_state():
    runtime_state = {}
    load_result = {
        "ok": True,
        "root": "x",
        "loaded_count": 1,
        "missing_count": 0,
        "loaded": {
            "Bran": {
                "path": "bran.json",
                "profile": {"npc_id": "Bran", "arc_stage": "trusting"},
            }
        },
        "missing": [],
        "errors": [],
    }

    updated = attach_loaded_profiles_to_runtime_state(
        runtime_state=runtime_state,
        load_result=load_result,
    )

    assert updated == runtime_state
    assert runtime_state["npc_evolution"]["loaded_profiles"] == load_result["loaded"]