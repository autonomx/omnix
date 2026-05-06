import json

from app.rpg.npc_evolution.profile_store import (
    load_npc_profile,
    persist_npc_evolution_profiles,
)


def test_persist_npc_evolution_profiles_writes_bounded_profile(tmp_path):
    runtime_state = {
        "npc_evolution": {
            "signals": [
                {
                    "signal_id": "s1",
                    "npc_id": "Bran",
                    "kind": "memory",
                    "turn_index": 2,
                    "summary": "Bran remembers the player.",
                    "source": "deferred_advisory_promotion",
                    "consumed": True,
                }
            ],
            "arcs": {
                "Bran": {
                    "npc_id": "Bran",
                    "arc_stage": "stable",
                    "axes": {"trust": 1},
                    "memories": [
                        {
                            "signal_id": "s1",
                            "summary": "Bran remembers the player.",
                        }
                    ],
                    "future_hooks": [],
                    "world_signals": [],
                    "semantic_intents": [],
                    "milestones": [],
                }
            },
        }
    }

    result = persist_npc_evolution_profiles(runtime_state=runtime_state, root=tmp_path)

    assert result["ok"] is True
    assert result["written_count"] == 1

    profile_path = tmp_path / "bran.json"
    assert profile_path.exists()
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    assert data["npc_id"] == "Bran"
    assert data["evolution"]["axes"]["trust"] == 1
    assert data["evolution"]["signals_applied"][0]["signal_id"] == "s1"


def test_persist_npc_evolution_profiles_is_idempotent(tmp_path):
    runtime_state = {
        "npc_evolution": {
            "signals": [
                {
                    "signal_id": "s1",
                    "npc_id": "Bran",
                    "kind": "future_hook",
                    "turn_index": 2,
                    "summary": "Bran may answer later.",
                    "source": "deferred_advisory_promotion",
                    "consumed": True,
                }
            ],
            "arcs": {
                "Bran": {
                    "npc_id": "Bran",
                    "arc_stage": "stable",
                    "axes": {},
                    "future_hooks": [{"signal_id": "s1", "summary": "Bran may answer later."}],
                }
            },
        }
    }

    persist_npc_evolution_profiles(runtime_state=runtime_state, root=tmp_path)
    persist_npc_evolution_profiles(runtime_state=runtime_state, root=tmp_path)
    profile = load_npc_profile("Bran", root=tmp_path)

    assert len(profile["evolution"]["future_hooks"]) == 1
    assert len(profile["evolution"]["signals_applied"]) == 1