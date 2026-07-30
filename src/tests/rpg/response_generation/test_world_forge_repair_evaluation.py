from __future__ import annotations

import app.rpg.worlds.generation_repair_evaluation as repair_evaluation
from app.rpg.worlds.generation_contract_bundle import CONTRACT_VERSION
from app.rpg.worlds.generation_repair_evaluation import (
    consecutive_no_op_count,
    evaluate_retry_repair,
    finding_fingerprint,
)
from app.rpg.worlds.generation_review_state import review_state


def _issue(
    code: str = "dangling_entity_ref",
    *,
    field: str = "group_ids",
    value: object = "ent:groups:[MegaCorps]",
) -> dict:
    return {
        "code": code,
        "topic_id": "actors",
        "entity_id": "ent:actor:004",
        "field_id": field,
        "message": "Invalid generated value.",
        "supplied_value": value,
    }


def _result(
    run_id: str,
    candidate_hash: str,
    issues: list[dict],
    previous_result: dict | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "topic_id": "actors",
        "status": "needs_review" if issues else "accepted",
        "candidate_hash": candidate_hash,
        "validation": {
            "status": "needs_review" if issues else "accepted",
            "blocking": bool(issues),
            "reason_codes": sorted({str(issue["code"]) for issue in issues}),
            "issues": issues,
        },
        "provider": {
            "attempt_count": 1,
            "strategy_identity": "sha256:current-strategy",
            "contract_descriptor": {"contract_version": CONTRACT_VERSION},
        },
        "job_id": f"job:{run_id}",
        "previous_result": previous_result,
    }


def test_finding_fingerprint_is_stable_for_structured_values() -> None:
    left = finding_fingerprint(_issue(value={"b": 2, "a": 1}))
    right = finding_fingerprint(_issue(value={"a": 1, "b": 2}))

    assert left == right
    assert left["bad_value"] == '{"a":1,"b":2}'


def test_retry_is_no_op_when_targeted_finding_remains() -> None:
    previous = _result("run:1", "sha256:first", [_issue()])
    current = _result("run:2", "sha256:changed", [_issue()])

    evaluation = evaluate_retry_repair(previous, current)

    assert evaluation["outcome"] == "no_op"
    assert evaluation["candidate_changed"] is True
    assert evaluation["remaining_finding_count"] == 1
    assert evaluation["repaired_finding_count"] == 0


def test_retry_is_repaired_when_original_finding_disappears() -> None:
    previous = _result("run:1", "sha256:first", [_issue()])
    current = _result("run:2", "sha256:second", [])

    evaluation = evaluate_retry_repair(previous, current)

    assert evaluation["outcome"] == "repaired"
    assert evaluation["repaired_finding_count"] == 1
    assert evaluation["remaining_finding_count"] == 0


def test_retry_is_partial_when_one_original_finding_remains() -> None:
    previous = _result(
        "run:1",
        "sha256:first",
        [_issue(), _issue("weak_operational_state", field="next_action", value="soon")],
    )
    current = _result("run:2", "sha256:second", [_issue()])

    evaluation = evaluate_retry_repair(previous, current)

    assert evaluation["outcome"] == "partially_repaired"
    assert evaluation["repaired_finding_count"] == 1
    assert evaluation["remaining_finding_count"] == 1


def test_retry_reports_replacement_with_new_failure() -> None:
    previous = _result("run:1", "sha256:first", [_issue()])
    current = _result(
        "run:2",
        "sha256:second",
        [_issue("weak_operational_state", field="next_action", value="soon")],
    )

    evaluation = evaluate_retry_repair(previous, current)

    assert evaluation["outcome"] == "replaced_with_new_failure"
    assert evaluation["repaired_finding_count"] == 1
    assert evaluation["introduced_finding_count"] == 1


def test_review_state_exhausts_budget_after_two_consecutive_no_ops() -> None:
    first = _result("run:1", "sha256:first", [_issue()])
    second = _result("run:2", "sha256:second", [_issue()], first)
    third = _result("run:3", "sha256:third", [_issue()], second)

    state = review_state(third)

    assert state["repair_evaluation"]["outcome"] == "no_op"
    assert state["consecutive_no_op_count"] == 2
    assert state["retry_budget_exhausted"] is True
    assert state["attempt_count"] == 3


def test_successful_repair_resets_consecutive_no_op_count() -> None:
    first = _result("run:1", "sha256:first", [_issue()])
    second = _result("run:2", "sha256:second", [_issue()], first)
    third = _result("run:3", "sha256:third", [], second)

    state = review_state(third)

    assert state["repair_evaluation"]["outcome"] == "repaired"
    assert state["consecutive_no_op_count"] == 0
    assert state["retry_budget_exhausted"] is False


def test_legacy_attempts_without_strategy_identity_do_not_consume_retry_budget() -> None:
    first = _result("run:1", "sha256:first", [_issue()])
    second = _result("run:2", "sha256:second", [_issue()], first)
    third = _result("run:3", "sha256:third", [_issue()], second)
    for result in (first, second, third):
        result["provider"].pop("strategy_identity")

    state = review_state(third)

    assert state["repair_evaluation"]["outcome"] == "no_op"
    assert state["consecutive_no_op_count"] == 0
    assert state["retry_budget_exhausted"] is False


def test_retry_gate_does_not_count_incomparable_legacy_lineage(monkeypatch) -> None:
    first = _result("run:1", "sha256:first", [_issue()])
    second = _result("run:2", "sha256:second", [_issue()], first)
    third = _result("run:3", "sha256:third", [_issue()], second)
    for result in (first, second, third):
        result["provider"].pop("strategy_identity")
    monkeypatch.setattr(
        repair_evaluation,
        "_result_chain",
        lambda *_args, **_kwargs: [third, second, first],
    )

    assert consecutive_no_op_count("run:3", "actors") == 0


def test_retry_gate_counts_only_matching_known_strategy(monkeypatch) -> None:
    first = _result("run:1", "sha256:first", [_issue()])
    second = _result("run:2", "sha256:second", [_issue()], first)
    third = _result("run:3", "sha256:third", [_issue()], second)
    monkeypatch.setattr(
        repair_evaluation,
        "_result_chain",
        lambda *_args, **_kwargs: [third, second, first],
    )

    assert consecutive_no_op_count("run:3", "actors") == 2


def test_retry_gate_resets_pre_current_contract_lineage(monkeypatch) -> None:
    first = _result("run:1", "sha256:first", [_issue()])
    second = _result("run:2", "sha256:second", [_issue()], first)
    third = _result("run:3", "sha256:third", [_issue()], second)
    for result in (first, second, third):
        result["provider"]["contract_descriptor"]["contract_version"] = (
            "world-topic-authored-draft-v1"
        )
    monkeypatch.setattr(
        repair_evaluation,
        "_result_chain",
        lambda *_args, **_kwargs: [third, second, first],
    )

    assert consecutive_no_op_count("run:3", "actors") == 0
