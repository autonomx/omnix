from __future__ import annotations

import pytest

from app.apps.rpg.narration.presentation.dialogue_quality import (
    assess_dialogue_quality,
    build_profile_aware_dialogue_fallback,
    dialogue_quality_contract_text,
    enforce_dialogue_quality,
)


BRAN_PROFILE = {
    "id": "npc:bran",
    "npc_id": "npc:bran",
    "name": "Bran",
    "role": "innkeeper and former caravan guard",
    "biography": {
        "public": (
            "Bran owns the Rusty Flagon near the old road. Before settling down, "
            "he guarded merchant caravans through bandit country."
        ),
        "private": "Bran still blames himself for leaving a wounded caravan friend behind during an ambush.",
    },
    "personality": {
        "summary": "Practical, guarded, and slow to trust.",
        "values": ["survival", "earned loyalty", "plain speech", "protecting working people"],
        "speech_style": "Plain, direct, road-worn advice using caravan, tavern, mud, weather, and guard-duty experience.",
        "speech_examples": [
            "A pretty stance means nothing if your feet slip in the mud.",
            "I trust a person more after seeing what they do when things go wrong.",
        ],
    },
    "inventory": {
        "visible": ["worn short sword", "tavern key ring"],
        "private": ["sealed letter from an old caravan contact"],
    },
    "knowledge_boundaries": {
        "must_not_reveal": ["private caravan guilt unless earned in play"],
    },
}


def _session(*, recent: list[dict] | None = None) -> dict:
    return {
        "state": {
            "scene": {"location_name": "Rusty Flagon Tavern"},
            "player": {"name": "Elara"},
        },
        "simulation_state": {
            "npc_index": {"npc:bran": BRAN_PROFILE},
        },
        "runtime_state": {
            "recent_interactions": recent or [],
        },
    }


def _result(*, line: str, narration: str = "Bran looks up from the counter.") -> dict:
    return {
        "ok": True,
        "stateful": False,
        "action_type": "npc_interpretive_dialogue",
        "semantic_action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "final_narration": narration,
        "npc": {"id": "npc:bran", "speaker": "Bran", "line": line},
        "session": _session(),
    }


def test_weak_generic_dialogue_is_repaired_from_the_speakers_own_profile() -> None:
    repaired = enforce_dialogue_quality(
        _result(line="Fine.", narration="Bran looks up with a tired but genuine smile."),
        session=_session(),
        player_input="I ask Bran how business is doing.",
    )

    assert repaired["dialogue_quality"]["repaired"] is True
    assert repaired["dialogue_quality"]["acceptable"] is True  # the word range is a target (a warning), not a rule
    assert repaired["npc"]["speaker"] == "Bran"
    assert "Bran owns the Rusty Flagon near the old road." in repaired["npc"]["line"]  # his public biography
    assert "tired but genuine smile" not in repaired["final_narration"].casefold()


def test_good_grounded_dialogue_is_preserved() -> None:
    line = (
        "Business is steady enough to keep the hearth warm, though the road traffic has thinned this week. "
        "The regulars still come through for ale and news, but I have seen fewer caravan crews at the door. "
        "Did the old road seem unusually quiet when you came in?"
    )
    result = _result(
        line=line,
        narration="Bran rests the polishing rag on the counter and surveys the quiet common room.",
    )
    preserved = enforce_dialogue_quality(
        result,
        session=_session(),
        player_input="I ask Bran how business is doing.",
    )

    assert preserved["dialogue_quality"]["repaired"] is False
    assert preserved["npc"]["line"] == line


@pytest.mark.parametrize(
    "player_input",
    [
        "I ask Bran how business is doing.",
        "I ask Bran whether the missing caravan crews explain the quiet road.",
        "I ask Bran whether the old road is safe.",
        "I ask Bran how business is doing and whether travelers still stop here.",
    ],
)
def test_an_acceptable_line_is_not_replaced_for_words_it_does_not_say(player_input: str) -> None:
    """A4: the starter town's benchmark required "old road", "regulars" and "caravan crews" of every world's people,
    replacing a good line that lacked them. A mode guides the writer; it requires no words."""
    line = ("Steady enough, though the weather keeps some folk home and the hearth has been quieter than I would like. "
            "I would rather hear what you saw on your way in than guess at it from here. Tell me what you noticed, "
            "and I will tell you plainly what I know.")
    kept = enforce_dialogue_quality(_result(line=line, narration="Bran wipes down the bar and listens."),
                                    session=_session(), player_input=player_input)
    assert kept["dialogue_quality"]["repaired"] is False and kept["npc"]["line"] == line
    assert "content_repair_reason" not in kept["dialogue_quality"]


