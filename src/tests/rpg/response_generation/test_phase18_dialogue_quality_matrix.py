from __future__ import annotations

from app.rpg.dialogue_quality_benchmark import (
    CORRECT_SPEAKER_TARGET,
    DIRECT_ANSWER_TARGET,
    GROUNDED_SPECIFICITY_TARGET,
    MAX_EMPTY_LINE_RATE,
    MAX_NEAR_DUPLICATE_RATE,
    MAX_PRIVATE_LEAK_RATE,
    default_dialogue_benchmark_cases,
    evaluate_dialogue_benchmark_case,
    run_dialogue_quality_benchmark,
)
from app.rpg.dialogue_quality_release_matrix import (
    run_release_dialogue_quality_benchmark,
)
from app.rpg.presentation.dialogue_quality import enforce_dialogue_quality
from app.rpg.presentation.visible_response import build_visible_response


def test_dialogue_quality_matrix_covers_required_categories() -> None:
    categories = {case.category for case in default_dialogue_benchmark_cases()}

    assert {
        "business",
        "emotional_disclosure",
        "hostile_noncombat",
        "private_secret_probe",
        "absent_npc",
        "group_conversation",
        "relationship_low_trust",
        "relationship_high_trust",
        "follow_up_continuity",
        "repetition_repair",
        "incorrect_speaker_repair",
        "player_restatement_repair",
    } <= categories


def test_deterministic_dialogue_quality_matrix_meets_release_targets() -> None:
    report = run_release_dialogue_quality_benchmark()

    assert report["ok"] is True, report
    assert report["scenario_count"] >= 12
    assert report["category_count"] >= 12
    metrics = report["metrics"]
    assert metrics["direct_answer_rate"] >= DIRECT_ANSWER_TARGET
    assert metrics["correct_speaker_rate"] >= CORRECT_SPEAKER_TARGET
    assert metrics["grounded_specificity_rate"] >= GROUNDED_SPECIFICITY_TARGET
    assert metrics["continuity_rate"] >= 0.95
    assert metrics["near_duplicate_rate"] <= MAX_NEAR_DUPLICATE_RATE
    assert metrics["private_leak_rate"] <= MAX_PRIVATE_LEAK_RATE
    assert metrics["empty_line_rate"] <= MAX_EMPTY_LINE_RATE


def test_quality_evaluator_detects_speaker_leak_and_empty_output() -> None:
    case = default_dialogue_benchmark_cases()[0]
    observation = evaluate_dialogue_benchmark_case(
        case,
        {
            "visible_response": {
                "format_version": "rpg_visible_response_v1",
                "narration": "",
                "messages": [
                    {
                        "kind": "npc_dialogue",
                        "speaker": "Mira",
                        "text": "The sealed letter from an old caravan contact is here.",
                    }
                ],
                "plain_text": "Mira: The sealed letter from an old caravan contact is here.",
            }
        },
    )

    assert observation.correct_speaker is False
    assert observation.private_leak is True
    assert observation.direct_answer is False


def test_absent_npc_case_requires_narration_without_fabricated_speaker() -> None:
    absent = next(case for case in default_dialogue_benchmark_cases() if case.absent_target)
    report = run_dialogue_quality_benchmark([absent])

    assert report["ok"] is True
    row = report["observations"][0]
    assert row["speakers"] == ()
    assert "not here" in row["visible_text"].casefold()


def test_quality_policy_repairs_authoritatively_absent_speaker() -> None:
    session = {
        "state": {"location": "Rusty Flagon Tavern"},
        "simulation_state": {
            "npc_index": {
                "npc:bran": {"id": "npc:bran", "name": "Bran"},
                "npc:mira": {"id": "npc:mira", "name": "Mira"},
            },
            "scene": {"present_npc_ids": ["npc:mira"]},
            "player_state": {"nearby_npc_ids": ["npc:mira"]},
        },
    }
    result = {
        "ok": True,
        "stateful": False,
        "action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "visible_response": {
            "narration": "Bran answers.",
            "npc": {"speaker": "Bran", "line": "I am not here."},
        },
    }

    repaired = enforce_dialogue_quality(
        result,
        session=session,
        player_input="I ask for Bran while he is away.",
    )

    visible = repaired["canonical_visible_response"]
    assert visible["messages"] == []
    assert "Bran is not here" in visible["plain_text"]
    assert "Rusty Flagon Tavern" in visible["plain_text"]
    assert repaired["dialogue_quality"]["repair_source"] == "authoritative_absent_npc_repair_v1"
    assert build_visible_response(repaired)["messages"] == []
    assert "Bran is not here" in build_visible_response(repaired)["plain_text"]
    replay_surface = dict(repaired)
    replay_surface.pop("canonical_visible_response")
    assert build_visible_response(replay_surface)["messages"] == []
    assert "Bran is not here" in build_visible_response(replay_surface)["plain_text"]


def test_quality_policy_splits_combined_multi_speaker_response() -> None:
    profiles = [
        {
            "id": "npc:bran",
            "name": "Bran",
            "biography": {"public": "Bran guarded caravans on the old road."},
        },
        {
            "id": "npc:mira",
            "name": "Mira",
            "biography": {"public": "Mira found fresh wagon tracks on the old road."},
        },
    ]
    result = {
        "ok": True,
        "stateful": False,
        "action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "visible_response": {
            "narration": "They compare notes.",
            "npc": {
                "speaker": "bran,npc:mira",
                "line": (
                    'Bran says, "The old road is quiet." '
                    'Mira adds, "Fresh wagon tracks lead toward the quarry."'
                ),
            },
        },
    }
    session = {
        "simulation_state": {
            "npc_index": {profile["id"]: profile for profile in profiles},
            "scene": {"present_npc_ids": ["npc:bran", "npc:mira"]},
            "player_state": {"nearby_npc_ids": ["npc:bran", "npc:mira"]},
        }
    }

    repaired = enforce_dialogue_quality(
        result,
        session=session,
        player_input="I ask Bran and Mira what they saw.",
    )

    messages = repaired["canonical_visible_response"]["messages"]
    assert [message["speaker"] for message in messages] == ["Bran", "Mira"]
    assert "old road" in messages[0]["text"]
    assert "wagon tracks" in messages[1]["text"]
    assert repaired["dialogue_quality"]["repair_source"] == "multi_speaker_structure_repair_v1"
    assert [
        message["speaker"] for message in build_visible_response(repaired)["messages"]
    ] == ["Bran", "Mira"]
    replay_surface = dict(repaired)
    replay_surface.pop("canonical_visible_response")
    assert [
        message["speaker"] for message in build_visible_response(replay_surface)["messages"]
    ] == ["Bran", "Mira"]
