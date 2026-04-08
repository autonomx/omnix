"""Phase 10.5 — Unit tests for runtime models and mutators."""
import pytest

from app.rpg.runtime.dialogue_runtime import (
    _dedupe_and_sort_global_stream_chunks,
    _dedupe_and_sort_turn_chunks,
    _normalize_emotion_entry,
    _normalize_emotion_name,
    _normalize_interruption_candidate,
    _normalize_sequence_actor,
    _rebuild_turn_text_from_chunks,
    _role_precedence,
    _sort_key_interruption_candidate,
    append_runtime_stream_chunk,
    apply_runtime_interruptions,
    begin_runtime_turn,
    build_runtime_fallback_text,
    build_runtime_sequence_id,
    build_runtime_style_tags,
    build_runtime_turn_id,
    build_runtime_turn_sequence,
    choose_runtime_interruptions,
    decay_runtime_emotions,
    ensure_runtime_state,
    finalize_runtime_turn,
    get_runtime_dialogue_state,
    get_runtime_emotion,
    mark_runtime_turn_interrupted,
    start_runtime_sequence,
    stream_runtime_text_segments,
    trim_runtime_state,
    update_runtime_emotion,
)


class TestPhase105RuntimeStateCreation:
    """Unit tests for runtime state creation and normalization."""

    def test_runtime_state_is_created_and_normalized(self):
        state = ensure_runtime_state({})
        dialogue = get_runtime_dialogue_state(state)

        assert "runtime_state" in state
        assert "dialogue" in state["runtime_state"]
        assert dialogue["active_sequence_id"] == ""
        assert dialogue["active_turn_id"] == ""
        assert dialogue["sequence_tick"] == 0
        assert dialogue["turn_cursor"] == 0
        assert dialogue["turns"] == []
        assert dialogue["pending_interruptions"] == []
        assert dialogue["interruption_log"] == []
        assert dialogue["stream"]["active"] is False
        assert dialogue["stream"]["active_turn_id"] == ""
        assert dialogue["stream"]["chunks"] == []
        assert dialogue["emotions"] == {}

    def test_runtime_ids_are_deterministic(self):
        assert build_runtime_sequence_id(12, 3) == "seq:12:3"
        assert build_runtime_turn_id(12, 3, "npc:guard") == "turn:12:3:npc:guard"

    def test_runtime_state_is_bounded(self):
        raw_turns = []
        for i in range(30):
            raw_turns.append({
                "turn_id": f"turn:7:{i}:npc:{i}",
                "sequence_id": "seq:7:0",
                "tick": 7,
                "sequence_index": i,
                "actor_id": f"npc:{i}",
                "speaker_id": f"npc:{i}",
                "speaker_name": f"NPC {i}",
                "role": "npc",
                "text": f"line {i}",
                "status": "complete",
                "emotion": "neutral",
                "interruption": False,
                "interrupt_target_id": "",
                "chunks": [],
            })

        state = ensure_runtime_state({
            "runtime_state": {
                "dialogue": {
                    "turns": raw_turns,
                }
            }
        })
        dialogue = get_runtime_dialogue_state(state)
        assert len(dialogue["turns"]) == 20
        assert dialogue["turns"][0]["sequence_index"] == 10
        assert dialogue["turns"][-1]["sequence_index"] == 29

    def test_runtime_emotion_defaults_to_neutral(self):
        state = ensure_runtime_state({})
        emotion = get_runtime_emotion(state, "comp:lyra")
        assert emotion == {
            "actor_id": "comp:lyra",
            "emotion": "neutral",
            "intensity": 0.0,
            "updated_tick": 0,
        }


