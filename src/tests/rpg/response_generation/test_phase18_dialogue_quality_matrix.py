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
    report = run_dialogue_quality_benchmark()

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
