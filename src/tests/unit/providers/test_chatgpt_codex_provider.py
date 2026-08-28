"""Unit coverage for the ChatGPT subscription-backed Codex provider."""
from __future__ import annotations

from types import SimpleNamespace

from app.providers import ChatGPTCodexProvider, ChatMessage, ProviderConfig, ProviderRegistry
import app.providers.chatgpt_codex_provider as codex_module


def _provider(**kwargs) -> ChatGPTCodexProvider:
    config = ProviderConfig(
        provider_type="chatgpt_codex",
        model=kwargs.pop("model", "gpt-5.6-sol"),
        extra_params={
            "codex_path": kwargs.pop("codex_path", "codex"),
            "reasoning_effort": kwargs.pop("reasoning_effort", "medium"),
            "fast_mode": kwargs.pop("fast_mode", False),
            "transport": "app_server",
        },
        **kwargs,
    )
    return ChatGPTCodexProvider(config)


def test_provider_requires_no_openai_api_key():
    provider = _provider()
    try:
        assert provider.provider_name == "chatgpt_codex"
        assert provider.requires_api_key() is False
        assert provider.config.model == "gpt-5.6-sol"
        assert provider.reasoning_effort == "medium"
        assert provider.fast_mode is False
    finally:
        provider.close()


def test_auth_status_recognizes_chatgpt_login(monkeypatch):
    monkeypatch.setattr(
        ChatGPTCodexProvider,
        "_resolve_executable",
        staticmethod(lambda _path: "codex"),
    )

    def fake_status(command):
        if command[-1] == "--version":
            return {"returncode": 0, "stdout": "codex-cli 0.test", "stderr": ""}
        return {"returncode": 0, "stdout": "Logged in using ChatGPT", "stderr": ""}

    monkeypatch.setattr(ChatGPTCodexProvider, "_run_status_command", staticmethod(fake_status))

    status = ChatGPTCodexProvider.auth_status("codex")

    assert status["installed"] is True
    assert status["authenticated"] is True
    assert status["auth_mode"] == "chatgpt"
    assert status["cli_version"] == "codex-cli 0.test"


def test_resolver_uses_bundled_codex_candidate_when_not_on_path(monkeypatch, tmp_path):
    executable = tmp_path / "codex.exe"
    executable.touch()
    monkeypatch.setattr(codex_module.shutil, "which", lambda _value: None)
    monkeypatch.setattr(
        ChatGPTCodexProvider,
        "_bundled_executable_candidates",
        staticmethod(lambda: [executable]),
    )

    assert ChatGPTCodexProvider._resolve_executable("codex") == str(executable)


def test_connection_probes_initialized_app_server(monkeypatch):
    provider = _provider()
    calls: list[str] = []
    monkeypatch.setattr(
        provider,
        "auth_status",
        lambda _path: {
            "installed": True,
            "authenticated": True,
            "auth_mode": "chatgpt",
        },
    )

    def ensure_server() -> None:
        calls.append("ensure")
        provider._process = SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(provider, "_ensure_app_server", ensure_server)
    try:
        assert provider.test_connection() is True
        assert calls == ["ensure"]
    finally:
        provider._process = None
        provider.close()


