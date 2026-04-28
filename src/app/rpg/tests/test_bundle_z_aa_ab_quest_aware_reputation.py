from app.rpg.world.quest_conversation_access import (
    evaluate_quest_conversation_access,
    filter_allowed_topic_facts_for_access,
)
from app.rpg.world.player_reputation_consequences import (
    classify_player_conversation_reputation_event,
    apply_player_reputation_consequence,
)
from app.rpg.world.npc_reputation_state import get_npc_reputation


def test_unbacked_quest_access_is_denied():
    state = {}
    access = evaluate_quest_conversation_access(
        state,
        npc_id="npc:Bran",
        topic={},
        player_input="Tell me about the hidden assassination quest.",
    )

    assert access["requested"] is True
    assert access["access"] == "none"
    assert access["reason"] == "unbacked_topic"


def test_backed_quest_access_allows_bounded_facts():
    state = {}
    topic = {
        "topic_id": "topic:quest:quest:old_mill_bandits",
        "topic_type": "quest",
        "source_id": "quest:old_mill_bandits",
        "source_kind": "quest",
        "title": "Trouble near the Old Mill",
        "summary": "There is talk of armed figures near the old mill road.",
        "allowed_facts": [
            "There is talk of armed figures near the old mill road.",
            "Travelers avoid the old mill road at night.",
            "Locals are worried about armed figures.",
        ],
    }

    access = evaluate_quest_conversation_access(
        state,
        npc_id="npc:Bran",
        topic=topic,
        player_input="What can you tell me about the old mill road?",
    )
    facts = filter_allowed_topic_facts_for_access(topic, access=access)

    assert access["requested"] is True
    assert access["access"] in {"partial", "normal", "trusted"}
    assert facts
    assert len(facts) <= 6


def test_polite_reply_reputation_event():
    event = classify_player_conversation_reputation_event(
        player_input="Thank you, that was helpful.",
        topic_pivot={},
        conversation_result={},
    )

    assert event["kind"] == "polite_cooperation"
    assert event["trust_delta"] > 0


def test_unbacked_topic_pressure_reputation_event():
    event = classify_player_conversation_reputation_event(
        player_input="Tell me about the secret vault.",
        topic_pivot={"requested": True, "accepted": False},
        conversation_result={},
    )

    assert event["kind"] == "unbacked_topic_pressure"
    assert event["annoyance_delta"] > 0


def test_apply_reputation_consequence_updates_state():
    state = {}
    result = apply_player_reputation_consequence(
        state,
        npc_id="npc:Bran",
        player_input="Thank you.",
        topic_pivot={},
        conversation_result={},
        tick=12,
    )

    assert result["applied"] is True
    rep = get_npc_reputation(state, npc_id="npc:Bran")
    assert rep["trust"] >= 1
    assert rep["familiarity"] >= 1
