from __future__ import annotations

from pathlib import Path

from app.rpg.presentation.turn_response import build_turn_response_v2
from app.rpg.session import durable_store
from app.rpg.session.interaction_timeline import (
    MAX_RECENT_INTERACTIONS,
    commit_turn_interaction,
    interaction_events,
)


def _session() -> dict:
    return {
        "manifest": {
            "id": "session:bran",
            "session_id": "session:bran",
            "title": "Rusty Flagon",
            "schema_version": 2,
        },
        "state": {
            "scene": {"location_name": "Rusty Flagon Tavern"},
            "player": {"name": "Elara", "level": 1, "hp": 20},
        },
        "simulation_state": {"tick": 0},
        "runtime_state": {"tick": 0},
        "installed_packs": [],
    }


def _dialogue_result(line: str) -> dict:
    return {
        "ok": True,
        "turn_id": "turn:0",
        "tick": 0,
        "stateful": False,
        "action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "narration": "Bran sets the polishing rag on the counter.",
        "npc": {"id": "npc:bran", "speaker": "Bran", "line": line},
    }


def test_non_stateful_dialogue_advances_interaction_not_simulation_tick() -> None:
    session = _session()

    session, first, first_event = commit_turn_interaction(
        session,
        _dialogue_result("Steady enough, though the road has been quiet."),
        player_input="How is business?",
        submission_id="submit:1",
    )
    session, second, second_event = commit_turn_interaction(
        session,
        _dialogue_result("Quiet, but I have had worse days."),
        player_input="How is your day going?",
        submission_id="submit:2",
    )

    assert first_event["interaction_id"] == "interaction:1"
    assert second_event["interaction_id"] == "interaction:2"
    assert session["runtime_state"]["interaction_seq"] == 2
    assert session["runtime_state"]["state_revision"] == 2
    assert session["simulation_state"]["tick"] == 0
    assert first["interaction_id"] == "interaction:1"
    assert second["interaction_id"] == "interaction:2"
    assert [event["player_input"] for event in interaction_events(session)] == [
        "How is business?",
        "How is your day going?",
    ]


def test_submission_replay_does_not_append_second_interaction() -> None:
    session = _session()
    session, first, _ = commit_turn_interaction(
        session,
        _dialogue_result("Steady enough."),
        player_input="How is business?",
        submission_id="submit:stable",
    )
    session, replay, replay_event = commit_turn_interaction(
        session,
        _dialogue_result("A different answer must not append."),
        player_input="How is business?",
        submission_id="submit:stable",
    )

    assert first["interaction_id"] == replay["interaction_id"] == "interaction:1"
    assert replay["interaction_replay"] is True
    assert replay_event["npc_line"] == "Steady enough."
    assert len(interaction_events(session)) == 1


def test_interaction_timeline_is_bounded() -> None:
    session = _session()
    for index in range(MAX_RECENT_INTERACTIONS + 10):
        session, _, _ = commit_turn_interaction(
            session,
            _dialogue_result(f"Answer {index}"),
            player_input=f"Question {index}",
            submission_id=f"submit:{index}",
        )

    events = interaction_events(session)
    assert len(events) == MAX_RECENT_INTERACTIONS
    assert events[0]["sequence"] == 11
    assert events[-1]["sequence"] == 60
    assert len(session["runtime_state"]["recent_interactions"]) == 12


def test_interaction_timeline_round_trips_through_durable_session_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    session = _session()
    session, result, event = commit_turn_interaction(
        session,
        _dialogue_result("The regulars keep the hearth warm."),
        player_input="How is business?",
        submission_id="submit:persisted",
    )

    durable_store.save_session_to_disk(session, compact=True)
    loaded = durable_store.load_session_from_disk("session:bran")

    assert loaded is not None
    loaded_events = interaction_events(loaded)
    assert loaded_events[-1]["interaction_id"] == event["interaction_id"]
    assert loaded_events[-1]["submission_id"] == "submit:persisted"
    assert loaded["runtime_state"]["interaction_seq"] == 1
    compact = build_turn_response_v2(
        result,
        session_id="session:bran",
        command="How is business?",
        session=loaded,
    )
    assert compact["interaction_id"] == "interaction:1"
    assert compact["state"]["revision"] == 1