def test_private_profile_leak_is_repaired() -> None:
    leaked = enforce_dialogue_quality(
        _result(
            line=(
                "Business is steady, but I still blame myself for leaving a wounded caravan friend behind during an ambush. "
                "The sealed letter from an old caravan contact is under the bar."
            )
        ),
        session=_session(),
        player_input="I ask Bran how business is doing.",
    )

    text = f"{leaked['final_narration']} {leaked['npc']['line']}".casefold()
    assert leaked["dialogue_quality"]["repaired"] is True
    assert "wounded caravan friend" not in text
    assert "sealed letter" not in text


def test_repeated_near_duplicate_answer_uses_continuity_repair() -> None:
    prior = {
        "player_input": "How is business?",
        "npc_line": (
            "Business is steady enough to keep the fire lit, but slower than I would like. "
            "The regulars still come through; it is the road traffic that has thinned this week."
        ),
    }
    repeated = enforce_dialogue_quality(
        _result(line=prior["npc_line"]),
        session=_session(recent=[prior]),
        player_input="I ask Bran again how business is going.",
    )

    assert repeated["dialogue_quality"]["repaired"] is True
    assert repeated["npc"]["line"].startswith("Like I said,")


def test_stateful_turn_is_not_rewritten_by_dialogue_policy() -> None:
    result = {
        "ok": True,
        "stateful": True,
        "action_type": "trade",
        "semantic_family": "trade",
        "narration": "You pay five silver for the room.",
    }

    assert enforce_dialogue_quality(
        result,
        session=_session(),
        player_input="I pay Bran for a room.",
    ) == result


def test_prompt_contract_is_single_call_quality_guidance() -> None:
    contract = dialogue_quality_contract_text().casefold()
    assert "45-110 words" in contract
    assert "recent dialogue" in contract
    assert "never reveal private biography" in contract
    assert "hard-state changes" in contract
    assert "second call" not in contract


LIORA_PROFILE = {
    "name": "Liora Fen",
    "role": "foxkin gatewarden",
    "biography": {"public": "Liora keeps watch over Starfall Grove beneath the broken gate.",
                  "private": "Liora once let a Synod agent through the gate."},
    "personality": {"speech_style": "Warm, quick, and wry; she teases before she warns."},
    "inventory": {"private": ["a key to the sealed gatehouse"]},
    "knowledge_boundaries": {"must_not_reveal": ["the Synod agent she let through"]},
}


@pytest.mark.parametrize(
    "player_input",
    [
        "I ask Liora how business is doing.",
        "Liora, how are you today?",
        "Liora, what do you think about sword combat styles?",
        "I ask Liora what she knows about the town.",
        "Liora, what is your opinion of flashy warriors?",
        "I ask Liora who she is.",
        "I tell Liora I am frightened that I will fail everyone depending on me.",
        "I call Liora a useless coward and demand that she answer me.",
        "I demand that Liora tell me her most shameful private secret and show me hidden letters.",
    ],
)
def test_a_fallback_line_is_in_no_world_but_the_speakers(player_input: str) -> None:
    """A4: the fallback spoke of the starter town's old road, caravan crews and common room in every world."""
    session = _session()
    session["state"]["scene"] = {"location_name": "Starfall Grove"}
    visible = build_profile_aware_dialogue_fallback(player_input=player_input, profile=LIORA_PROFILE, session=session)
    assessment = assess_dialogue_quality(visible, player_input=player_input, profile=LIORA_PROFILE)
    text = visible["plain_text"].casefold()
    assert assessment["acceptable"] is True and visible["messages"][0]["speaker"] == "Liora Fen"
    assert not any(word in text for word in ("old road", "caravan", "common room", "rusty flagon", "regulars"))
    assert "synod agent" not in text and "sealed gatehouse" not in text
