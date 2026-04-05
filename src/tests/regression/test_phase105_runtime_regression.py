"""Phase 10.5 — Regression tests for runtime layer stability."""
import pytest

from app.rpg.runtime.dialogue_runtime import (
    ensure_runtime_state,
    get_runtime_dialogue_state,
    start_runtime_sequence,
    apply_runtime_interruptions,
    begin_runtime_turn,
    finalize_runtime_turn,
    build_runtime_style_tags,
)
from app.rpg.presentation.runtime_bridge import build_runtime_presentation_payload


class TestPhase105RuntimeBoundsRegression:
    """Regression tests for bounded runtime state."""

    def test_sequence_participants_are_bounded_to_eight(self):
        companions = [{"actor_id": f"comp:{i}"} for i in range(10)]
        npcs = [{"actor_id": f"npc:{i}"} for i in range(10)]

        state = {"player_id": "player:hero"}
        state = start_runtime_sequence(
            state,
            tick=5,
            sequence_index=0,
            companions=companions,
            npcs=npcs,
        )

        dialogue = get_runtime_dialogue_state(state)
        assert len(dialogue["sequence_participants"]) == 8
        assert dialogue["sequence_participants"][0]["actor_id"] == "player:hero"

    def test_runtime_state_normalization_preserves_empty_sequence_participants(self):
        state = ensure_runtime_state({
            "runtime_state": {
                "dialogue": {
                    "sequence_participants": [],
                }
            }
        })
        dialogue = get_runtime_dialogue_state(state)
        assert dialogue["sequence_participants"] == []


class TestPhase105InterruptionPriorityRegression:
    """Regression tests for interruption priority ordering."""

    def test_pending_interruptions_sort_highest_priority_first(self):
        state = {}
        state = apply_runtime_interruptions(
            state,
            candidates=[
                {
                    "actor_id": "comp:low",
                    "target_id": "npc:guard",
                    "reason": "runtime_interjection",
                    "priority": 1,
                },
                {
                    "actor_id": "comp:high",
                    "target_id": "npc:guard",
                    "reason": "runtime_interjection",
                    "priority": 5,
                },
            ],
        )

        dialogue = get_runtime_dialogue_state(state)
        assert [v["actor_id"] for v in dialogue["pending_interruptions"]] == [
            "comp:high",
            "comp:low",
        ]


class TestPhase105PresentationBridgeRegression:
    """Regression tests for presentation bridge payload stability."""

    def test_runtime_bridge_payload_shape_is_stable(self):
        state = {
            "runtime_state": {
                "dialogue": {
                    "active_sequence_id": "seq:9:0",
                    "active_turn_id": "turn:9:1:comp:lyra",
                    "sequence_tick": 9,
                    "turn_cursor": 1,
                    "turns": [
                        {
                            "turn_id": "turn:9:1:comp:lyra",
                            "sequence_id": "seq:9:0",
                            "tick": 9,
                            "sequence_index": 1,
                            "actor_id": "comp:lyra",
                            "speaker_id": "comp:lyra",
                            "speaker_name": "Lyra",
                            "role": "companion",
                            "text": "Move.",
                            "status": "complete",
                            "emotion": "stern",
                            "interruption": False,
                            "interrupt_target_id": "",
                            "chunks": [],
                        }
                    ],
                    "pending_interruptions": [
                        {
                            "actor_id": "comp:zane",
                            "target_id": "npc:guard",
                            "reason": "runtime_interjection",
                            "priority": 1,
                        }
                    ],
                    "interruption_log": [
                        {
                            "tick": 9,
                            "actor_id": "comp:zane",
                            "target_id": "npc:guard",
                            "reason": "runtime_interjection",
                            "turn_id": "turn:9:2:comp:zane",
                        }
                    ],
                    "stream": {
                        "active": False,
                        "active_turn_id": "",
                        "chunks": [],
                    },
                    "emotions": {
                        "comp:lyra": {
                            "emotion": "stern",
                            "intensity": 0.7,
                            "updated_tick": 9,
                        }
                    },
                    "sequence_participants": [
                        {
                            "actor_id": "player:hero",
                            "speaker_id": "player:hero",
                            "speaker_name": "Hero",
                            "role": "player",
                            "sequence_index": 0,
                        },
                        {
                            "actor_id": "comp:lyra",
                            "speaker_id": "comp:lyra",
                            "speaker_name": "Lyra",
                            "role": "companion",
                            "sequence_index": 1,
                        },
                    ],
                }
            }
        }

        payload = build_runtime_presentation_payload(state)
        runtime = payload["runtime_dialogue"]

        assert sorted(runtime.keys()) == sorted([
            "active_sequence_id",
            "active_turn_id",
            "sequence_tick",
            "turn_cursor",
            "sequence_participants",
            "turns",
            "pending_interruptions",
            "interruption_log",
            "stream",
            "emotions",
        ])
        assert runtime["turns"][0]["style_tags"] == ["emotion:stern"]


class TestPhase105EmotionStabilityRegression:
    """Regression tests for emotion snapshot stability."""

    def test_finalize_runtime_turn_preserves_emotion_snapshot(self):
        state = {}
        state = begin_runtime_turn(
            state,
            tick=50,
            sequence_index=0,
            actor_id="comp:lyra",
            speaker_id="comp:lyra",
            speaker_name="Lyra",
            role="companion",
            sequence_id="seq:50:0",
        )
        state = finalize_runtime_turn(
            state,
            turn_id="turn:50:0:comp:lyra",
        )

        dialogue = get_runtime_dialogue_state(state)
        turn = dialogue["turns"][0]
        assert turn["emotion"] == "neutral"
        assert turn["status"] == "complete"

    def test_build_runtime_style_tags_returns_sorted_unique_tags(self):
        state = {}
        tags = build_runtime_style_tags(
            state,
            actor_id="npc:guard",
            base_tags=["brief", "brief", "calm"],
        )
        assert tags == ["brief", "calm"]