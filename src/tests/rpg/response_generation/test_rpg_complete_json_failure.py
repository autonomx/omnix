from __future__ import annotations

import pytest

from app.providers.base import ChatResponse, ProviderConfig
from app.providers.structured import StructuredDecodeError
from app.rpg.llm_app_gateway import AppLLMGateway


class _Provider:
    provider_name = "lmstudio"

    def __init__(self, content: str) -> None:
        self.config = ProviderConfig(provider_type="lmstudio", model="test-model")
        self.content = content

    def chat_completion(self, messages, **kwargs):
        return ChatResponse(content=self.content, model="test-model")


def test_complete_json_rejects_malformed_output_instead_of_returning_empty() -> None:
    gateway = AppLLMGateway(_Provider("not-json"))

    with pytest.raises(StructuredDecodeError):
        gateway.complete_json("return data")


def test_complete_json_keeps_legitimate_empty_object_distinct() -> None:
    gateway = AppLLMGateway(_Provider("{}"))

    assert gateway.complete_json("return data") == {}
