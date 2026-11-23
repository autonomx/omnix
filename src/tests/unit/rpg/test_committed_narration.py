"""A committed turn's narration owns its steps and refusals; the edge builds the turn's request once."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.apps.rpg.edge.api.turn_pipeline import turn_request
from app.apps.rpg.narration.narrative_engine import DeliveryMode
from app.apps.rpg.session.committed_narration import NarrationRefused, narrate_committed_turn


def test_a_replay_of_another_campaigns_narration_is_refused_with_the_detail_the_client_reads() -> None:
    replay = {"ok": True, "idempotent_replay": True, "canonical_narrative": {
        "response_id": "response:1", "content_hash": "hash", "campaign_id": "session:other", "turn_id": "turn:1"}}

    with pytest.raises(NarrationRefused) as refused:
        narrate_committed_turn(replay, session_id="session:mine", command="look", delivery_mode=DeliveryMode.BLOCKING)

    assert refused.value.status_code == 409
    assert refused.value.detail["error"] == "canonical_narrative_replay_mismatch"
    assert refused.value.detail["session_id"] == "session:mine"
    assert "session:other" in refused.value.detail["message"]
    assert not isinstance(refused.value, HTTPException)  # HTTP is the edge's translation


def test_the_turn_request_names_its_kind_and_a_submission_once() -> None:
    tick = turn_request(session_id="session:a", command="", submission_id=" submit:named ",
                        action={"turn_kind": "world_tick", "ticks": 2})
    assert (tick.kind, tick.submission_id, tick.action["ticks"]) == ("world_tick", "submit:named", 2)

    typed = turn_request(session_id="session:a", command="look around")
    assert typed.kind == "player_text"
    assert typed.text == "look around"
    assert typed.submission_id.startswith("submit:")
    assert typed.submission_id != turn_request(session_id="session:a", command="look around").submission_id
