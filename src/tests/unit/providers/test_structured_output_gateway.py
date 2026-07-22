from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.providers.base import ChatMessage, ChatResponse, ProviderConfig
from app.providers.structured import (
    StructuredCapabilities,
    StructuredContract,
    StructuredDecodeError,
    StructuredMode,
    StructuredOutputGateway,
    StructuredRetryBudget,
    StructuredSchemaError,
)


class ExamplePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    count: int = Field(ge=0)
    enabled: StrictBool
    tags: list[str] = Field(default_factory=list)


class EmptyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[str] = Field(default_factory=list)


EXAMPLE_CONTRACT = StructuredContract(
    contract_id="tests.structured.example",
    version=1,
    output_model=ExamplePayload,
    schema_profile="local",
)


class FakeProvider:
    def __init__(
        self,
        responses: list[ChatResponse | Exception],
        *,
        provider_name: str = "lmstudio",
        capabilities: StructuredCapabilities | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.config = ProviderConfig(provider_type=provider_name, model="test-model")
        self.responses = list(responses)
        self.calls: list[dict] = []
        self._capabilities = capabilities

    def get_structured_capabilities(self, model=None):
        return self._capabilities or StructuredCapabilities.default_for_provider(
            self.provider_name
        )

    def chat_completion(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), **kwargs})
        if not self.responses:
            raise AssertionError("fake provider exhausted")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="Return the requested test object.")]


def _response(payload, *, finish_reason: str = "stop") -> ChatResponse:
    return ChatResponse(
        content=payload if isinstance(payload, str) else json.dumps(payload),
        model="test-model",
        finish_reason=finish_reason,
        usage={"prompt_tokens": 10, "completion_tokens": 5},
    )


def test_lmstudio_uses_projected_json_schema_and_returns_typed_value() -> None:
    provider = FakeProvider(
        [_response({"name": "alpha", "count": 3, "enabled": True, "tags": []})]
    )
    gateway = StructuredOutputGateway(provider)

    result = gateway.generate(_messages(), contract=EXAMPLE_CONTRACT)

    assert isinstance(result, ExamplePayload)
    assert result.count == 3
    response_format = provider.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    schema = response_format["json_schema"]["schema"]
    assert "$defs" not in schema
    assert response_format["json_schema"]["strict"] is True
    assert gateway.last_diagnostics is not None
    assert gateway.last_diagnostics.selected_mode is StructuredMode.JSON_SCHEMA


def test_unsupported_mode_downgrades_to_text_once() -> None:
    provider = FakeProvider(
        [
            ValueError("response_format json_schema is unsupported"),
            _response({"name": "beta", "count": 1, "enabled": False, "tags": []}),
        ]
    )
    gateway = StructuredOutputGateway(provider)

    result = gateway.generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=StructuredRetryBudget(
            max_provider_calls=3,
            max_transport_retries=0,
            max_format_downgrades=1,
            max_validation_regenerations=0,
            deadline_seconds=5,
        ),
    )

    assert result.name == "beta"
    assert provider.calls[0]["response_format"]["type"] == "json_schema"
    assert provider.calls[1]["response_format"]["type"] == "text"
    assert gateway.last_diagnostics is not None
    assert gateway.last_diagnostics.format_downgrades == 1


def test_fenced_and_surrounded_json_is_conservatively_extracted() -> None:
    provider = FakeProvider(
        [
            _response(
                "```json\n"
                '{"name":"gamma","count":2,"enabled":true,"tags":[]}'
                "\n```"
            )
        ]
    )

    result = StructuredOutputGateway(provider).generate(
        _messages(), contract=EXAMPLE_CONTRACT
    )

    assert result.name == "gamma"


def test_schema_failure_is_regenerated_with_machine_readable_feedback() -> None:
    provider = FakeProvider(
        [
            _response({"name": "delta", "count": "wrong", "enabled": True}),
            _response({"name": "delta", "count": 4, "enabled": True, "tags": []}),
        ]
    )
    gateway = StructuredOutputGateway(provider)

    result = gateway.generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=StructuredRetryBudget(
            max_provider_calls=2,
            max_transport_retries=0,
            max_format_downgrades=0,
            max_validation_regenerations=1,
            deadline_seconds=5,
        ),
    )

    assert result.count == 4
    correction = provider.calls[1]["messages"][-1].content
    assert "STRUCTURED_OUTPUT_CORRECTION" in correction
    assert '"path": ["count"]' in correction
    assert gateway.last_diagnostics is not None
    assert gateway.last_diagnostics.validation_regenerations == 1


def test_invalid_json_is_a_failure_not_an_empty_object() -> None:
    provider = FakeProvider([_response("not json")])
    gateway = StructuredOutputGateway(provider)

    outcome = gateway.try_generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=StructuredRetryBudget(
            max_provider_calls=1,
            max_transport_retries=0,
            max_format_downgrades=0,
            max_validation_regenerations=0,
            deadline_seconds=5,
        ),
    )

    assert outcome.value is None
    assert isinstance(outcome.error, StructuredDecodeError)


def test_valid_empty_payload_remains_distinct_from_failure() -> None:
    contract = StructuredContract(
        contract_id="tests.structured.empty",
        version=1,
        output_model=EmptyPayload,
    )
    provider = FakeProvider([_response({"rows": []})])

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(), contract=contract
    )

    assert outcome.succeeded is True
    assert outcome.value == EmptyPayload(rows=[])
    assert outcome.error is None


def test_strict_boolean_rejects_string_boolean() -> None:
    provider = FakeProvider(
        [_response({"name": "epsilon", "count": 1, "enabled": "false", "tags": []})]
    )

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=StructuredRetryBudget(
            max_provider_calls=1,
            max_transport_retries=0,
            max_format_downgrades=0,
            max_validation_regenerations=0,
            deadline_seconds=5,
        ),
    )

    assert isinstance(outcome.error, StructuredSchemaError)


def test_token_exhaustion_is_not_parsed_as_valid_json() -> None:
    provider = FakeProvider(
        [
            _response(
                '{"name":"partial"',
                finish_reason="length",
            )
        ]
    )

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=StructuredRetryBudget(
            max_provider_calls=1,
            max_transport_retries=0,
            max_format_downgrades=0,
            max_validation_regenerations=0,
            deadline_seconds=5,
        ),
    )

    assert outcome.succeeded is False
    assert outcome.error is not None
    assert "failed after 1 provider call" in str(outcome.error)
