from __future__ import annotations

from pathlib import Path

import pytest

from app.rpg.local_live_smoke import (
    assert_live_smoke_allowed,
    build_smoke_plan,
    evaluate_live_smoke_payload,
)
from app.rpg.release_finalization import (
    INTERACTIVE_RELEASE_VERSION,
    LOCAL_LIVE_SMOKE_ENV,
    PHASE_EVIDENCE,
    assert_release_evidence_ready,
    build_release_evidence_index,
    local_live_acceptance_criteria,
)


def _valid_turn_payload() -> dict:
    return {
        "ok": True,
        "contract_version": "rpg_turn_response_v2",
        "session_id": "session:bran",
        "submission_id": "submit:one",
        "interaction_id": "interaction:1",
        "turn_id": "turn:1",
        "visible_response": {
            "format_version": "rpg_visible_response_v1",
            "narration": "Bran rests the polishing rag on the counter.",
            "messages": [
                {
                    "kind": "npc_dialogue",
                    "speaker_id": "npc:bran",
                    "speaker": "Bran",
                    "text": "Business is steady enough, though the old road has been quiet.",
                }
            ],
            "plain_text": (
                "Bran rests the polishing rag on the counter.\n\n"
                'Bran: "Business is steady enough, though the old road has been quiet."'
            ),
        },
        "response": "Bran answers.",
        "state": {
            "revision": 1,
            "changed": True,
            "changed_domains": ["conversation"],
        },
    }


def test_release_evidence_index_is_complete_and_provider_free() -> None:
    assert_release_evidence_ready()
    index = build_release_evidence_index()

    assert index["format_version"] == INTERACTIVE_RELEASE_VERSION
    assert index["ready_for_operator_validation"] is True
    assert index["completed_phase_count"] == 10
    assert [item["phase"] for item in index["completed_phases"]] == list(range(1, 11))
    assert all(item["provider_free_ci"] is True for item in index["completed_phases"])
    assert len({item.pull_request for item in PHASE_EVIDENCE}) == 10
    assert index["live_provider_validation"]["github_actions_allowed"] is False


def test_local_live_smoke_is_blocked_in_ci() -> None:
    with pytest.raises(RuntimeError, match="must not run in CI"):
        assert_live_smoke_allowed({"CI": "true", LOCAL_LIVE_SMOKE_ENV: "1"})


def test_local_live_smoke_requires_explicit_operator_opt_in() -> None:
    with pytest.raises(RuntimeError, match=LOCAL_LIVE_SMOKE_ENV):
        assert_live_smoke_allowed({"CI": "", LOCAL_LIVE_SMOKE_ENV: "0"})

    assert_live_smoke_allowed({"CI": "", LOCAL_LIVE_SMOKE_ENV: "1"})


def test_smoke_plan_replays_the_same_submission_exactly_once() -> None:
    plan = build_smoke_plan(
        ["First question", "Second question", "Third question"],
        run_id="stable",
    )

    assert len(plan) == 4
    assert len({item.submission_id for item in plan[:-1]}) == 3
    assert plan[-1].submission_id == plan[0].submission_id
    assert plan[-1].command == plan[0].command
    assert plan[-1].replay_of == plan[0].submission_id


def test_live_smoke_payload_uses_permanent_release_gates() -> None:
    report = evaluate_live_smoke_payload(_valid_turn_payload())

    assert report["ok"] is True
    assert report["failures"] == []
    assert report["interaction_id"] == "interaction:1"
    assert 0 < report["response_bytes"] < 50_000


def test_live_smoke_payload_rejects_graph_leaks_and_missing_visible_text() -> None:
    payload = _valid_turn_payload()
    payload["session"] = {"runtime_state": {"private": "must not cross the boundary"}}
    payload["visible_response"] = {"messages": [], "plain_text": ""}
    payload["response"] = ""

    report = evaluate_live_smoke_payload(payload)

    assert report["ok"] is False
    assert "foreground_graph_leak:session" in report["failures"]
    assert "missing_visible_text" in report["failures"]


def test_operator_acceptance_criteria_keep_latency_out_of_provider_free_ci() -> None:
    criteria = local_live_acceptance_criteria()

    assert criteria["required_contract_version"] == "rpg_turn_response_v2"
    assert criteria["maximum_turn_response_bytes"] == 50_000
    assert criteria["target_p95_seconds"] == 5.0
    assert criteria["target_is_operator_evidence_not_ci_assertion"] is True


def test_release_runbook_keeps_live_provider_validation_out_of_actions() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runbook = (repo_root / "docs" / "rpg-interactive-response-release.md").read_text(
        encoding="utf-8"
    )
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((repo_root / ".github" / "workflows").glob("*.y*ml"))
    )

    assert "GitHub Actions must remain provider-free" in runbook
    assert "Do not add it to a GitHub Actions workflow" in runbook
    assert "OMNIX_RPG_LIVE_SMOKE" in runbook
    assert "rpg_interactive_live_smoke.py" not in workflows
    assert "OMNIX_RPG_LIVE_SMOKE" not in workflows
