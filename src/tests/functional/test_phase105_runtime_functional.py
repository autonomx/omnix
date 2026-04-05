"""Phase 10.5 — Functional tests for runtime layer integration."""
import pytest

from app.rpg.runtime.dialogue_runtime import (
    begin_runtime_turn,
    append_runtime_stream_chunk,
    finalize_runtime_turn,
    mark_runtime_turn_interrupted,
    get_runtime_dialogue_state,
    start_runtime_sequence,
    build_runtime_turn_sequence,
    choose_runtime_interruptions,
    apply_runtime_interruptions,
    stream_runtime_text_segments,
    update_runtime_emotion,
    decay_runtime_emotions,
    get_runtime_emotion,
    build_runtime_style_tags,
    build_runtime_fallback_text,
)
from app.rpg.presentation.runtime_bridge import build_runtime_presentation_payload


class TestPhase105StreamingInterruptionsFunctional:
    """Functional tests for streaming and interruption logic."""

    def test_build_runtime_turn_sequence_orders_player_then_companions_then_npcs(self):
        state = {"player_id": "player:hero"}
        sequence = build_runtime_turn_sequence(
            state,
            companions=[
                {"actor_id": "comp:zane", "speaker_name": "Zane"},
                {"actor_id": "comp:lyra", "speaker_name": "Lyra"},
            ],
            npcs=[
                {"actor_id": "npc:guard_b", "speaker_name": "Guard B"},
                {"actor_id": "npc:guard_a", "speaker_name": "Guard A"},
            ],
        )

        assert [v["actor_id"] for v in sequence] == [
            "player:hero",
            "comp:lyra",
            "comp:zane",
            "npc:guard_a",
            "npc:guard_b",
        ]
        assert [v["sequence_index"] for v in sequence] == [0, 1, 2, 3, 4]

    def test_start_runtime_sequence_seeds_active_sequence_metadata(self):
        state = {"player_id": "player:hero"}
        state = start_runtime_sequence(
            state,
            tick=100,
            sequence_index=2,
            companions=[{"actor_id": "comp:lyra"}],
            npcs=[{"actor_id": "npc:guard"}],
        )

        dialogue = get_runtime_dialogue_state(state)
        assert dialogue["active_sequence_id"] == "seq:100:2"
        assert dialogue["sequence_tick"] == 100
        assert dialogue["active_turn_id"] == ""
        assert dialogue["turn_cursor"] == 0
        assert [v["actor_id"] for v in dialogue["sequence_participants"]] == [
            "player:hero",
            "comp:lyra",
            "npc:guard",
        ]

    def test_choose_runtime_interruptions_is_deterministic_and_bounded(self):
        state = {"player_id": "player:hero"}
        state = start_runtime_sequence(
            state,
            tick=110,
            companions=[
                {"actor_id": "comp:lyra", "interrupt_priority": 2, "interjection_score": 1},
                {"actor_id": "comp:zane", "interrupt_priority": 1, "interjection_score": 0},
            ],
            npcs=[
                {"actor_id": "npc:guard", "interrupt_priority": 3, "interjection_score": 0},
            ],
        )
        state = begin_runtime_turn(
            state,
            tick=110,
            sequence_index=3,
            actor_id="npc:guard",
            speaker_id="npc:guard",
            speaker_name="Guard",
            role="npc",
            sequence_id="seq:110:0",
        )

        dialogue = get_runtime_dialogue_state(state)
        candidates = choose_runtime_interruptions(
            state,
            active_turn_id="turn:110:3:npc:guard",
            sequence=dialogue["sequence_participants"],
            context={"threat": True},
        )

        assert len(candidates) <= 2
        assert [v["actor_id"] for v in candidates] == ["comp:lyra", "comp:zane"]
        assert all(v["target_id"] == "npc:guard" for v in candidates)
        assert all(v["reason"] == "protective_reaction" for v in candidates)

    def test_apply_runtime_interruptions_persists_pending_candidates(self):
        state = {}
        state = apply_runtime_interruptions(
            state,
            candidates=[
                {
                    "actor_id": "comp:zane",
                    "target_id": "npc:guard",
                    "reason": "runtime_interjection",
                    "priority": 1,
                },
                {
                    "actor_id": "comp:lyra",
                    "target_id": "npc:guard",
                    "reason": "runtime_interjection",
                    "priority": 3,
                },
            ],
        )

        dialogue = get_runtime_dialogue_state(state)
        assert [v["actor_id"] for v in dialogue["pending_interruptions"]] == [
            "comp:lyra",
            "comp:zane",
        ]

    def test_stream_runtime_text_segments_appends_chunks_and_finalizes(self):
        state = {}
        state = begin_runtime_turn(
            state,
            tick=120,
            sequence_index=1,
            actor_id="comp:lyra",
            speaker_id="comp:lyra",
            speaker_name="Lyra",
            role="companion",
            sequence_id="seq:120:0",
        )
        state = stream_runtime_text_segments(
            state,
            turn_id="turn:120:1:comp:lyra",
            actor_id="comp:lyra",
            speaker_id="comp:lyra",
            segments=["We ", "should ", "go."],
            finalize=True,
        )

        dialogue = get_runtime_dialogue_state(state)
        turn = dialogue["turns"][0]
        assert turn["text"] == "We should go."
        assert turn["status"] == "complete"
        assert len(turn["chunks"]) == 3
        assert dialogue["stream"]["active"] is False