def test_connection_fails_when_app_server_cannot_initialize(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(
        provider,
        "auth_status",
        lambda _path: {
            "installed": True,
            "authenticated": True,
            "auth_mode": "chatgpt",
        },
    )
    monkeypatch.setattr(
        provider,
        "_ensure_app_server",
        lambda: (_ for _ in ()).throw(RuntimeError("startup failed")),
    )
    try:
        assert provider.test_connection() is False
    finally:
        provider.close()


def test_registry_resolves_typed_codex_profile_instead_of_lmstudio_config(monkeypatch):
    monkeypatch.setattr(
        "app.shared.load_settings",
        lambda: {
            "settings_control_center": {
                "providerConfigs": {
                    "chatgptCodex": {
                        "model": "gpt-test-subscription-model",
                        "reasoningEffort": "high",
                        "fastMode": True,
                        "codexPath": "C:/tools/codex.exe",
                        "transport": "app_server",
                    }
                }
            }
        },
    )
    registry = ProviderRegistry()
    registry.discover_providers()
    provider = registry.create_provider(
        "chatgpt_codex",
        provider_config=ProviderConfig(
            provider_type="lmstudio",
            model="local-model-that-must-not-leak",
            base_url="http://localhost:1234",
        ),
    )
    assert isinstance(provider, ChatGPTCodexProvider)
    try:
        assert provider.config.provider_type == "chatgpt_codex"
        assert provider.config.model == "gpt-test-subscription-model"
        assert provider.reasoning_effort == "high"
        assert provider.fast_mode is True
        assert provider.codex_path == "C:/tools/codex.exe"
        assert provider.config.api_key is None
    finally:
        provider.close()


def test_non_streaming_completion_uses_app_server_events(monkeypatch):
    provider = _provider()
    events = iter(
        [
            {"method": "item/agentMessage/delta", "params": {"delta": "Hello"}},
            {"method": "item/agentMessage/delta", "params": {"delta": " from Plus"}},
            {
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "usage": {
                            "inputTokens": 12,
                            "outputTokens": 4,
                            "totalTokens": 16,
                        }
                    }
                },
            },
        ]
    )
    monkeypatch.setattr(provider, "_ensure_app_server", lambda: None)
    monkeypatch.setattr(provider, "_start_thread", lambda **_kwargs: "thread-1")
    monkeypatch.setattr(provider, "_request", lambda *_args, **_kwargs: {"turn": {"id": "turn-1"}})
    monkeypatch.setattr(provider, "_next_event", lambda _timeout: next(events))

    try:
        response = provider.chat_completion(
            [
                ChatMessage(role="system", content="Be concise."),
                ChatMessage(role="user", content="Say hello."),
            ],
            stream=False,
            conversation_id="chat:1",
        )
    finally:
        provider.close()

    assert response.content == "Hello from Plus"
    assert response.model == "gpt-5.6-sol"
    assert response.usage == {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}


def test_json_schema_response_format_is_projected_into_codex_system_prompt(
    monkeypatch,
):
    provider = _provider()
    captured = {}

    def fake_stream(messages, **_kwargs):
        captured["messages"] = messages
        yield SimpleNamespace(
            content='{"lane":"chat"}',
            model="gpt-5.6-sol",
            usage=None,
            tool_calls=None,
            finish_reason="stop",
        )

    monkeypatch.setattr(provider, "_chat_stream", fake_stream)
    try:
        response = provider.chat_completion(
            [ChatMessage(role="user", content="Classify this.")],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "semantic_intent",
                    "strict": False,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "lane": {
                                "type": "string",
                                "enum": ["chat", "agent"],
                            }
                        },
                        "required": ["lane"],
                        "additionalProperties": False,
                    },
                },
            },
        )
    finally:
        provider.close()

    system_text = "\n".join(
        message.content
        for message in captured["messages"]
        if message.role == "system"
    )
    assert response.content == '{"lane":"chat"}'
    assert "STRUCTURED RESPONSE CONTRACT" in system_text
    assert '"additionalProperties":false' in system_text
    assert '"lane"' in system_text
    assert "contract metadata" in system_text


def test_fast_mode_uses_codex_fast_service_tier(monkeypatch):
    provider = _provider(fast_mode=True, reasoning_effort="none")
    events = iter([
        {"method": "item/agentMessage/delta", "params": {"delta": "Fast"}},
        {"method": "turn/completed", "params": {"turn": {}}},
    ])
    turn_params = {}

    monkeypatch.setattr(provider, "_ensure_app_server", lambda: None)
    monkeypatch.setattr(provider, "_start_thread", lambda **_kwargs: "thread-fast")

    def fake_request(method, params, **_kwargs):
        if method == "turn/start":
            turn_params.update(params)
        return {}

    monkeypatch.setattr(provider, "_request", fake_request)
    monkeypatch.setattr(provider, "_next_event", lambda _timeout: next(events))

    try:
        response = provider.chat_completion([ChatMessage(role="user", content="Be fast")])
    finally:
        provider.close()

    assert response.content == "Fast"
    assert turn_params["effort"] == "none"
    assert turn_params["serviceTier"] == "fast"


def test_fast_mode_is_not_sent_for_non_sol_models(monkeypatch):
    provider = _provider(model="gpt-5.6-terra", fast_mode=True)
    events = iter([
        {"method": "item/agentMessage/delta", "params": {"delta": "Balanced"}},
        {"method": "turn/completed", "params": {"turn": {}}},
    ])
    turn_params = {}

    monkeypatch.setattr(provider, "_ensure_app_server", lambda: None)
    monkeypatch.setattr(provider, "_start_thread", lambda **_kwargs: "thread-terra")

    def fake_request(method, params, **_kwargs):
        if method == "turn/start":
            turn_params.update(params)
        return {}

    monkeypatch.setattr(provider, "_request", fake_request)
    monkeypatch.setattr(provider, "_next_event", lambda _timeout: next(events))

    try:
        provider.chat_completion([ChatMessage(role="user", content="Answer")])
    finally:
        provider.close()

    assert "serviceTier" not in turn_params


