"""Unit coverage for the ChatGPT subscription-backed Codex provider."""
from __future__ import annotations

from app.providers import ChatGPTCodexProvider, ChatMessage, ProviderConfig, ProviderRegistry


def _provider(**kwargs) -> ChatGPTCodexProvider:
    config = ProviderConfig(
        provider_type="chatgpt_codex",
        model=kwargs.pop("model", "gpt-5.6-sol"),
        extra_params={
            "codex_path": kwargs.pop("codex_path", "codex"),
            "reasoning_effort": kwargs.pop("reasoning_effort", "medium"),
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


def test_registry_resolves_typed_codex_profile_instead_of_lmstudio_config(monkeypatch):
    monkeypatch.setattr(
        "app.shared.load_settings",
        lambda: {
            "settings_control_center": {
                "providerConfigs": {
                    "chatgptCodex": {
                        "model": "gpt-test-subscription-model",
                        "reasoningEffort": "high",
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
