from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from app.providers.base import BaseProvider, ChatMessage, ChatResponse, ProviderConfig
from app.apps.rpg.foundation.llm_gateway_adapter import LLMGatewayAdapter, adapt_base_provider


class _Provider(BaseProvider):
    provider_name = "test-provider"

    def __init__(self) -> None:
        super().__init__(ProviderConfig(provider_type="test-provider"))
        self.calls: list[dict[str, object]] = []

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        self.calls.append({
            "messages": messages,
            "model": model,
            "stream": stream,
            "kwargs": kwargs,
        })
        if stream:
            return iter([
                ChatResponse(content="one", model="test"),
                ChatResponse(content="two", model="test"),
            ])
        return ChatResponse(content="ready", model="test")

    def get_models(self):
        return []

    def test_connection(self):
        return True


def test_base_provider_adapter_exposes_generate_stream_and_call() -> None:
    provider = _Provider()
    gateway = adapt_base_provider(provider)

    assert isinstance(gateway, LLMGatewayAdapter)
    assert gateway.provider_name == "test-provider"
    assert gateway.generate("hello", context={"npc": "Ada"}, temperature=0.2) == "ready"
    request = provider.calls[-1]
    messages = request["messages"]
    assert isinstance(messages, list)
    assert all(isinstance(message, ChatMessage) for message in messages)
    assert messages[-1].content == "Context JSON:\n{\"npc\": \"Ada\"}"
    assert request["kwargs"] == {"temperature": 0.2}

    assert gateway.call("complete", "again") == "ready"
    assert list(gateway.generate_stream("stream")) == [{"text": "one"}, {"text": "two"}]
    assert provider.calls[-1]["stream"] is True


def test_provider_access_wraps_base_provider(monkeypatch) -> None:
    from app.providers import service as provider_service
    from app.apps.rpg.foundation.provider_access import get_provider

    provider = _Provider()
    monkeypatch.setattr(provider_service, "get_provider", lambda: provider)

    assert isinstance(get_provider(), LLMGatewayAdapter)


def test_importing_app_does_not_add_builtin_opening_bonus() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    source_root = repository_root / "src"
    environment = dict(os.environ)
    inherited_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(source_root), inherited_pythonpath) if item
    )

    subprocess.run(
        [
            sys.executable,
            "-c",
            "import builtins; import app; assert not hasattr(builtins, 'opening_bonus')",
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
        timeout=15,
    )
