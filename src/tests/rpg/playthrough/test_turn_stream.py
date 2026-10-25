"""The play screen follows its turn on a stream: the outcome first, the narration after (RQ-6.2; roadmap §4.7)."""
from __future__ import annotations

import json

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


def _followed(play, command: str, submission_id: str) -> dict:
    response = play.client.post(f"/api/rpg/sessions/{play.session_id}/turn", json={"command": command},
                                headers={"x-omnix-rpg-submission-id": submission_id, "x-omnix-rpg-turn-stream": "1"})
    assert response.status_code == 200, response.text[:400]
    return response.json()


def _events(play, submission_id: str, *, after: int | None = None) -> list[tuple[int, str, dict]]:
    path = f"/api/rpg/sessions/{play.session_id}/submissions/{submission_id}/stream"
    events: list[tuple[int, str, dict]] = []
    with play.client.stream("GET", path, params={} if after is None else {"after": after}) as response:
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
        index, name = -1, ""
        for line in response.iter_lines():
            if line.startswith("id: "):
                index = int(line[4:])
            elif line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                events.append((index, name, json.loads(line[6:])))
    return events


def test_a_followed_turn_commits_first_and_streams_its_narration(launch) -> None:
    play = launch("aurelia")
    revision = play.revision()
    body = _followed(play, "look around", "stream-look")
    # The response comes at the commit: the outcome, and the narration still to come.
    assert body["narration"]["status"] == "pending" and body["visible_response"]["status"] == "pending"
    assert body["outcome"]["revision"] == revision + 1
    assert body["outcome"]["model_calls"]["total"] == 0  # the writer runs after the turn has committed
    events = _events(play, "stream-look")
    names = [name for _, name, _ in events]
    assert names[:3] == ["accepted", "committed", "outcome"] and names[-1] == "narration.final", names
    assert set(names[3:-1]) <= {"narration.delta"}
    assert events[2][2]["outcome"]["revision"] == revision + 1
    final = events[-1][2]["visible_response"]
    assert final.get("narration") or final.get("plain_text")
    # Narration is outside the campaign document: the turn was one revision, and reading the campaign finds it.
    assert play.revision() == revision + 1
    shown = play.client.get(f"/api/rpg/sessions/{play.session_id}").json()["session"]
    latest = shown["runtime_state"]["recent_interactions"][-1]
    assert latest["narrative_response_id"] == events[-1][2]["response_id"]
    assert latest["visible_response"]["narration"] == final["narration"]
    # A reconnect resumes after the last event it had.
    assert [name for _, name, _ in _events(play, "stream-look", after=1)] == names[2:]


def test_a_turn_whose_words_are_written_ends_its_stream_at_once(launch) -> None:
    play = launch("aurelia")
    body = _followed(play, "wait", "stream-wait")
    assert "narration" not in body and "You wait a while" in body["visible_response"]["plain_text"]
    names = [name for _, name, _ in _events(play, "stream-wait")]
    assert names == ["accepted", "committed", "outcome", "narration.final"], names


def test_a_narration_that_fails_leaves_the_turn_and_the_stream_says_so(launch, monkeypatch) -> None:
    from app.apps.rpg.session import narrative_engine_bridge

    play = launch("aurelia")
    revision = play.revision()

    def broken(*args, **kwargs):
        raise RuntimeError("the storyteller is down")

    monkeypatch.setattr(narrative_engine_bridge, "canonicalize_resolved_turn_result", broken)
    _followed(play, "look around", "stream-broken")
    events = _events(play, "stream-broken")
    assert [name for _, name, _ in events][-1] == "error" and events[-1][2]["stage"] == "narration"
    assert play.revision() == revision + 1  # the turn stands


def test_a_stream_nobody_took_says_so(launch) -> None:
    play = launch("aurelia")
    assert [name for _, name, _ in _events(play, "never-submitted")] == ["error"]
