from __future__ import annotations

import time

from app.assistant_memory.paralinguistic_state import (
    clear_ephemeral_call_state,
    durable_affect_candidate_allowed,
    get_ephemeral_call_state,
    observe_paralinguistic_turn,
    paralinguistic_prompt_directive,
)


def test_laughter_hesitation_and_pause_shape_immediate_style() -> None:
    clear_ephemeral_call_state()
    state = observe_paralinguistic_turn(
        "chat:signals",
        "Um... [laughs] maybe I should try that",
        metadata={"pause_ms": 1_200, "speech_duration_ms": 4_000},
    )

    kinds = {signal.kind for signal in state.signals}
    assert {"laughter", "hesitation", "reflective_pause", "uncertain_delivery"} <= kinds
    directive = paralinguistic_prompt_directive(state)
    assert directive is not None
    assert "uncertain" in directive.casefold()
    assert "diagnosis" in directive.casefold()


def test_interruption_attempt_takes_style_priority() -> None:
    clear_ephemeral_call_state()
    state = observe_paralinguistic_turn(
        "chat:interrupt",
        "Wait",
        metadata={"interruption_attempt": True},
    )

    directive = paralinguistic_prompt_directive(state)
    assert directive is not None
    assert "opening brief" in directive.casefold()


def test_neutral_turn_replaces_signal_state_and_removes_directive() -> None:
    clear_ephemeral_call_state()
    observe_paralinguistic_turn(
        "chat:replace",
        "Wait",
        metadata={"interruption_attempt": True},
    )

    neutral = observe_paralinguistic_turn("chat:replace", "What time is the meeting?")

    assert neutral.signals == ()
    assert paralinguistic_prompt_directive(neutral) is None
    assert get_ephemeral_call_state("chat:replace") == neutral


def test_current_signal_replaces_stale_higher_priority_signal() -> None:
    clear_ephemeral_call_state()
    observe_paralinguistic_turn(
        "chat:priority",
        "Wait",
        metadata={"interruption_attempt": True},
    )

    current = observe_paralinguistic_turn("chat:priority", "haha that worked!!")
    directive = paralinguistic_prompt_directive(current)

    assert {signal.kind for signal in current.signals} == {"laughter", "excited_delivery"}
    assert directive is not None
    assert "light response" in directive.casefold()
    assert "opening brief" not in directive.casefold()


def test_state_retains_no_transcript_or_audio_and_never_creates_affect_memory() -> None:
    clear_ephemeral_call_state()
    state = observe_paralinguistic_turn(
        "chat:private",
        "[sighs] I am not sure",
        metadata={"original_audio_ms": 5_000, "raw_audio": b"not-retained"},
        private_mode=True,
    )

    serialized = state.model_dump(mode="json")
    assert "transcript" not in serialized
    assert "audio" not in serialized
    assert "content" not in serialized
    assert serialized["private_mode"] is True
    assert durable_affect_candidate_allowed(state) is False
    assert state.content_free_diagnostics()["durable_candidate_created"] is False


def test_emotional_attunement_off_disables_style_directive() -> None:
    clear_ephemeral_call_state()
    state = observe_paralinguistic_turn("chat:off", "haha that worked!!")
    assert paralinguistic_prompt_directive(state, emotional_attunement="off") is None


def test_state_is_bounded_and_clearable() -> None:
    clear_ephemeral_call_state()
    for index in range(40):
        observe_paralinguistic_turn(
            "chat:bounded",
            "um... maybe",
            metadata={"pause_ms": 1_000 if index % 2 else 0},
        )
    state = get_ephemeral_call_state("chat:bounded")
    assert state is not None
    assert len(state.signals) <= 3

    clear_ephemeral_call_state("chat:bounded")
    assert get_ephemeral_call_state("chat:bounded") is None


def test_signal_detection_is_non_blocking_for_live_prompt_path() -> None:
    clear_ephemeral_call_state()
    started = time.perf_counter()
    for index in range(100):
        observe_paralinguistic_turn(
            f"chat:perf:{index}",
            "Um... [laughs] maybe that is right",
            metadata={"speech_duration_ms": 2_000},
        )
    elapsed_ms = (time.perf_counter() - started) * 1_000
    assert elapsed_ms < 250
