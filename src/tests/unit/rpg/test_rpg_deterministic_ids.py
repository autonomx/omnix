"""Decision streams and record ids replay identically within a turn (RQ-4.6)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.apps.rpg.foundation.core.determinism import deterministic_rng, next_turn_id
from app.apps.rpg.narration.narrative.event_injector import EventInjector
from app.apps.rpg.rules.choice.choice_models import PlayerChoice
from app.apps.rpg.rules.quest.quest_models import Quest
from app.runtime.clock import SYSTEM_CLOCK, TurnContext, bind_turn_context

_NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def _turn(turn_index: int = 4) -> TurnContext:
    return TurnContext(clock=SYSTEM_CLOCK, now=_NOW, session_seed=99, turn_index=turn_index, session_id="rpg_session")


def _created_in_a_turn(turn_index: int = 4) -> tuple[list[str], float, list[float]]:
    with bind_turn_context(_turn(turn_index)):
        ids = [Quest().id, Quest().id, PlayerChoice().id]
        created_at = PlayerChoice().created_at
        draws = [deterministic_rng("test.decision", {"npc": "liora"}).random() for _ in range(2)]
    return ids, created_at, draws


def test_a_turn_creates_the_same_ids_and_draws_the_same_numbers_when_replayed() -> None:
    first = _created_in_a_turn()
    replayed = _created_in_a_turn()

    assert first == replayed
    ids, created_at, draws = first
    assert len(set(ids)) == 3  # two quests in one turn do not share an id
    assert created_at == _NOW.timestamp()  # the turn's recorded time, not the wall clock
    assert draws[0] == draws[1]  # one named decision, one stream


def test_another_turn_gets_other_ids() -> None:
    assert _created_in_a_turn(4)[0] != _created_in_a_turn(5)[0]


def test_outside_a_turn_streams_are_fixed_by_purpose_and_subject() -> None:
    assert deterministic_rng("test.decision", {"a": 1}).random() == deterministic_rng("test.decision", {"a": 1}).random()
    assert deterministic_rng("test.decision", {"a": 1}).random() != deterministic_rng("test.decision", {"a": 2}).random()
    assert next_turn_id("test.outside") != next_turn_id("test.outside")


def test_injected_story_events_replay_with_the_turn() -> None:
    class _Story:
        phase = "rising"

    with bind_turn_context(_turn()):
        first = [EventInjector().inject(_Story(), world={}) for _ in range(3)]
    with bind_turn_context(_turn()):
        replayed = [EventInjector().inject(_Story(), world={}) for _ in range(3)]

    assert first == replayed
