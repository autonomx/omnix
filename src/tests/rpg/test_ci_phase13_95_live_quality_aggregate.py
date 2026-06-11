from __future__ import annotations

from tests.rpg import interactive_cli_live_quality_eval as quality


def _summary(*, ok: bool = True, turn_count: int = 3, avg_score: float = 4.0, fun: float = 4.1) -> dict[str, object]:
    return {
        "format_version": quality.LIVE_QUALITY_EVAL_VERSION,
        "ok": ok,
        "turn_count": turn_count,
        "avg_score": avg_score,
        "scores": {
            "coherence": avg_score,
            "agency": avg_score,
            "specificity": avg_score,
            "continuity": avg_score,
            "fun": fun,
        },
        "failures": [] if ok else ["average_quality_score_below_threshold"],
        "warnings": [] if ok else ["fun_score_below_target"],
    }


def test_phase13_95_summary_schema_accepts_valid_payload() -> None:
    assert quality.validate_live_quality_eval_summary(_summary()) == {
        "ok": True,
        "format_version": quality.LIVE_QUALITY_EVAL_VERSION,
    }


def test_phase13_95_summary_schema_rejects_missing_required_keys() -> None:
    assert quality.validate_live_quality_eval_summary({"ok": True}) == {
        "ok": False,
        "error": "live_quality_summary_required_keys_missing",
        "missing_keys": ["avg_score", "format_version", "scores", "turn_count"],
    }


def test_phase13_95_summary_schema_rejects_wrong_version_and_bad_scores() -> None:
    wrong_version = dict(_summary())
    wrong_version["format_version"] = "old"
    assert quality.validate_live_quality_eval_summary(wrong_version)["error"] == "live_quality_summary_version_mismatch"

    bad_scores = dict(_summary())
    bad_scores["scores"] = {"fun": 4.0}
    assert quality.validate_live_quality_eval_summary(bad_scores) == {
        "ok": False,
        "error": "live_quality_summary_scores_invalid",
        "missing_scores": ["agency", "coherence", "continuity", "specificity"],
    }


def test_phase13_95_summary_schema_rejects_non_bool_ok_and_bad_turn_count() -> None:
    bad_ok = dict(_summary())
    bad_ok["ok"] = "true"
    assert quality.validate_live_quality_eval_summary(bad_ok) == {
        "ok": False,
        "error": "live_quality_summary_ok_not_bool",
        "actual_type": "str",
    }

    bad_turn_count = dict(_summary())
    bad_turn_count["turn_count"] = -1
    assert quality.validate_live_quality_eval_summary(bad_turn_count) == {
        "ok": False,
        "error": "live_quality_summary_turn_count_invalid",
    }


def test_phase13_95_aggregate_counts_all_successes() -> None:
    aggregate = quality.aggregate_live_quality_eval_summaries(
        [
            _summary(turn_count=2, avg_score=4.0, fun=4.2),
            _summary(turn_count=4, avg_score=3.5, fun=3.7),
        ]
    )

    assert aggregate["aggregate_format_version"] == quality.LIVE_QUALITY_AGGREGATE_VERSION
    assert aggregate["ok"] is True
    assert aggregate["summary_count"] == 2
    assert aggregate["valid_summary_count"] == 2
    assert aggregate["invalid_summary_count"] == 0
    assert aggregate["passed"] == 2
    assert aggregate["failed"] == 0
    assert aggregate["total_turn_count"] == 6
    assert aggregate["scores"]["fun"] == 3.867
    assert aggregate["entries"] == [
        {
            "index": 0,
            "schema_ok": True,
            "quality_ok": True,
            "turn_count": 2,
            "avg_score": 4.0,
            "fun_score": 4.2,
            "failure_count": 0,
            "warning_count": 0,
            "error": "none",
        },
        {
            "index": 1,
            "schema_ok": True,
            "quality_ok": True,
            "turn_count": 4,
            "avg_score": 3.5,
            "fun_score": 3.7,
            "failure_count": 0,
            "warning_count": 0,
            "error": "none",
        },
    ]


def test_phase13_95_aggregate_preserves_quality_failures_and_warnings() -> None:
    aggregate = quality.aggregate_live_quality_eval_summaries([_summary(ok=False, turn_count=3, avg_score=2.5, fun=2.0)])

    assert aggregate["ok"] is False
    assert aggregate["passed"] == 0
    assert aggregate["failed"] == 1
    assert aggregate["failure_types"] == ["average_quality_score_below_threshold"]
    assert aggregate["warning_types"] == ["fun_score_below_target"]
    assert aggregate["entries"] == [
        {
            "index": 0,
            "schema_ok": True,
            "quality_ok": False,
            "turn_count": 3,
            "avg_score": 2.5,
            "fun_score": 2.0,
            "failure_count": 1,
            "warning_count": 1,
            "error": "average_quality_score_below_threshold",
        }
    ]


def test_phase13_95_aggregate_preserves_schema_errors() -> None:
    aggregate = quality.aggregate_live_quality_eval_summaries([{"ok": True}])

    assert aggregate["ok"] is False
    assert aggregate["valid_summary_count"] == 0
    assert aggregate["invalid_summary_count"] == 1
    assert aggregate["failed"] == 1
    assert aggregate["entries"] == [
        {
            "index": 0,
            "schema_ok": False,
            "quality_ok": False,
            "error": "live_quality_summary_required_keys_missing",
            "validation": {
                "ok": False,
                "error": "live_quality_summary_required_keys_missing",
                "missing_keys": ["avg_score", "format_version", "scores", "turn_count"],
            },
        }
    ]
