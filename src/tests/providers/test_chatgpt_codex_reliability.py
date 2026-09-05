from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.providers import ChatGPTCodexProvider, ChatMessage, ProviderConfig
from app.providers import codex_reliability as reliability


def _provider() -> ChatGPTCodexProvider:
    return ChatGPTCodexProvider(
        ProviderConfig(
            provider_type="chatgpt_codex",
            model="gpt-5.6-sol",
            extra_params={
                "codex_path": "codex",
                "reasoning_effort": "medium",
                "fast_mode": False,
                "transport": "app_server",
            },
        )
    )


def _install_fake_transport(monkeypatch, provider, events, captured_turns):
    monkeypatch.setattr(provider, "_ensure_app_server", lambda: None)
    monkeypatch.setattr(provider, "_start_thread", lambda **_kwargs: "thread-1")

    def fake_request(_self, method, params, *args, **kwargs):
        del args, kwargs
        if method == "turn/start":
            captured_turns.append(dict(params))
            return {"turn": {"id": "turn-1"}}
        return {}

    iterator = iter(events)

    def fake_next_event(_self, _timeout, *args, **kwargs):
        del args, kwargs
        return next(iterator)

    monkeypatch.setattr(reliability, "_ORIGINAL_REQUEST", fake_request)
    monkeypatch.setattr(reliability, "_ORIGINAL_NEXT_EVENT", fake_next_event)


def test_retryable_codex_error_notification_does_not_abort_turn(monkeypatch):
    provider = _provider()
    captured_turns = []
    _install_fake_transport(
        monkeypatch,
        provider,
        [
            {
                "method": "error",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "willRetry": True,
                    "error": {
                        "message": "Reconnecting... 2/5",
                        "codexErrorInfo": {
                            "responseStreamDisconnected": {"httpStatusCode": 404}
                        },
                    },
                },
            },
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "delta": "Recovered",
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1"},
                },
            },
        ],
        captured_turns,
    )
    try:
        response = provider.chat_completion(
            [ChatMessage(role="user", content="Return one word")],
            stream=False,
        )
    finally:
        provider._process = None
        provider.close()

    assert response.content == "Recovered"
    assert len(captured_turns) == 1


def test_terminal_codex_error_notification_still_fails(monkeypatch):
    provider = _provider()
    captured_turns = []
    _install_fake_transport(
        monkeypatch,
        provider,
        [
            {
                "method": "error",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "willRetry": False,
                    "error": "terminal failure",
                },
            }
        ],
        captured_turns,
    )
    try:
        with pytest.raises(OSError, match="terminal failure"):
            provider.chat_completion(
                [ChatMessage(role="user", content="Return one word")],
                stream=False,
            )
    finally:
        provider._process = None
        provider.close()


def test_json_schema_is_sent_as_native_turn_output_schema(monkeypatch):
    provider = _provider()
    captured_turns = []
    schema = {
        "type": "object",
        "properties": {"decision": {"type": "string"}},
        "required": ["decision"],
        "additionalProperties": False,
    }
    _install_fake_transport(
        monkeypatch,
        provider,
        [
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "delta": '{"decision":"hold"}',
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1"},
                },
            },
        ],
        captured_turns,
    )
    try:
        response = provider.chat_completion(
            [ChatMessage(role="user", content="Choose")],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "decision",
                    "strict": True,
                    "schema": schema,
                },
            },
        )
    finally:
        provider._process = None
        provider.close()

    assert response.content == '{"decision":"hold"}'
    assert captured_turns[0]["outputSchema"] == schema


def test_json_object_gets_generic_native_object_schema(monkeypatch):
    provider = _provider()
    captured_turns = []
    _install_fake_transport(
        monkeypatch,
        provider,
        [
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "delta": "{}",
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1"},
                },
            },
        ],
        captured_turns,
    )
    try:
        provider.chat_completion(
            [ChatMessage(role="user", content="Object")],
            response_format={"type": "json_object"},
        )
    finally:
        provider._process = None
        provider.close()

    assert captured_turns[0]["outputSchema"] == {"type": "object"}
