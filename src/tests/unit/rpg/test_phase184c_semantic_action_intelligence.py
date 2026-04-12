from app.rpg.ai.semantic_action_intelligence import normalize_semantic_action_advisory


def test_normalize_semantic_action_for_darts_competition():
    candidate = {"action_type": "social_activity", "target_id": "npc_bran"}
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
    }
    normalized = normalize_semantic_action_advisory(advisory, candidate)
    assert normalized["action_type"] == "social_competition"
    assert normalized["semantic_family"] == "social"
    assert normalized["activity_label"] == "darts"
    assert normalized["target_id"] == "npc_bran"
    assert {"axis": "camaraderie", "delta": 2} in normalized["social_axes"]


def test_normalize_semantic_action_for_hug():
    candidate = {"action_type": "social_activity", "target_id": "npc_elara"}
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
        "social_axes": [{"axis": "trust", "delta": 1}, {"axis": "camaraderie", "delta": 1}],
        "observer_hooks": ["relationship_shift"],
        "scene_impact": "changes_mood",
    }
    normalized = normalize_semantic_action_advisory(advisory, candidate)
    assert normalized["action_type"] == "social_affection"
    assert normalized["activity_label"] == "hug"
    assert normalized["target_id"] == "npc_elara"