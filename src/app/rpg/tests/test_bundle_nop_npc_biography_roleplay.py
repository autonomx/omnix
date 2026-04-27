from app.rpg.ai.npc_roleplay import validate_npc_roleplay_output
from app.rpg.world.npc_biography_registry import get_npc_biography, list_npc_biographies
from app.rpg.world.npc_dialogue_profile import (
    build_npc_dialogue_profile,
    deterministic_biography_line,
)


def test_biography_registry_has_default_npcs():
    ids = {bio["npc_id"] for bio in list_npc_biographies()}
    assert "npc:Bran" in ids
    assert "npc:Mira" in ids
    assert "npc:GuardCaptain" in ids


def test_bran_biography_contains_role_and_boundaries():
    bio = get_npc_biography("npc:Bran")
    assert bio["role"] == "Tavern keeper"
    assert "personality_traits" in bio
    assert "knowledge_boundaries" in bio
    assert "must_not_claim" in bio["knowledge_boundaries"]


def test_dialogue_profile_uses_topic_facts_and_biography():
    state = {
        "conversation_social_state": {
            "npc_state": {
                "npc:Bran": {
                    "familiarity": 2,
                    "trust_hint": "guarded",
                }
            }
        },
        "npc_goal_state": {
            "goals": {
                "npc:Bran": [
                    {
                        "goal_id": "goal:bran:keep_tavern_orderly",
                        "kind": "maintain_order",
                        "priority": 3,
                        "status": "active",
                    }
                ]
            }
        },
    }
    topic = {
        "topic_id": "topic:quest:old_mill",
        "topic_type": "quest",
        "title": "Trouble near the Old Mill",
        "summary": "There is talk of armed figures near the old mill road.",
        "allowed_facts": ["There is talk of armed figures near the old mill road."],
    }
    profile = build_npc_dialogue_profile(
        npc_id="npc:Bran",
        simulation_state=state,
        runtime_state={},
        topic=topic,
        listener_id="player",
        response_intent="answer",
    )

    assert profile["role"] == "Tavern keeper"
    assert profile["topic_type"] == "quest"
    assert profile["allowed_facts"]
    assert profile["used_fact_ids"] == ["topic:quest:old_mill"]
    assert profile["active_goal"]["kind"] == "maintain_order"


def test_deterministic_biography_line_personalizes_backed_fact():
    profile = build_npc_dialogue_profile(
        npc_id="npc:Bran",
        simulation_state={},
        runtime_state={},
        topic={
            "topic_id": "topic:quest:old_mill",
            "topic_type": "quest",
            "title": "Trouble near the Old Mill",
            "summary": "There is talk of armed figures near the old mill road.",
            "allowed_facts": ["There is talk of armed figures near the old mill road."],
        },
        listener_id="player",
        response_intent="answer",
    )

    line = deterministic_biography_line(
        profile=profile,
        topic={
            "topic_id": "topic:quest:old_mill",
            "topic_type": "quest",
            "allowed_facts": ["There is talk of armed figures near the old mill road."],
        },
        pivot={"requested": True, "accepted": True},
        response_style="guarded",
    )

    assert line["roleplay_source"] == "deterministic_template"
    assert line["biography_role"] == "Tavern keeper"
    assert "old mill road" in line["line"].lower()
    assert line["used_fact_ids"] == ["topic:quest:old_mill"]


def test_deterministic_biography_line_deflects_unbacked_topic():
    profile = build_npc_dialogue_profile(
        npc_id="npc:Bran",
        simulation_state={},
        runtime_state={},
        topic={},
        listener_id="player",
        response_intent="deflect",
    )

    line = deterministic_biography_line(
        profile=profile,
        topic={},
        pivot={
            "requested": True,
            "accepted": False,
            "requested_topic_hint": "secret vault under city",
            "pivot_rejected_reason": "no_backed_topic_found",
        },
        response_style="guarded",
    )

    assert line["roleplay_source"] == "deterministic_template"
    assert line["used_fact_ids"] == []
    assert "no reliable word" in line["line"].lower() or "do not know" in line["line"].lower()
    assert "secret vault is" not in line["line"].lower()


def test_roleplay_validator_accepts_valid_output():
    profile = {
        "used_fact_ids": ["topic:quest:old_mill"],
        "allowed_facts": ["There is trouble near the old mill road."],
    }
    validation = validate_npc_roleplay_output(
        {
            "speaker_id": "npc:Bran",
            "speaker_name": "Bran",
            "line": "Folk have been avoiding the old mill road after dusk.",
            "style_tags": ["guarded"],
            "used_fact_ids": ["topic:quest:old_mill"],
            "claims": ["People avoid the old mill road."],
            "forbidden_effects": [],
        },
        expected_speaker_id="npc:Bran",
        profile=profile,
    )

    assert validation["ok"] is True


def test_roleplay_validator_rejects_wrong_speaker_and_unbacked_fact():
    profile = {
        "used_fact_ids": ["topic:quest:old_mill"],
        "allowed_facts": ["There is trouble near the old mill road."],
    }
    validation = validate_npc_roleplay_output(
        {
            "speaker_id": "npc:Mira",
            "speaker_name": "Mira",
            "line": "Take this reward and follow the secret lair map.",
            "style_tags": ["helpful"],
            "used_fact_ids": ["topic:secret:lair"],
            "claims": ["There is a secret lair map."],
            "forbidden_effects": [],
        },
        expected_speaker_id="npc:Bran",
        profile=profile,
    )

    assert validation["ok"] is False
    assert "speaker_id_mismatch" in validation["violations"]
    assert "unbacked_fact_id:topic:secret:lair" in validation["violations"]