class TestPhase105EmotionalContinuityFunctional:
    """Functional tests for emotional continuity."""

    def test_update_runtime_emotion_persists_normalized_entry(self):
        state = {}
        state = update_runtime_emotion(
            state,
            actor_id="comp:lyra",
            emotion="tense",
            intensity=0.8,
            tick=100,
        )

        emotion = get_runtime_emotion(state, "comp:lyra")
        assert emotion["actor_id"] == "comp:lyra"
        assert emotion["emotion"] == "tense"
        assert emotion["intensity"] == 0.8
        assert emotion["updated_tick"] == 100

    def test_decay_runtime_emotions_reduces_intensity_by_tick_delta(self):
        state = {}
        state = update_runtime_emotion(
            state,
            actor_id="comp:lyra",
            emotion="tense",
            intensity=0.8,
            tick=100,
        )
        state = decay_runtime_emotions(
            state,
            tick=102,
        )

        emotion = get_runtime_emotion(state, "comp:lyra")
        assert emotion["emotion"] == "tense"
        assert round(emotion["intensity"], 2) == 0.50
        assert emotion["updated_tick"] == 102

    def test_decay_runtime_emotions_returns_to_neutral_when_low(self):
        state = {}
        state = update_runtime_emotion(
            state,
            actor_id="npc:guard",
            emotion="stern",
            intensity=0.2,
            tick=50,
        )
        state = decay_runtime_emotions(
            state,
            tick=51,
        )

        emotion = get_runtime_emotion(state, "npc:guard")
        assert emotion["emotion"] == "neutral"
        assert emotion["intensity"] == 0.0
        assert emotion["updated_tick"] == 51

    def test_build_runtime_style_tags_overlays_emotion_tag(self):
        state = {}
        state = update_runtime_emotion(
            state,
            actor_id="comp:lyra",
            emotion="supportive",
            intensity=0.9,
            tick=10,
        )

        tags = build_runtime_style_tags(
            state,
            actor_id="comp:lyra",
            base_tags=["gentle", "measured"],
        )
        assert tags == ["emotion:supportive", "gentle", "measured"]

    def test_build_runtime_fallback_text_depends_on_emotion(self):
        state = {}
        state = update_runtime_emotion(
            state,
            actor_id="comp:lyra",
            emotion="wary",
            intensity=0.7,
            tick=10,
        )

        text = build_runtime_fallback_text(
            state,
            actor_id="comp:lyra",
            base_text="",
        )
        assert text == "Something feels off."

    def test_finalize_runtime_turn_uses_emotional_fallback_when_text_empty(self):
        state = {}
        state = update_runtime_emotion(
            state,
            actor_id="comp:lyra",
            emotion="supportive",
            intensity=0.6,
            tick=200,
        )
        state = begin_runtime_turn(
            state,
            tick=200,
            sequence_index=1,
            actor_id="comp:lyra",
            speaker_id="comp:lyra",
            speaker_name="Lyra",
            role="companion",
            sequence_id="seq:200:0",
        )
        state = finalize_runtime_turn(
            state,
            turn_id="turn:200:1:comp:lyra",
        )

        dialogue = get_runtime_dialogue_state(state)
        turn = dialogue["turns"][0]
        assert turn["status"] == "complete"
        assert turn["text"] == "We can handle this together."
        assert turn["emotion"] == "supportive"