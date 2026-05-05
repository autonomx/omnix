from tests.rpg.autoplay_llm_campaign import (
    _apply_deferred_narration_violation_detection,
    _replace_turn_result_narration_with_pending,
    _turn_result_narration_source,
)


def test_turn_result_narration_source_reads_exact_transcript_path():
    turn_result = {
        "narration_payload": {
            "source": "provider_runtime_narration",
            "narration": "Provider narration.",
        }
    }

    assert _turn_result_narration_source(turn_result) == "provider_runtime_narration"


def test_replace_turn_result_narration_with_pending_updates_exact_transcript_path():
    turn_result = {
        "narration_payload": {
            "source": "provider_runtime_narration",
            "narration": "Provider narration.",
        }
    }

    _replace_turn_result_narration_with_pending(turn_result)

    assert turn_result["narration_payload"]["source"] == "deferred_runtime_narration_pending"
    assert turn_result["structured_narration"]["source"] == "deferred_runtime_narration_pending"
    assert turn_result["narration"] == "Narration is being prepared..."


def test_apply_deferred_narration_violation_detection_marks_and_replaces_payload():
    record = {
        "turn_index": 1,
        "narration": "Provider narration.",
        "turn_result": {
            "narration_payload": {
                "source": "provider_runtime_narration",
                "narration": "Provider narration.",
            }
        },
    }

    _apply_deferred_narration_violation_detection(
        record=record,
        narration_mode="deferred",
    )

    assert record["blocking_narration_source"] == "provider_runtime_narration"
    assert record["deferred_blocking_provider_violation"] is True
    assert record["blocking_provider_call_suppressed_after_the_fact"] is True
    assert record["turn_result"]["narration_payload"]["source"] == "deferred_runtime_narration_pending"
    assert record["narration"] == "Narration is being prepared..."


def test_apply_deferred_narration_violation_detection_does_not_flag_pending_payload():
    record = {
        "turn_index": 1,
        "turn_result": {
            "narration_payload": {
                "source": "deferred_runtime_narration_pending",
            }
        },
    }

    _apply_deferred_narration_violation_detection(record=record, narration_mode="deferred")

    assert record["blocking_narration_source"] == "deferred_runtime_narration_pending"
    assert record["deferred_blocking_provider_violation"] is False


def test_apply_deferred_narration_violation_detection_reads_raw_result_payload():
    record = {
        "turn_index": 1,
        "narration": "Provider narration.",
        "turn_result": {
            "raw_result": {
                "narration_payload": {
                    "source": "provider_runtime_narration",
                    "narration": "Provider narration.",
                }
            }
        },
    }

    _apply_deferred_narration_violation_detection(
        record=record,
        narration_mode="deferred",
    )

    assert record["blocking_narration_source"] == "provider_runtime_narration"
    assert record["deferred_blocking_provider_violation"] is True
    assert record["blocking_provider_call_suppressed_after_the_fact"] is True
    assert (
        record["turn_result"]["raw_result"]["narration_payload"]["source"]
        == "deferred_runtime_narration_pending"
    )