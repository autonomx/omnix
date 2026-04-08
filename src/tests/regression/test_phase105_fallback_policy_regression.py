"""Phase 10.5 — Fallback policy regression tests.

Verifies that finalize_runtime_turn and mark_runtime_turn_interrupted
do NOT invent text by default, only when explicitly enabled.
"""
import pytest

from app.rpg.runtime.dialogue_runtime import (
    begin_runtime_turn,
    finalize_runtime_turn,
    get_runtime_dialogue_state,
    mark_runtime_turn_interrupted,
    update_runtime_emotion,
)


def test_phase105_finalize_runtime_turn_does_not_invent_text_by_default():
    state = {}
    state = update_runtime_emotion(
        state,
        actor_id="comp:lyra",
        emotion="supportive",
        intensity=0.8,
        tick=10,
    )
    state = begin_runtime_turn(
        state,
        tick=10,
        sequence_index=1,
        actor_id="comp:lyra",
        speaker_id="comp:lyra",
        speaker_name="Lyra",
        role="companion",
        sequence_id="seq:10:0",
    )
    state = finalize_runtime_turn(
        state,
        turn_id="turn:10:1:comp:lyra",
    )

    dialogue = get_runtime_dialogue_state(state)
    turn = dialogue["turns"][0]
    assert turn["status"] == "complete"
    assert turn["text"] == ""


def test_phase105_finalize_runtime_turn_can_use_emotional_fallback_when_explicitly_enabled():
    state = {}
    state = update_runtime_emotion(
        state,
        actor_id="comp:lyra",
        emotion="supportive",
        intensity=0.8,
        tick=10,
    )
    state = begin_runtime_turn(
        state,
        tick=10,
        sequence_index=1,
        actor_id="comp:lyra",
        speaker_id="comp:lyra",
        speaker_name="Lyra",
        role="companion",
        sequence_id="seq:10:0",
    )
    state = finalize_runtime_turn(
        state,
        turn_id="turn:10:1:comp:lyra",
        allow_emotional_fallback=True,
    )

    dialogue = get_runtime_dialogue_state(state)
    turn = dialogue["turns"][0]
    assert turn["text"] == "We can handle this together."


def test_phase105_interrupted_turn_does_not_invent_text_by_default():
    state = {}
    state = begin_runtime_turn(
        state,
        tick=11,
        sequence_index=1,
        actor_id="npc:guard",
        speaker_id="npc:guard",
        speaker_name="Guard",
        role="npc",
        sequence_id="seq:11:0",
    )
    state = mark_runtime_turn_interrupted(
        state,
        turn_id="turn:11:1:npc:guard",
        interrupt_actor_id="comp:lyra",
        reason="protective_reaction",
    )

    dialogue = get_runtime_dialogue_state(state)
    turn = dialogue["turns"][0]
    assert turn["status"] == "interrupted"
    assert turn["text"] == ""