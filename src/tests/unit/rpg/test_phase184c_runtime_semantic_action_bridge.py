from app.rpg.session import runtime as rt


def _sim_state():
    return {
        "tick": 70,
        "player_state": {
            "location_id": "loc:tavern",
            "nearby_npc_ids": ["npc_bran", "npc_elara"],
            "stats": {"charisma": 12, "intelligence": 10},
            "skills": {"persuasion": {"level": 2}},
        },
        "npc_index": {
            "npc_bran": {
                "id": "npc_bran",
                "name": "Bran the Innkeeper",
                "role": "innkeeper",
                "location_id": "loc:tavern",
            },
            "npc_elara": {
                "id": "npc_elara",
                "name": "Elara the Merchant",
                "role": "merchant",
                "location_id": "loc:tavern",
            },
        },
        "active_interactions": [],
        "event_history": [],
    }


def _runtime_state():
    return {
        "tick": 70,
        "current_scene": {
            "scene_id": "scene:tavern",
            "location_id": "loc:tavern",
            "summary": "A lively tavern scene.",
        },
        "recent_world_event_rows": [],
        "recent_scene_beats": [],
        "world_consequences": [],
        "world_rumors": [],
        "world_pressure": [],
        "location_conditions": [],
        "actor_activities": {},
        "llm_records": [],
        "llm_records_index": {},
    }


def test_compile_and_apply_semantic_action_for_darts():
    sim = _sim_state()
    runtime_state = _runtime_state()
    action = {"action_type": "social_activity", "target_id": "npc_bran"}
    advisory = {
        "action_type": "social_competition",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "activity_label": "darts",
        "target_id": "npc_bran",
        "target_name": "Bran the Innkeeper",
        "visibility": "public",
        "intensity": 1,
        "stakes": 1,
        "social_axes": [{"axis": "camaraderie", "delta": 2}, {"axis": "respect", "delta": 1}],
        "observer_hooks": ["spectacle", "conversation_seed"],
        "scene_impact": "gathers_attention",
        "reason": "Direct public friendly competition.",
    }

    record = rt._compile_semantic_action_record(sim, runtime_state, "I challenge Bran to darts", action, advisory)
    assert record["action_type"] == "social_competition"
    assert record["activity_label"] == "darts"
    assert record["target_id"] == "npc_bran"

    sim2, runtime2 = rt._apply_semantic_action_to_runtime(sim, runtime_state, record)

    assert sim2["active_interactions"]
    assert sim2["active_interactions"][0]["subtype"] == "darts"
    assert runtime2["actor_activities"]["npc_bran"]["kind"] == "player_social_competition"
    assert any("draws local attention" in item.get("summary", "") for item in runtime2["world_consequences"])
    assert any(row.get("source") == "semantic_player_runtime" for row in runtime2["recent_world_event_rows"])
    assert any(beat.get("kind") == "interaction_beat" for beat in runtime2["recent_scene_beats"])


def test_compile_and_apply_semantic_action_appends_simulation_event():
    sim = _sim_state()
    runtime_state = _runtime_state()
    action = {"action_type": "social_activity", "target_id": "npc_bran"}
    advisory = {
        "action_type": "social_competition",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "activity_label": "darts",
        "target_id": "npc_bran",
        "target_name": "Bran the Innkeeper",
        "visibility": "public",
        "intensity": 1,
        "stakes": 1,
        "social_axes": [{"axis": "camaraderie", "delta": 2}],
        "observer_hooks": ["spectacle", "conversation_seed"],
        "scene_impact": "gathers_attention",
        "reason": "Direct public friendly competition.",
    }

    record = rt._compile_semantic_action_record(sim, runtime_state, "I challenge Bran to darts", action, advisory)
    sim2, runtime2 = rt._apply_semantic_action_to_runtime(sim, runtime_state, record)

    assert sim2["event_history"]
    assert sim2["event_history"][-1]["type"] == "player_semantic_action"
    assert sim2["event_history"][-1]["payload"]["activity_label"] == "darts"
    assert runtime2["actor_activities"]["npc_bran"]["kind"] == "player_social_competition"
    assert any(row.get("source") == "semantic_player_runtime" for row in runtime2["recent_world_event_rows"])


def test_target_resolution_supports_role_fallback():
    sim = _sim_state()
    target = rt._find_npc_target_by_name(sim, "I challenge the innkeeper to darts")
    assert target == "npc_bran"


def test_apply_semantic_action_is_idempotent_for_same_record():
    sim = _sim_state()
    runtime_state = _runtime_state()
    action = {"action_type": "social_activity", "target_id": "npc_bran"}
    advisory = {
        "action_type": "social_competition",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "activity_label": "darts",
        "target_id": "npc_bran",
        "target_name": "Bran the Innkeeper",
        "visibility": "public",
        "intensity": 1,
        "stakes": 1,
        "social_axes": [{"axis": "camaraderie", "delta": 2}],
        "observer_hooks": ["spectacle"],
        "scene_impact": "gathers_attention",
    }

    record = rt._compile_semantic_action_record(sim, runtime_state, "I challenge Bran to darts", action, advisory)
    sim2, runtime2 = rt._apply_semantic_action_to_runtime(sim, runtime_state, record)
    sim3, runtime3 = rt._apply_semantic_action_to_runtime(sim2, runtime2, record)

    assert len(sim3["event_history"]) == 1
    assert len(runtime3["world_consequences"]) == 1
    assert len(runtime3["recent_world_event_rows"]) == 1
    assert len(runtime3["recent_scene_beats"]) == 1