def test_streaming_completion_yields_codex_deltas(monkeypatch):
    provider = _provider()
    events = iter(
        [
            {"method": "item/agentMessage/delta", "params": {"delta": "One"}},
            {"method": "item/agentMessage/delta", "params": {"delta": " two"}},
            {"method": "turn/completed", "params": {"turn": {}}},
        ]
    )
    monkeypatch.setattr(provider, "_ensure_app_server", lambda: None)
    monkeypatch.setattr(provider, "_start_thread", lambda **_kwargs: "thread-1")
    monkeypatch.setattr(provider, "_request", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(provider, "_next_event", lambda _timeout: next(events))

    try:
        chunks = list(
            provider.chat_completion(
                [ChatMessage(role="user", content="Count")],
                stream=True,
                conversation_id="chat:stream",
            )
        )
    finally:
        provider.close()

    assert "".join(chunk.content for chunk in chunks) == "One two"


def test_tool_enabled_completion_bridges_native_dynamic_tool_call(monkeypatch):
    provider = _provider()
    events = iter(
        [
            {
                "id": 91,
                "method": "item/tool/call",
                "params": {
                    "threadId": "thread-tools",
                    "turnId": "turn-tools",
                    "callId": "call_read",
                    "tool": "omnix_read",
                    "arguments": {"path": "src/app.py"},
                },
            },
            {"method": "item/agentMessage/delta", "params": {"delta": "Reviewed"}},
            {"method": "turn/completed", "params": {"turn": {}}},
        ]
    )
    writes = []
    monkeypatch.setattr(provider, "_ensure_app_server", lambda: None)
    monkeypatch.setattr(provider, "_start_thread", lambda **_kwargs: "thread-tools")
    monkeypatch.setattr(provider, "_request", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(provider, "_write_message", writes.append)
    monkeypatch.setattr(provider, "_next_event", lambda _timeout, **_kwargs: next(events))

    tools = [
        {
            "type": "function",
            "function": {
                "name": "read",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        }
    ]

    try:
        first_chunks = list(
            provider.chat_completion(
                [ChatMessage(role="user", content="Read the file")],
                stream=True,
                conversation_id="agent:1",
                tools=tools,
            )
        )
        second_chunks = list(
            provider.chat_completion(
                [
                    ChatMessage(role="user", content="Read the file"),
                    ChatMessage(
                        role="tool",
                        content="file contents",
                        name="read",
                        tool_call_id="call_read",
                    ),
                ],
                stream=True,
                conversation_id="agent:1",
                tools=tools,
            )
        )
    finally:
        provider.close()

    assert len(first_chunks) == 1
    assert first_chunks[0].content == ""
    assert first_chunks[0].finish_reason == "tool_calls"
    assert first_chunks[0].tool_calls == [
        {
            "id": "call_read",
            "type": "function",
            "function": {
                "name": "read",
                "arguments": '{"path":"src/app.py"}',
            },
        }
    ]
    assert "".join(chunk.content for chunk in second_chunks) == "Reviewed"
    assert writes == [
        {
            "id": 91,
            "result": {
                "success": True,
                "contentItems": [{"type": "inputText", "text": "file contents"}],
            },
        }
    ]


def test_tool_result_prompt_preserves_tool_identity():
    prompt = ChatGPTCodexProvider._turn_prompt(
        [
            ChatMessage(
                role="tool",
                content="file contents",
                name="read",
                tool_call_id="call_read",
            )
        ],
        recover_history=False,
    )

    assert "Omnix executed read" in prompt
    assert "file contents" in prompt


def test_fresh_thread_recovery_marks_old_messages_as_history():
    prompt = ChatGPTCodexProvider._turn_prompt(
        [
            ChatMessage(role="system", content="System"),
            ChatMessage(role="user", content="First question"),
            ChatMessage(role="assistant", content="First answer"),
            ChatMessage(role="user", content="Second question"),
        ],
        recover_history=True,
    )

    assert "<conversation_history>" in prompt
    assert "USER: First question" in prompt
    assert "ASSISTANT: First answer" in prompt
    assert prompt.endswith("USER: Second question")
