"""A turn's reply over its byte budget keeps what the play screen reads (the playtest: a journey's reply, 52 KB, came
back without its outcome, so no card and no suggestions)."""
from __future__ import annotations

from app.apps.rpg.foundation.state.changes import LocationChanged, MapStateProjected
from app.apps.rpg.narration.presentation.outcome_facts import OutcomeFact, Suggestion
from app.apps.rpg.narration.presentation.turn_outcome import ModelCalls, PresentationHints, TurnOutcome
from app.apps.rpg.narration.presentation.turn_response_budget import encoded_size_bytes, enforce_turn_response_budget

SUGGESTIONS = tuple(Suggestion(label=f"Go to Place {number}", command=f"go to Place {number}") for number in range(6))


def _reply(bulk: int) -> dict:
    outcome = TurnOutcome(
        turn_id="turn:7", planned_action="travel",
        applied_changes=(LocationChanged(location_id="location:pass", location_name="Skybridge Pass"),
                         MapStateProjected(map_state={"cells": "z" * bulk}, location_id="location:pass")),
        presentation=PresentationHints(changed_sections=("location",), location_name="Skybridge Pass",
                                       facts=(OutcomeFact(kind="item", text="+Radio", tone="gain"),),
                                       suggestions=SUGGESTIONS),
        model_calls=ModelCalls(total=1, by_kind={"narrative_writer": 1}))
    return {
        "session_id": "session:1", "submission_id": "submission:1", "response": "You set out along the road.",
        "content": "You set out along the road.",
        "narrative_projections": {"bulk": "x" * bulk}, "narrative_engine_shadow": {"bulk": "y" * bulk},
        "outcome": outcome.model_dump(mode="json"),
        "state": {"location_name": "Skybridge Pass"},
    }


def test_a_reply_inside_its_budget_is_untouched() -> None:
    reply = _reply(100)
    assert enforce_turn_response_budget(reply, max_bytes=50_000) is reply


def test_an_oversized_reply_drops_what_is_unread_and_keeps_its_outcome() -> None:
    reply = _reply(20_000)
    kept = enforce_turn_response_budget(reply, max_bytes=20_000)
    assert encoded_size_bytes(kept) <= 20_000
    assert "narrative_projections" not in kept and "narrative_engine_shadow" not in kept
    outcome = TurnOutcome.model_validate(kept["outcome"])  # still the outcome's contract
    assert outcome.planned_action == "travel" and outcome.model_calls.total == 1
    assert outcome.presentation == TurnOutcome.model_validate(reply["outcome"]).presentation  # the card, whole
    assert outcome.applied_changes == ()  # a change's own state is its bulk; it is whole or absent


def test_the_last_resort_fallback_still_carries_the_outcome() -> None:
    reply = _reply(20_000)
    reply["visible_response"] = {"narration": "n" * 30_000}  # compacted, still over: the fallback's turn
    kept = enforce_turn_response_budget(reply, max_bytes=30_000)
    assert kept["response_budget"]["fallback"] is True and encoded_size_bytes(kept) <= 30_000
    assert TurnOutcome.model_validate(kept["outcome"]).presentation.suggestions == SUGGESTIONS
