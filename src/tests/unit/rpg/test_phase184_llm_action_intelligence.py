from app.rpg.ai.action_intelligence import (
    build_action_intelligence_prompt,
    normalize_action_advisory,
    merge_action_advisory,
    get_action_advisory,
)


class _Gateway:
    def __init__(self, payload):
        self.payload = payload

    def complete(self, prompt):
        return {"text": self.payload}


def test_normalize_action_advisory_bounds_fields():
    advisory = normalize_action_advisory(
        {
            "action_type": "persuade",
            "difficulty": "hard",
            "skill_id": "persuasion",
            "intent_tags": ["social", "de-escalation", "please convert this to a very long tag that should be clipped"],
            "narrative_goal": "Convince the guard to let the player pass peacefully.",
            "target_id": "guard_1",
            "reason": "The user explicitly asked to talk rather than threaten.",
        },
        {"action_type": "investigate"},
    )
    assert advisory["action_type"] == "persuade"
    assert advisory["difficulty"] == "hard"
    assert advisory["skill_id"] == "persuasion"
    assert advisory["target_id"] == "guard_1"
    assert len(advisory["intent_tags"]) <= 6


def test_normalize_action_advisory_rejects_invalid_values():
    advisory = normalize_action_advisory(
        {
            "action_type": "become_god",
            "difficulty": "impossible",
            "skill_id": "omniscience",
        },
        {"action_type": "investigate", "difficulty": "normal"},
    )
    assert advisory["action_type"] == "investigate"
    assert advisory["difficulty"] == "normal"
    assert advisory["skill_id"] == ""


def test_merge_action_advisory_adds_metadata_without_overriding_truth():
    merged = merge_action_advisory(
        {
            "action_type": "persuade",
            "target_id": "npc_sara",
        },
        {
            "action_type": "persuade",
            "difficulty": "hard",
            "skill_id": "persuasion",
            "intent_tags": ["social", "rapport"],
            "narrative_goal": "Build trust.",
            "reason": "Talking is better than threatening here.",
        },
    )
    assert merged["action_type"] == "persuade"
    assert merged["difficulty"] == "hard"
    assert merged["skill_id"] == "persuasion"
    assert merged["metadata"]["llm_advisory"] is True
    assert merged["metadata"]["intent_tags"] == ["social", "rapport"]


def test_get_action_advisory_parses_json_text():
    gateway = _Gateway(
        '{"action_type":"persuade","difficulty":"hard","skill_id":"persuasion","intent_tags":["social"],"target_id":"npc_sara","reason":"Talk action detected."}'
    )
    result = get_action_advisory(
        llm_gateway=gateway,
        player_input="talk to sara",
        simulation_state={},
        runtime_state={},
        candidate_action={"action_type": "persuade", "npc_id": "npc_sara"},
    )
    assert result["action_type"] == "persuade"
    assert result["difficulty"] == "hard"
    assert result["target_id"] == "npc_sara"


def test_build_action_intelligence_prompt_contains_candidate_action():
    prompt = build_action_intelligence_prompt(
        player_input="look around carefully",
        simulation_state={"player_state": {"level": 1}},
        runtime_state={"current_scene": {"scene_id": "scene:tavern", "title": "Rusty Flagon"}},
        candidate_action={"action_type": "investigate"},
    )
    assert "candidate_action" in prompt
    assert "investigate" in prompt