def test_prune_llm_records_state_bounds_index():
    runtime_state = _runtime_state()
    runtime_state["llm_records"] = []
    runtime_state["llm_records_index"] = {}
    for tick in range(400):
        item = {"type": "semantic_action_compiled", "tick": tick, "output": {"tick": tick}}
        runtime_state["llm_records"].append(item)
        runtime_state["llm_records_index"][f"semantic_action_compiled:{tick}"] = item

    pruned = rt._prune_llm_records_state(runtime_state)
    assert len(pruned["llm_records"]) <= rt._MAX_RUNTIME_LLM_RECORDS
    assert len(pruned["llm_records_index"]) <= rt._MAX_RUNTIME_LLM_RECORDS
    assert "semantic_action_compiled:399" in pruned["llm_records_index"]
    assert "semantic_action_compiled:0" not in pruned["llm_records_index"]


def test_compile_and_apply_semantic_action_for_hug():
    sim = _sim_state()
    runtime_state = _runtime_state()
    action = {"action_type": "social_activity", "target_id": "npc_elara"}
    advisory = {
        "action_type": "social_affection",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "activity_label": "hug",
        "target_id": "npc_elara",
        "target_name": "Elara the Merchant",
        "visibility": "local",
        "intensity": 1,
        "stakes": 0,
        "social_axes": [{"axis": "trust", "delta": 1}],
        "observer_hooks": ["relationship_shift"],
        "scene_impact": "changes_mood",
        "reason": "Warm direct social contact.",
    }

    record = rt._compile_semantic_action_record(sim, runtime_state, "I hug Elara", action, advisory)
    sim2, runtime2 = rt._apply_semantic_action_to_runtime(sim, runtime_state, record)

    assert runtime2["actor_activities"]["npc_elara"]["kind"] == "player_social_affection"
    assert any("warmer toward the player" in item.get("summary", "") for item in runtime2["world_consequences"])


def test_semantic_competition_propagates_pressure_and_rumor_and_observer_activity():
    sim = _sim_state()
    runtime_state = _runtime_state()
    action = {"action_type": "social_activity", "target_id": "npc_bran"}
    advisory = {
        "action_type": "social_competition",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "activity_label": "arm_wrestling",
        "target_id": "npc_bran",
        "target_name": "Bran the Innkeeper",
        "visibility": "public",
        "intensity": 2,
        "stakes": 1,
        "social_axes": [{"axis": "respect", "delta": 1}, {"axis": "camaraderie", "delta": 1}],
        "observer_hooks": ["spectacle", "crowd_attention", "rumor_seed"],
        "scene_impact": "gathers_attention",
        "reason": "Direct public contest in a tavern.",
    }

    record = rt._compile_semantic_action_record(sim, runtime_state, "I arm wrestle Bran", action, advisory)
    sim2, runtime2 = rt._apply_semantic_action_to_runtime(sim, runtime_state, record)

    assert runtime2["world_pressure"]
    assert any("Attention builds" in item.get("summary", "") for item in runtime2["world_pressure"])
    assert runtime2["world_rumors"]
    assert any("People start talking" in item.get("summary", "") for item in runtime2["world_rumors"])
    assert "relationship_state" in sim2
    rel = sim2["relationship_state"]["npc_bran::player"]
    assert rel["axes"]["respect"] >= 1
    assert rel["axes"]["camaraderie"] >= 1


def test_semantic_public_competition_generates_observer_activity():
    sim = _sim_state()
    sim["npc_index"]["npc_guard"] = {
        "id": "npc_guard",
        "name": "Captain Aldric",
        "role": "guard captain",
        "location_id": "loc:tavern",
    }
    runtime_state = _runtime_state()
    action = {"action_type": "social_activity", "target_id": "npc_bran"}
    advisory = {
        "action_type": "social_competition",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "activity_label": "darts",
        "target_id": "npc_bran",
        "target_name": "Bran the Innkeeper",
        "visibility": "public",
        "intensity": 1,
        "stakes": 1,
        "social_axes": [{"axis": "respect", "delta": 1}],
        "observer_hooks": ["authority_notice", "crowd_attention"],
        "scene_impact": "gathers_attention",
    }

    record = rt._compile_semantic_action_record(sim, runtime_state, "I challenge Bran to darts", action, advisory)
    sim2, runtime2 = rt._apply_semantic_action_to_runtime(sim, runtime_state, record)

    assert "npc_guard" in runtime2["actor_activities"]
    assert runtime2["actor_activities"]["npc_guard"]["kind"] in {"observer_reaction", "authority_observation"}