from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any

from app.gateway.rpg_turn_job_mirror import _apply_turn_with_job_mirror
from app.jobs.store import InMemoryJobStore
from app.rpg.presentation.dialogue_quality import enforce_dialogue_quality
from app.rpg.presentation.turn_response import build_turn_response_v2
from app.rpg.presentation.visible_response import visible_response_text
from app.rpg.release_gates import (
    assert_release_gate,
    evaluate_job_transition_release_gates,
    evaluate_session_release_gates,
    evaluate_turn_response_release_gates,
)
from app.rpg.session.interaction_lifecycle import initialize_interaction_lifecycle
from app.rpg.session.interaction_timeline import commit_turn_interaction, interaction_events


def _session() -> dict[str, Any]:
    return {
        "manifest": {
            "id": "session:release",
            "session_id": "session:release",
            "title": "Rusty Flagon",
            "schema_version": 2,
        },
        "state": {
            "scene": {"location_name": "Rusty Flagon Tavern"},
            "player": {"name": "Elara", "level": 1, "hp": 20},
        },
        "simulation_state": {
            "tick": 0,
            "npc_index": {
                "npc:bran": {
                    "id": "npc:bran",
                    "npc_id": "npc:bran",
                    "name": "Bran",
                    "biography": {
                        "public": "Bran owns the Rusty Flagon near the old road and once guarded caravans.",
                        "private": "Bran left a wounded caravan friend behind during an ambush.",
                    },
                    "personality": {
                        "values": ["survival", "plain speech", "earned loyalty"],
                        "speech_style": "Plain, direct, road-worn advice.",
                    },
                }
            },
        },
        "runtime_state": {"tick": 0},
        "installed_packs": [],
    }


def _dialogue_result(line: str = "Fine.") -> dict[str, Any]:
    return {
        "ok": True,
        "turn_id": "turn:0",
        "tick": 0,
        "stateful": False,
        "action_type": "npc_interpretive_dialogue",
        "semantic_action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "narration": "Bran looks up with a tired but genuine smile.",
        "npc": {"id": "npc:bran", "speaker": "Bran", "line": line},
    }


def test_release_gate_exactly_once_under_concurrent_duplicate_submissions(monkeypatch: Any, tmp_path: Path) -> None:
    store = InMemoryJobStore(tmp_path / "jobs")
    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: store)
    calls = 0
    call_lock = Lock()

    def apply_turn(session_id: str, command: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        with call_lock:
            calls += 1
        return {
            "ok": True,
            "turn_id": "turn:1",
            "interaction_id": "interaction:1",
            "final_narration": "Bran answers.",
        }

    def submit(_: int) -> dict[str, Any]:
        return _apply_turn_with_job_mirror(
            apply_turn,
            "session:release",
            "How is business?",
            submission_id="submit:concurrent",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(16)))

    assert calls == 1
    assert {result["interaction_id"] for result in results} == {"interaction:1"}
    assert len(store.list_jobs()) == 1


def test_release_gate_100_mixed_interactions_are_monotonic_bounded_and_provider_free() -> None:
    session = _session()
    for index in range(1, 101):
        stateful = index % 5 == 0
        result = {
            "ok": True,
            "turn_id": f"turn:{index // 5}",
            "tick": index // 5,
            "stateful": stateful,
            "action_type": "trade" if stateful else "npc_interpretive_dialogue",
            "semantic_family": "trade" if stateful else "social",
            "narration": "You exchange a coin." if stateful else "Bran considers the question.",
            "npc": {} if stateful else {
                "id": "npc:bran",
                "speaker": "Bran",
                "line": f"A grounded answer for interaction {index}, with road and tavern context.",
            },
        }
        session, result, _ = commit_turn_interaction(
            session,
            result,
            player_input=f"Player action {index}",
            submission_id=f"submit:{index}",
        )
        initialize_interaction_lifecycle(session, result)

    events = interaction_events(session)
    assert len(events) == 50
    assert [event["sequence"] for event in events] == list(range(51, 101))
    assert session["runtime_state"]["interaction_seq"] == 100
    assert_release_gate(evaluate_session_release_gates(session))


def test_release_gate_compact_response_matches_canonical_formatter_and_stays_under_budget() -> None:
    session = _session()
    result = _dialogue_result(
        "Business is steady enough to keep the hearth warm, though the road traffic has thinned this week."
    )
    session, result, _ = commit_turn_interaction(
        session,
        result,
        player_input="I ask Bran how business is doing.",
        submission_id="submit:response",
    )
    payload = build_turn_response_v2(
        result,
        session_id="session:release",
        command="I ask Bran how business is doing.",
        session=session,
    )

    assert payload["response"] == visible_response_text(result, "I ask Bran how business is doing.")
    report = evaluate_turn_response_release_gates(payload)
    assert report["response_bytes"] < 50_000
    assert_release_gate(report)


def test_release_gate_dialogue_privacy_and_quality_repair() -> None:
    session = _session()
    weak = _dialogue_result(
        "Business is fine, but I left a wounded caravan friend behind during an ambush."
    )
    weak["session"] = deepcopy(session)

    repaired = enforce_dialogue_quality(
        weak,
        session=session,
        player_input="I ask Bran how business is doing.",
    )
    text = f"{repaired['final_narration']} {repaired['npc']['line']}".casefold()

    assert repaired["dialogue_quality"]["repaired"] is True
    assert repaired["dialogue_quality"]["acceptable"] is True
    assert "wounded caravan friend" not in text
    assert repaired["npc"]["speaker"] == "Bran"


def test_release_gate_terminal_jobs_never_reopen() -> None:
    assert_release_gate(
        evaluate_job_transition_release_gates(["queued", "running", "completed"])
    )
    bad = evaluate_job_transition_release_gates(
        ["queued", "running", "completed", "running", "completed"]
    )
    assert bad["ok"] is False
    assert "terminal_job_reopened" in bad["failures"]
    assert "job_completed_more_than_once" in bad["failures"]


def test_release_gate_rejects_full_runtime_graph_in_foreground_contract() -> None:
    payload = {
        "ok": True,
        "contract_version": "rpg_turn_response_v2",
        "interaction_id": "interaction:1",
        "visible_response": {"plain_text": "Visible.", "messages": []},
        "state": {"changed_domains": []},
        "session": {"huge": True},
    }
    report = evaluate_turn_response_release_gates(payload)
    assert report["ok"] is False
    assert any(value.startswith("foreground_graph_leak:session") for value in report["failures"])
