from app.rpg.ai.world_scene_narrator import build_structured_narration, apply_narration_emphasis


def test_build_structured_narration_includes_required_blocks():
    scene = {
        "scene_id": "scene:tavern",
        "title": "The Rusty Flagon Tavern",
        "location_name": "Rusty Flagon",
        "summary": "Patrons glance over as tension gathers near the hearth.",
    }
    narration_context = {
        "action_type": "persuade",
        "resolved_result": {
            "ok": True,
            "target_name": "Sara",
            "message": "You get Sara's attention.",
            "npc_reply": '"All right," Sara says. "I will listen."',
        },
        "xp_result": {"player_xp": 12},
        "skill_xp_result": {"awards": {"persuasion": 3}},
        "level_up": [],
        "skill_level_ups": [],
    }
    result = build_structured_narration(scene, narration_context, "Sara watches you carefully.")

    assert result["scene_summary"]
    assert result["action_result_line"]
    assert result["npc_reply_block"]
    assert result["rewards_block"]
    assert isinstance(result["emphasis_markers"], list)
    assert "**+12 XP**" in result["rewards_block"] or "+12 XP" in result["rewards_block"]


def test_build_structured_narration_marks_damage_and_level_up():
    scene = {
        "scene_id": "scene:road",
        "title": "Old North Road",
        "location_name": "Old North Road",
    }
    narration_context = {
        "action_type": "attack_melee",
        "resolved_result": {
            "ok": True,
            "target_name": "Bandit",
            "combat_result": {
                "outcome": "hit",
                "damage": 18,
                "target_name": "Bandit",
            },
        },
        "xp_result": {"player_xp": 20},
        "skill_xp_result": {"awards": {"swordsmanship": 4}},
        "level_up": [{"level": 2}],
        "skill_level_ups": [{"skill_id": "swordsmanship"}],
    }
    result = build_structured_narration(scene, narration_context, "")

    assert "18 damage" in result["markdown"]
    assert "Level Up!" in result["markdown"]
    assert result["action_result_line"]


def test_build_structured_narration_falls_back_without_npc_reply():
    scene = {
        "scene_id": "scene:market",
        "title": "Market Square",
    }
    narration_context = {
        "action_type": "investigate",
        "resolved_result": {
            "ok": True,
            "message": "You find fresh boot prints near the cart.",
        },
        "xp_result": {"player_xp": 5},
        "skill_xp_result": {"awards": {"investigation": 2}},
        "level_up": [],
        "skill_level_ups": [],
    }
    result = build_structured_narration(scene, narration_context, "Vendors keep their distance as you inspect the square.")

    assert result["scene_summary"]
    assert result["action_result_line"]
    assert result["markdown"]


def test_apply_narration_emphasis_does_not_double_wrap_existing_bold():
    text = "**Bandit** takes **18 damage**."
    rendered = apply_narration_emphasis(text, ["Bandit", "18 damage"])
    assert rendered == "**Bandit** takes **18 damage**."


def test_structured_narration_includes_rewards_label_in_markdown():
    result = build_structured_narration({}, {"xp_result": {"player_xp": 7}}, "")
    assert "**Rewards:**" in result["markdown"]