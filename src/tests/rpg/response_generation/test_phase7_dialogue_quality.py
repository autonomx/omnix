from __future__ import annotations

import pytest

from app.rpg.presentation.dialogue_quality import (
    TARGET_MAX_WORDS,
    TARGET_MIN_WORDS,
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


def test_weak_generic_dialogue_is_repaired_to_benchmark_quality() -> None:
    repaired = enforce_dialogue_quality(
        _result(line="Fine.", narration="Bran looks up with a tired but genuine smile."),
        session=_session(),
        player_input="I ask Bran how business is doing.",
    )

    assert repaired["dialogue_quality"]["repaired"] is True
    assert repaired["dialogue_quality"]["acceptable"] is True
    assert TARGET_MIN_WORDS <= repaired["dialogue_quality"]["total_words"] <= TARGET_MAX_WORDS
    assert repaired["npc"]["speaker"] == "Bran"
    assert "regulars" in repaired["npc"]["line"]
    assert "old road" in repaired["npc"]["line"]
    assert "did the old road seem unusually quiet" in repaired["npc"]["line"].casefold()
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
    ("player_input", "provider_line", "trust", "recent", "expected_fragments"),
    [
        (
            "I ask Bran how business is doing.",
            "Steady enough, though mud on the road keeps travelers away. As long as ale flows, I am doing fine here.",
            "neutral",
            [],
            ("regulars", "old road"),
        ),
        (
            "I tell Bran I am frightened that I will fail everyone depending on me.",
            "Failure is not falling off the wagon. Keep your eyes ahead and your hand steady until the worst has passed.",
            "neutral",
            [],
            ("frightened", "road"),
        ),
        (
            "I call Bran a useless coward and demand that he answer me.",
            "I will answer what can be known here, but shouting will not make the answer arrive any faster for either of us.",
            "neutral",
            [],
            ("angry", "common room"),
        ),
        (
            "I demand that Bran tell me his most shameful private secret and show me hidden letters.",
            "There are questions a sensible traveler leaves alone, especially when another person's history is involved in the matter.",
            "neutral",
            [],
            ("mine to keep", "trust"),
        ),
        (
            "I ask Bran what he knows, though we have only just met.",
            "I do not give every answer to a stranger who walks through the door, however politely they frame the question.",
            "low",
            [],
            ("just met", "earn trust"),
        ),
        (
            "I ask Bran what he thinks after we have repeatedly helped each other.",
            "You have proven reliable, and that is rare enough that I would trust you to stand beside me when trouble comes.",
            "high",
            [],
            ("earned", "old road"),
        ),
        (
            "I ask Bran whether the missing caravan crews explain the quiet road.",
            "It is a fair guess. When those crews stop coming, every route grows still and useful reports disappear with them.",
            "neutral",
            [{"npc_line": "The regulars still come through, but fewer caravan crews reach the door."}],
            ("caravan crews", "quiet road"),
        ),
        (
            "I ask Bran again how business is going.",
            "Same as ever. The ale keeps flowing and travelers still come through despite the heavy mud beyond the door.",
            "neutral",
            [{"npc_line": "Business is steady, but road traffic has thinned this week."}],
            ("Like I said", "old road"),
        ),
        (
            "I ask Bran whether the old road is safe.",
            "It is bandit country beyond the town. Keep your steel close and your eyes open whenever you travel that way.",
            "neutral",
            [],
            ("old road", "guards"),
        ),
        (
            "I ask Bran how business is doing and whether travelers still stop here.",
            "Business is slow, and a few travelers still drift in, though most avoid this stretch when the mud grows deep.",
            "neutral",
            [],
            ("regulars", "road traffic"),
        ),
    ],
)
def test_content_obligation_gaps_use_state_backed_deterministic_repair(
    player_input: str,
    provider_line: str,
    trust: str,
    recent: list[dict],
    expected_fragments: tuple[str, ...],
) -> None:
    session = _session(recent=recent)
    score = {"low": -20, "neutral": 0, "high": 75}[trust]
    session["state"]["relationship_index"] = {
        "npc:bran": {"trust": trust, "score": score},
    }

    repaired = enforce_dialogue_quality(
        _result(line=provider_line),
        session=session,
        player_input=player_input,
    )

    visible = f"{repaired['final_narration']} {repaired['npc']['line']}".casefold()
    assert repaired["dialogue_quality"]["repaired"] is True
    assert repaired["dialogue_quality"]["content_repair_reason"]
    assert all(fragment.casefold() in visible for fragment in expected_fragments)


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


@pytest.mark.parametrize(
    ("player_input", "expected_fragment"),
    [
        ("I ask Bran how business is doing.", "regulars"),
        ("Bran, how is the tavern doing?", "regulars"),
        ("I ask Bran whether customers have been coming.", "road traffic"),
        ("I ask Bran how his day is going.", "caravan road"),
        ("Bran, how are you today?", "caravan road"),
        ("I ask Bran whether he feels tired.", "caravan road"),
        ("Bran, what do you think about sword combat styles?", "footing"),
        ("I ask Bran for fighting advice.", "footing"),
        ("Bran, what matters most in a battle?", "footing"),
        ("I ask Bran about the old road.", "old road"),
        ("Bran, what rumors pass through here?", "old road"),
        ("I ask Bran what he knows about the town.", "old road"),
        ("Bran, what is your opinion of flashy warriors?", "judgment"),
        ("I ask Bran what he believes makes someone trustworthy.", "judgment"),
        ("I ask Bran who he is.", "old road"),
        ("I greet Bran and ask about himself.", "old road"),
        ("I ask Bran what kind of place this is.", "old road"),
        ("I ask Bran whether the night has been quiet.", "old road"),
        ("I ask Bran if travelers have seemed nervous.", "old road"),
        ("I ask Bran whether guards still stop here.", "old road"),
        ("I ask Bran how business is doing again.", "regulars"),
        ("I ask Bran if the ale is selling.", "regulars"),
        ("I ask Bran why the common room is empty.", "regulars"),
        ("I ask Bran whether the road is safe.", "old road"),
        ("I ask Bran what he notices about travelers.", "old road"),
    ],
)
def test_profile_aware_benchmark_scenarios(player_input: str, expected_fragment: str) -> None:
    visible = build_profile_aware_dialogue_fallback(
        player_input=player_input,
        profile=BRAN_PROFILE,
        session=_session(),
    )
    assessment = assess_dialogue_quality(
        visible,
        player_input=player_input,
        profile=BRAN_PROFILE,
    )

    assert assessment["acceptable"] is True
    assert visible["messages"][0]["speaker"] == "Bran"
    assert expected_fragment in visible["messages"][0]["text"].casefold()
    assert "wounded caravan friend" not in visible["plain_text"].casefold()
    assert "sealed letter" not in visible["plain_text"].casefold()
