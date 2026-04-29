"""Tests for Bundles AC, AD, AE — Quest Rumor Propagation, NPC Referrals, Consequence Signals."""
from __future__ import annotations

from app.rpg.world.consequence_signals import emit_consequence_signals
from app.rpg.world.npc_referrals import suggest_npc_referral
from app.rpg.world.quest_rumor_propagation import (
    maybe_seed_quest_rumor_from_conversation,
    quest_rumors_for_location,
)


def test_backed_quest_conversation_seeds_rumor():
    state = {}
    result = maybe_seed_quest_rumor_from_conversation(
        state,
        conversation_result={
            "topic_pivot": {"requested": True, "accepted": True},
            "requested_topic_access": {"requested": True, "access": "backed"},
            "quest_conversation_access": {
                "requested": True,
                "access": "normal",
                "topic_id": "topic:quest:old_mill",
                "topic_type": "quest",
            },
            "thread": {
                "topic_payload": {
                    "topic_id": "topic:quest:old_mill",
                    "topic_type": "quest",
                    "summary": "There is talk of armed figures near the old mill road.",
                }
            },
            "npc_response_beat": {"speaker_id": "npc:Bran"},
        },
        tick=10,
    )

    assert result["created"] is True
    assert quest_rumors_for_location(state)


def test_unbacked_requested_topic_does_not_seed_rumor():
    state = {}
    result = maybe_seed_quest_rumor_from_conversation(
        state,
        conversation_result={
            "topic_pivot": {"requested": True, "accepted": False},
            "requested_topic_access": {"requested": True, "access": "none"},
            "thread": {
                "topic_payload": {
                    "topic_id": "topic:quest:fallback",
                    "topic_type": "quest",
                    "summary": "A backed fallback topic.",
                }
            },
        },
        tick=10,
    )

    assert result["created"] is False


def test_consequence_signal_for_polite_reply():
    state = {}
    result = emit_consequence_signals(
        state,
        conversation_result={
            "player_reputation_consequence": {
                "event": {"kind": "polite_cooperation"}
            }
        },
        tick=10,
    )

    assert result["emitted"] is True
    assert result["signals"][0]["kind"] == "trust_signal"


def test_consequence_signal_for_unbacked_pressure():
    state = {}
    result = emit_consequence_signals(
        state,
        conversation_result={
            "player_reputation_consequence": {
                "event": {"kind": "unbacked_topic_pressure"}
            }
        },
        tick=5,
    )

    assert result["emitted"] is True
    assert result["signals"][0]["kind"] == "social_tension"


def test_no_consequence_signal_when_no_relevant_event():
    state = {}
    result = emit_consequence_signals(
        state,
        conversation_result={},
        tick=1,
    )

    assert result["emitted"] is False
    assert result["signals"] == []


def test_suggest_npc_referral_no_candidates():
    state = {}
    result = suggest_npc_referral(
        state,
        speaker_id="npc:Bran",
        topic={
            "topic_id": "topic:quest:old_mill",
            "topic_type": "quest",
            "summary": "Armed figures near the old mill road.",
        },
        access={"access": "none"},
    )

    assert result["suggested"] is False


def test_rumor_not_seeded_when_topic_not_quest():
    state = {}
    result = maybe_seed_quest_rumor_from_conversation(
        state,
        conversation_result={
            "topic_pivot": {},
            "requested_topic_access": {},
            "thread": {
                "topic_payload": {
                    "topic_id": "topic:tavern_chatter",
                    "topic_type": "rumor",
                    "summary": "Idle talk about the evening.",
                }
            },
        },
        tick=1,
    )

    assert result["created"] is False
    assert result["reason"] == "not_quest_topic"


def test_requested_topic_access_from_pivot_not_requested():
    from app.rpg.world.quest_conversation_access import (
        requested_topic_access_from_pivot,
    )

    result = requested_topic_access_from_pivot({})
    assert result["requested"] is False
    assert result["source"] == "deterministic_requested_topic_access"


def test_requested_topic_access_from_pivot_accepted():
    from app.rpg.world.quest_conversation_access import (
        requested_topic_access_from_pivot,
    )

    result = requested_topic_access_from_pivot({
        "requested": True,
        "accepted": True,
        "requested_topic_hint": "old mill quest",
        "selected_topic_id": "topic:quest:old_mill",
    })
    assert result["requested"] is True
    assert result["accepted"] is True
    assert result["access"] == "backed"
    assert result["selected_topic_id"] == "topic:quest:old_mill"


def test_requested_topic_access_from_pivot_rejected():
    from app.rpg.world.quest_conversation_access import (
        requested_topic_access_from_pivot,
    )

    result = requested_topic_access_from_pivot({
        "requested": True,
        "accepted": False,
        "requested_topic_hint": "hidden royal assassination",
        "pivot_rejected_reason": "no_backed_topic_found",
    })
    assert result["requested"] is True
    assert result["accepted"] is False
    assert result["access"] == "none"
    assert result["reason"] == "no_backed_topic_found"


def test_consequence_signals_do_not_emit_quest_interest_for_unbacked_fallback():
    from app.rpg.world.consequence_signals import emit_consequence_signals

    state = {}
    result = emit_consequence_signals(
        state,
        conversation_result={
            "requested_topic_access": {
                "requested": True,
                "access": "none",
                "requested_topic_hint": "hidden royal assassination quest",
            },
            "quest_conversation_access": {
                "requested": True,
                "access": "normal",
                "topic_id": "topic:location:loc_tavern:mood",
                "topic_type": "location_smalltalk",
            },
            "player_reputation_consequence": {
                "event": {"kind": "unbacked_topic_pressure"}
            },
        },
        tick=10,
    )

    kinds = {signal["kind"] for signal in result.get("signals", [])}
    assert "social_tension" in kinds
    assert "rumor_pressure" in kinds
    assert "quest_interest" not in kinds


def test_referral_not_suggested_for_generic_polite_reply():
    from app.rpg.world.location_registry import set_current_location
    from app.rpg.world.npc_referrals import suggest_npc_referral

    state = {
        "present_npc_state": {
            "loc_tavern": ["npc:Bran", "npc:Mira", "npc:GuardCaptain"]
        }
    }
    set_current_location(state, "loc_tavern")

    referral = suggest_npc_referral(
        state,
        speaker_id="npc:Bran",
        topic={
            "topic_id": "topic:location:loc_tavern:mood",
            "topic_type": "location_smalltalk",
            "summary": "The tavern is busy.",
        },
        access={"requested": False},
        requested_topic_access={"requested": False},
        player_input="Thank you, that was helpful.",
    )

    assert referral["suggested"] is False
    assert referral["reason"] == "referral_not_relevant_for_turn"


def test_referral_still_suggested_when_player_asks_who_to_ask():
    from app.rpg.world.location_registry import set_current_location
    from app.rpg.world.npc_referrals import suggest_npc_referral

    state = {
        "present_npc_state": {
            "loc_tavern": ["npc:Bran", "npc:Mira", "npc:GuardCaptain"]
        }
    }
    set_current_location(state, "loc_tavern")

    referral = suggest_npc_referral(
        state,
        speaker_id="npc:Bran",
        topic={
            "topic_id": "topic:quest:quest:old_mill_bandits",
            "topic_type": "quest",
            "summary": "There is talk of armed figures near the old mill road.",
        },
        access={"requested": True, "access": "partial"},
        requested_topic_access={"requested": True, "access": "backed"},
        player_input="Who should I ask about the old mill road?",
    )

    assert referral["suggested"] is True
