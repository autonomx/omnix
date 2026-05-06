from app.rpg.npc_evolution.target_grounding import ground_projection_target


def test_ground_projection_explicit_role_alias_to_present_npc():
    projection = {
        "kind": "future_hook",
        "payload": {
            "target": "innkeeper",
            "summary": "The innkeeper may become guarded.",
        },
    }
    grounded, result = ground_projection_target(
        projection=projection,
        simulation_state={
            "scene": {"nearby_npcs": ["Bran"]},
            "npc_progression_state": {
                "npcs": {"Bran": {"name": "Bran", "role": "innkeeper"}}
            },
        },
    )

    assert result["grounded"] is True
    assert result["npc_id"] == "Bran"
    assert result["reason"] == "explicit_role_alias"
    assert grounded["payload"]["target"] == "Bran"


def test_ground_projection_name_mentioned_in_summary():
    grounded, result = ground_projection_target(
        projection={
            "kind": "memory",
            "payload": {
                "owner": "Player",
                "summary": "Bran remembers the player asking about the mill.",
            },
        },
        simulation_state={
            "scene": {"nearby_npcs": ["Bran", "Mira"]},
            "npc_progression_state": {
                "npcs": {
                    "Bran": {"name": "Bran", "role": "innkeeper"},
                    "Mira": {"name": "Mira", "role": "scout"},
                }
            },
        },
    )

    assert result["grounded"] is True
    assert result["npc_id"] == "Bran"
    assert result["reason"] == "name_mentioned_in_projection_text"
    assert grounded["payload"]["target"] == "Bran"


def test_ground_projection_single_present_npc():
    grounded, result = ground_projection_target(
        projection={
            "kind": "semantic_intent",
            "payload": {
                "intent": "ask",
                "summary": "The player asks a direct question.",
            },
        },
        simulation_state={
            "scene": {"nearby_npcs": ["Bran"]},
            "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
        },
    )

    assert result["grounded"] is True
    assert result["npc_id"] == "Bran"
    assert result["reason"] == "single_present_npc"


def test_ground_projection_refuses_ambiguous_multi_npc_context():
    grounded, result = ground_projection_target(
        projection={
            "kind": "future_hook",
            "payload": {"summary": "Someone may react later."},
        },
        simulation_state={
            "scene": {"nearby_npcs": ["Bran", "Mira"]},
            "npc_progression_state": {
                "npcs": {
                    "Bran": {"name": "Bran"},
                    "Mira": {"name": "Mira"},
                }
            },
        },
    )

    assert result["grounded"] is False
    assert result["reason"] == "no_deterministic_target"
    assert "target" not in grounded["payload"]


def test_ground_projection_canonicalizes_prefixed_present_npc_id():
    grounded, result = ground_projection_target(
        projection={
            "kind": "semantic_intent",
            "payload": {
                "summary": "The player asks a direct question.",
            },
        },
        simulation_state={
            "scene": {"nearby_npcs": ["npc:bran"]},
            "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
        },
    )

    assert result["grounded"] is True
    assert result["npc_id"] == "Bran"
    assert grounded["payload"]["target"] == "Bran"