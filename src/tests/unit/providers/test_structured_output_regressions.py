from __future__ import annotations

import json
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.providers.base import (
    AuthenticationError,
    ChatMessage,
    ChatResponse,
    ProviderConfig,
)
from app.providers.openai_compatible_provider import OpenAICompatibleProvider
from app.providers.structured import (
    ProviderTimeout,
    StructuredContract,
    StructuredOutputExhausted,
    StructuredOutputGateway,
    StructuredRetryBudget,
    UnsupportedStructuredMode,
)


class _PayloadA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    enabled: StrictBool


class _PayloadB(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["safe", "strict"]


class _SlowProvider:
    provider_name = "slow-test"

    def __init__(self, delay: float) -> None:
        self.config = ProviderConfig(provider_type=self.provider_name, model="slow-model")
        self.delay = delay
        self.calls: list[dict] = []

    def chat_completion(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), **kwargs})
        time.sleep(self.delay)
        return ChatResponse(
            content=json.dumps({"name": "late", "enabled": True}),
            model="slow-model",
        )


class _ErrorProvider:
    provider_name = "permanent-error-test"

    def __init__(self) -> None:
        self.config = ProviderConfig(provider_type=self.provider_name, model="error-model")
        self.calls = 0

    def chat_completion(self, messages, **kwargs):
        self.calls += 1
        raise AuthenticationError("invalid credential")


class _ScriptedProvider:
    provider_name = "lmstudio"

    def __init__(self, responses: list[ChatResponse | Exception], model: str) -> None:
        self.config = ProviderConfig(provider_type=self.provider_name, model=model)
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat_completion(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="Return the object.")]


def test_blocking_provider_cannot_hold_caller_past_absolute_deadline() -> None:
    provider = _SlowProvider(delay=0.25)
    started = time.monotonic()

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(),
        contract=StructuredContract(
            contract_id="tests.structured.slow-deadline",
            version=1,
            output_model=_PayloadA,
        ),
        retry_budget=StructuredRetryBudget(
            max_provider_calls=1,
            max_transport_retries=0,
            max_format_downgrades=0,
            max_validation_regenerations=0,
            deadline_seconds=0.05,
        ),
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.18
    assert isinstance(outcome.error, StructuredOutputExhausted)
    assert isinstance(outcome.error.last_error, ProviderTimeout)
    assert provider.calls[0]["request_timeout_seconds"] <= 0.05


def test_permanent_authentication_failure_is_not_retried() -> None:
    provider = _ErrorProvider()

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(),
        contract=StructuredContract(
            contract_id="tests.structured.permanent-error",
            version=1,
            output_model=_PayloadA,
        ),
        retry_budget=StructuredRetryBudget(
            max_provider_calls=3,
            max_transport_retries=2,
            max_format_downgrades=1,
            max_validation_regenerations=1,
            deadline_seconds=1,
        ),
    )

    assert isinstance(outcome.error, StructuredOutputExhausted)
    assert isinstance(outcome.error.last_error, AuthenticationError)
    assert provider.calls == 1


def test_negative_capability_cache_is_scoped_to_schema_hash() -> None:
    model = "schema-scoped-negative-cache"
    first = _ScriptedProvider(
        [
            UnsupportedStructuredMode("schema A rejected"),
            ChatResponse(
                content=json.dumps({"name": "fallback", "enabled": True}),
                model=model,
            ),
        ],
        model,
    )
    StructuredOutputGateway(first).generate(
        _messages(),
        contract=StructuredContract(
            contract_id="tests.structured.schema-a",
            version=1,
            output_model=_PayloadA,
            schema_profile="local",
        ),
        retry_budget=StructuredRetryBudget(
            max_provider_calls=2,
            max_transport_retries=0,
            max_format_downgrades=1,
            max_validation_regenerations=0,
            deadline_seconds=1,
        ),
    )
    second = _ScriptedProvider(
        [ChatResponse(content=json.dumps({"mode": "safe"}), model=model)],
        model,
    )

    value = StructuredOutputGateway(second).generate(
        _messages(),
        contract=StructuredContract(
            contract_id="tests.structured.schema-b",
            version=1,
            output_model=_PayloadB,
            schema_profile="local",
        ),
    )

    assert value.mode == "safe"
    assert second.calls[0]["response_format"]["type"] == "json_schema"


def test_openai_compatible_forwards_structured_fields_and_timeout(monkeypatch) -> None:
    captured: dict = {}

    class _Response:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "model": "remote-model",
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "return_value",
                                        "arguments": '{"value":1}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }

    def request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return _Response()

    monkeypatch.setattr("app.providers.openai_compatible_provider.requests.request", request)
    provider = OpenAICompatibleProvider(
        ProviderConfig(
            provider_type="openai_compatible",
            api_key="test-key",
            base_url="https://example.invalid/v1",
            model="remote-model",
        )
    )

    response = provider.chat_completion(
        _messages(),
        response_format={"type": "json_object"},
        tools=[
            {
                "type": "function",
                "function": {"name": "return_value", "parameters": {"type": "object"}},
            }
        ],
        tool_choice={"type": "function", "function": {"name": "return_value"}},
        request_timeout_seconds=0.75,
    )

    assert captured["timeout"] == 0.75
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["json"]["tools"][0]["type"] == "function"
    assert captured["json"]["tool_choice"]["function"]["name"] == "return_value"
    assert response.tool_calls is not None
