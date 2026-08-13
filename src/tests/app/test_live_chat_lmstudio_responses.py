from __future__ import annotations

from app.gateway import live_chat_lmstudio_responses as runtime
from app.providers import ChatMessage as ProviderMessage


def _message(role: str, content: str) -> ProviderMessage:
    return ProviderMessage(role=role, content=content)


def setup_function() -> None:
    runtime._clear_response_states_for_tests()


def teardown_function() -> None:
    runtime._clear_response_states_for_tests()


def test_state_reuse_accepts_front_only_rolling_window_shift() -> None:
    seeded = [
        _message("system", "stable persona"),
        _message("user", "old user 1"),
        _message("assistant", "old assistant 1"),
        _message("user", "old user 2"),
        _message("assistant", "old assistant 2"),
        _message("user", "current user"),
    ]
    assert runtime._remember_response_state(
        session_id="chat:rolling",
        model_id="model-a",
        request_messages=seeded,
        assistant_text="current assistant",
        response_id="resp_seed",
    ) is True

    next_prompt = [
        _message("system", "stable persona"),
        _message("user", "old user 2"),
        _message("assistant", "old assistant 2"),
        _message("user", "current user"),
        _message("assistant", "current assistant"),
        _message("user", "next user"),
    ]
    response_id, reason, continuation_count, rolled_off = runtime._resolve_previous_response_id(
        session_id="chat:rolling",
        model_id="model-a",
        messages=next_prompt,
    )

    assert response_id == "resp_seed"
    assert reason == "hit"
    assert continuation_count == 0
    assert rolled_off == 2


def test_state_reuse_rejects_stable_context_change() -> None:
    seeded = [
        _message("system", "persona v1"),
        _message("user", "hello"),
    ]
    assert runtime._remember_response_state(
        session_id="chat:context",
        model_id="model-a",
        request_messages=seeded,
        assistant_text="hi",
        response_id="resp_context",
    ) is True

    changed = [
        _message("system", "persona v2"),
        _message("user", "hello"),
        _message("assistant", "hi"),
        _message("user", "again"),
    ]
    response_id, reason, _, _ = runtime._resolve_previous_response_id(
        session_id="chat:context",
        model_id="model-a",
        messages=changed,
    )

    assert response_id is None
    assert reason == "stable_context_changed"


def test_state_reuse_rejects_divergent_recent_tail() -> None:
    seeded = [
        _message("system", "stable persona"),
        _message("user", "hello"),
    ]
    assert runtime._remember_response_state(
        session_id="chat:tail",
        model_id="model-a",
        request_messages=seeded,
        assistant_text="original answer",
        response_id="resp_tail",
    ) is True

    changed = [
        _message("system", "stable persona"),
        _message("user", "hello"),
        _message("assistant", "edited answer"),
        _message("user", "again"),
    ]
    response_id, reason, _, _ = runtime._resolve_previous_response_id(
        session_id="chat:tail",
        model_id="model-a",
        messages=changed,
    )

    assert response_id is None
    assert reason == "conversation_tail_changed"


def test_state_reuse_forces_periodic_reseed(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_LMSTUDIO_RESPONSE_MAX_CONTINUATIONS", "1")
    first = [
        _message("system", "stable persona"),
        _message("user", "one"),
    ]
    assert runtime._remember_response_state(
        session_id="chat:lease",
        model_id="model-a",
        request_messages=first,
        assistant_text="answer one",
        response_id="resp_one",
    ) is True

    second = [
        _message("system", "stable persona"),
        _message("user", "one"),
        _message("assistant", "answer one"),
        _message("user", "two"),
    ]
    response_id, reason, continuation_count, _ = runtime._resolve_previous_response_id(
        session_id="chat:lease",
        model_id="model-a",
        messages=second,
    )
    assert response_id == "resp_one"
    assert reason == "hit"
    assert continuation_count == 0
    assert runtime._remember_response_state(
        session_id="chat:lease",
        model_id="model-a",
        request_messages=second,
        assistant_text="answer two",
        response_id="resp_two",
        prior_continuation_count=continuation_count,
        state_hit=True,
    ) is True

    third = [
        _message("system", "stable persona"),
        _message("user", "one"),
        _message("assistant", "answer one"),
        _message("user", "two"),
        _message("assistant", "answer two"),
        _message("user", "three"),
    ]
    response_id, reason, continuation_count, _ = runtime._resolve_previous_response_id(
        session_id="chat:lease",
        model_id="model-a",
        messages=third,
    )

    assert response_id is None
    assert reason == "continuation_limit"
    assert continuation_count == 1


def test_ephemeral_context_prevents_state_from_being_carried() -> None:
    messages = [
        _message("system", "stable persona"),
        _message("user", "question with temporary context"),
    ]
    assert runtime._remember_response_state(
        session_id="chat:ephemeral",
        model_id="model-a",
        request_messages=messages,
        assistant_text="answer",
        response_id="resp_ephemeral",
        carry_allowed=False,
    ) is False

    follow_up = [
        _message("system", "stable persona"),
        _message("user", "question with temporary context"),
        _message("assistant", "answer"),
        _message("user", "follow up"),
    ]
    response_id, reason, _, _ = runtime._resolve_previous_response_id(
        session_id="chat:ephemeral",
        model_id="model-a",
        messages=follow_up,
    )

    assert response_id is None
    assert reason == "state_missing"