class TestPhase105RuntimeMutators:
    """Unit tests for runtime mutator functions."""

    def test_begin_runtime_turn_creates_pending_turn(self):
        state = {}
        state = begin_runtime_turn(
            state,
            tick=15,
            sequence_index=1,
            actor_id="comp:lyra",
            speaker_id="comp:lyra",
            speaker_name="Lyra",
            role="companion",
            sequence_id="seq:15:0",
        )

        dialogue = get_runtime_dialogue_state(state)
        assert dialogue["active_sequence_id"] == "seq:15:0"
        assert dialogue["active_turn_id"] == "turn:15:1:comp:lyra"
        assert dialogue["sequence_tick"] == 15
        assert dialogue["turn_cursor"] == 1
        assert dialogue["stream"]["active"] is True
        assert dialogue["stream"]["active_turn_id"] == "turn:15:1:comp:lyra"
        assert len(dialogue["turns"]) == 1

        turn = dialogue["turns"][0]
        assert turn["turn_id"] == "turn:15:1:comp:lyra"
        assert turn["status"] == "pending"
        assert turn["emotion"] == "neutral"
        assert turn["chunks"] == []

    def test_append_runtime_stream_chunk_updates_turn_and_global_stream(self):
        state = {}
        state = begin_runtime_turn(
            state,
            tick=20,
            sequence_index=2,
            actor_id="npc:guard",
            speaker_id="npc:guard",
            speaker_name="Guard",
            role="npc",
            sequence_id="seq:20:0",
        )

        state = append_runtime_stream_chunk(
            state,
            turn_id="turn:20:2:npc:guard",
            actor_id="npc:guard",
            speaker_id="npc:guard",
            text="Hold ",
            chunk_index=0,
            final=False,
        )
        state = append_runtime_stream_chunk(
            state,
            turn_id="turn:20:2:npc:guard",
            actor_id="npc:guard",
            speaker_id="npc:guard",
            text="there.",
            chunk_index=1,
            final=False,
        )

        dialogue = get_runtime_dialogue_state(state)
        turn = dialogue["turns"][0]

        assert turn["status"] == "streaming"
        assert turn["text"] == "Hold there."
        assert len(turn["chunks"]) == 2
        assert len(dialogue["stream"]["chunks"]) == 2
        assert dialogue["stream"]["active"] is True
        assert dialogue["stream"]["active_turn_id"] == "turn:20:2:npc:guard"

    def test_append_runtime_stream_chunk_dedupes_by_turn_id_chunk_index_actor(self):
        state = {}
        state = begin_runtime_turn(
            state,
            tick=22,
            sequence_index=0,
            actor_id="npc:guard",
            speaker_id="npc:guard",
            speaker_name="Guard",
            role="npc",
            sequence_id="seq:22:0",
        )

        state = append_runtime_stream_chunk(
            state,
            turn_id="turn:22:0:npc:guard",
            actor_id="npc:guard",
            text="Old",
            chunk_index=0,
        )
        state = append_runtime_stream_chunk(
            state,
            turn_id="turn:22:0:npc:guard",
            actor_id="npc:guard",
            text="New",
            chunk_index=0,
        )

        dialogue = get_runtime_dialogue_state(state)
        turn = dialogue["turns"][0]
        assert len(turn["chunks"]) == 1
        assert turn["chunks"][0]["text"] == "New"
        assert turn["text"] == "New"

    def test_finalize_runtime_turn_marks_complete_and_stops_stream(self):
        state = {}
        state = begin_runtime_turn(
            state,
            tick=30,
            sequence_index=3,
            actor_id="comp:lyra",
            speaker_id="comp:lyra",
            speaker_name="Lyra",
            role="companion",
            sequence_id="seq:30:0",
        )
        state = append_runtime_stream_chunk(
            state,
            turn_id="turn:30:3:comp:lyra",
            actor_id="comp:lyra",
            text="We should move.",
            chunk_index=0,
        )
        state = finalize_runtime_turn(
            state,
            turn_id="turn:30:3:comp:lyra",
        )

        dialogue = get_runtime_dialogue_state(state)
        turn = dialogue["turns"][0]
        assert turn["status"] == "complete"
        assert turn["text"] == "We should move."
        assert dialogue["stream"]["active"] is False
        assert dialogue["stream"]["active_turn_id"] == ""
        assert dialogue["active_turn_id"] == ""

    def test_finalize_runtime_turn_can_append_final_chunk(self):
        state = {}
        state = begin_runtime_turn(
            state,
            tick=31,
            sequence_index=0,
            actor_id="npc:guard",
            speaker_id="npc:guard",
            speaker_name="Guard",
            role="npc",
            sequence_id="seq:31:0",
        )
        state = append_runtime_stream_chunk(
            state,
            turn_id="turn:31:0:npc:guard",
            actor_id="npc:guard",
            text="Stop",
            chunk_index=0,
        )
        state = finalize_runtime_turn(
            state,
            turn_id="turn:31:0:npc:guard",
            final_chunk_text=" now.",
        )

        dialogue = get_runtime_dialogue_state(state)
        turn = dialogue["turns"][0]
        assert turn["status"] == "complete"
        assert turn["text"] == "Stop now."
        assert turn["chunks"][-1]["final"] is True

    def test_mark_runtime_turn_interrupted_marks_turn_and_logs_event(self):
        state = {}
        state = begin_runtime_turn(
            state,
            tick=40,
            sequence_index=1,
            actor_id="npc:guard",
            speaker_id="npc:guard",
            speaker_name="Guard",
            role="npc",
            sequence_id="seq:40:0",
        )
        state = append_runtime_stream_chunk(
            state,
            turn_id="turn:40:1:npc:guard",
            actor_id="npc:guard",
            text="Wait ",
            chunk_index=0,
        )
        state = mark_runtime_turn_interrupted(
            state,
            turn_id="turn:40:1:npc:guard",
            interrupt_actor_id="comp:lyra",
            reason="protective_reaction",
        )

        dialogue = get_runtime_dialogue_state(state)
        turn = dialogue["turns"][0]
        assert turn["status"] == "interrupted"
        assert turn["interruption"] is True
        assert turn["interrupt_target_id"] == "comp:lyra"
        assert turn["text"] == "Wait "
        assert dialogue["stream"]["active"] is False
        assert dialogue["stream"]["active_turn_id"] == ""
        assert len(dialogue["interruption_log"]) == 1
        assert dialogue["interruption_log"][0]["actor_id"] == "comp:lyra"
        assert dialogue["interruption_log"][0]["target_id"] == "npc:guard"
        assert dialogue["interruption_log"][0]["reason"] == "protective_reaction"


class TestPhase105ChunkHelpers:
    """Unit tests for chunk helper functions."""

    def test_dedupe_and_sort_turn_chunks_overwrites_duplicates(self):
        chunks = [
            {
                "turn_id": "turn:1:0:npc:a",
                "chunk_index": 1,
                "actor_id": "npc:a",
                "speaker_id": "npc:a",
                "text": "B",
                "final": False,
            },
            {
                "turn_id": "turn:1:0:npc:a",
                "chunk_index": 0,
                "actor_id": "npc:a",
                "speaker_id": "npc:a",
                "text": "A",
                "final": False,
            },
            {
                "turn_id": "turn:1:0:npc:a",
                "chunk_index": 1,
                "actor_id": "npc:a",
                "speaker_id": "npc:a",
                "text": "B2",
                "final": False,
            },
        ]

        out = _dedupe_and_sort_turn_chunks(chunks)
        assert len(out) == 2
        assert out[0]["chunk_index"] == 0
        assert out[0]["text"] == "A"
        assert out[1]["chunk_index"] == 1
        assert out[1]["text"] == "B2"

    def test_dedupe_and_sort_global_stream_chunks_is_bounded(self):
        chunks = []
        for i in range(60):
            chunks.append({
                "turn_id": "turn:2:0:npc:a",
                "chunk_index": i,
                "actor_id": "npc:a",
                "speaker_id": "npc:a",
                "text": str(i),
                "final": False,
            })

        out = _dedupe_and_sort_global_stream_chunks(chunks)
        assert len(out) == 40
        assert out[0]["chunk_index"] == 20
        assert out[-1]["chunk_index"] == 59

    def test_rebuild_turn_text_from_chunks_joins_sorted_text(self):
        turn = {
            "chunks": [
                {
                    "turn_id": "turn:3:0:npc:a",
                    "chunk_index": 2,
                    "actor_id": "npc:a",
                    "speaker_id": "npc:a",
                    "text": "c",
                    "final": False,
                },
                {
                    "turn_id": "turn:3:0:npc:a",
                    "chunk_index": 0,
                    "actor_id": "npc:a",
                    "speaker_id": "npc:a",
                    "text": "a",
                    "final": False,
                },
                {
                    "turn_id": "turn:3:0:npc:a",
                    "chunk_index": 1,
                    "actor_id": "npc:a",
                    "speaker_id": "npc:a",
                    "text": "b",
                    "final": False,
                },
            ]
        }

        assert _rebuild_turn_text_from_chunks(turn) == "abc"


class TestPhase105Interruptions:
    """Unit tests for interruption helpers."""

    def test_role_precedence_is_stable(self):
        assert _role_precedence("player") == 0
        assert _role_precedence("companion") == 1
        assert _role_precedence("npc") == 2
        assert _role_precedence("system") == 3

    def test_normalize_sequence_actor_defaults_are_safe(self):
        item = _normalize_sequence_actor({"actor_id": "comp:lyra"})
        assert item["actor_id"] == "comp:lyra"
        assert item["speaker_id"] == "comp:lyra"
        assert item["role"] == "npc"
        assert item["present"] is True
        assert item["can_speak"] is True

    def test_interruptions_sort_highest_priority_first(self):
        a = _normalize_interruption_candidate({
            "actor_id": "comp:zane",
            "target_id": "npc:guard",
            "priority": 2,
            "role": "companion",
            "target_sequence_index": 3,
        })
        b = _normalize_interruption_candidate({
            "actor_id": "comp:lyra",
            "target_id": "npc:guard",
            "priority": 3,
            "role": "companion",
            "target_sequence_index": 3,
        })

        assert _sort_key_interruption_candidate(b) < _sort_key_interruption_candidate(a)


class TestPhase105Emotions:
    """Unit tests for emotional continuity helpers."""

    def test_normalize_emotion_name_falls_back_to_neutral(self):
        assert _normalize_emotion_name("tense") == "tense"
        assert _normalize_emotion_name("invalid") == "neutral"
        assert _normalize_emotion_name(None) == "neutral"

    def test_normalize_emotion_entry_clamps_intensity(self):
        entry = _normalize_emotion_entry("comp:lyra", {
            "emotion": "warm",
            "intensity": 5.0,
            "updated_tick": "7",
        })
        assert entry == {
            "actor_id": "comp:lyra",
            "emotion": "warm",
            "intensity": 1.0,
            "updated_tick": 7,
        }

    def test_build_runtime_style_tags_ignores_neutral_emotion_overlay(self):
        state = {}
        tags = build_runtime_style_tags(
            state,
            actor_id="npc:guard",
            base_tags=["brief"],
        )
        assert tags == ["brief"]

    def test_build_runtime_fallback_text_prefers_base_text(self):
        state = {}
        assert build_runtime_fallback_text(
            state,
            actor_id="npc:guard",
            base_text="Already have text.",
        ) == "Already have text."