from __future__ import annotations

import json
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.providers.base import ChatMessage, ChatResponse, ProviderConfig
from app.providers.structured import (
    ProviderEmptyResponse,
    ProviderTimeout,
    StructuredCapabilities,
    StructuredContract,
    StructuredDecodeError,
    StructuredMode,
    StructuredOutputExhausted,
    StructuredOutputGateway,
    StructuredRetryBudget,
    StructuredSchemaError,
    StructuredSemanticError,
    UnsupportedStructuredMode,
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


class EnumPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["safe", "strict"]


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
        model: str = "test-model",
        capabilities: StructuredCapabilities | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.config = ProviderConfig(provider_type=provider_name, model=model)
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


def _budget(
    *,
    calls: int = 1,
    transport: int = 0,
    downgrade: int = 0,
    validation: int = 0,
    deadline: float = 5.0,
) -> StructuredRetryBudget:
    return StructuredRetryBudget(
        max_provider_calls=calls,
        max_transport_retries=transport,
        max_format_downgrades=downgrade,
        max_validation_regenerations=validation,
        deadline_seconds=deadline,
    )


def test_lmstudio_uses_projected_json_schema_and_returns_typed_value() -> None:
    provider = FakeProvider(
        [_response({"name": "alpha", "count": 3, "enabled": True, "tags": []})],
        model="lmstudio-success",
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


def test_openai_compatible_profile_prefers_json_object() -> None:
    provider = FakeProvider(
        [_response({"name": "remote", "count": 1, "enabled": True, "tags": []})],
        provider_name="openrouter",
        model="openrouter-json-object",
    )

    result = StructuredOutputGateway(provider).generate(
        _messages(), contract=EXAMPLE_CONTRACT
    )

    assert result.name == "remote"
    assert provider.calls[0]["response_format"] == {"type": "json_object"}


def test_typed_unsupported_mode_downgrades_to_text_once() -> None:
    provider = FakeProvider(
        [
            UnsupportedStructuredMode("schema mode unavailable"),
            _response({"name": "beta", "count": 1, "enabled": False, "tags": []}),
        ],
        model="typed-downgrade",
    )
    gateway = StructuredOutputGateway(provider)

    result = gateway.generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=_budget(calls=3, downgrade=1),
    )

    assert result.name == "beta"
    assert provider.calls[0]["response_format"]["type"] == "json_schema"
    assert provider.calls[1]["response_format"]["type"] == "text"
    assert gateway.last_diagnostics is not None
    assert gateway.last_diagnostics.format_downgrades == 1


def test_negative_capability_cache_skips_known_unsupported_mode() -> None:
    model = "negative-capability-cache-phase9"
    first = FakeProvider(
        [
            UnsupportedStructuredMode("schema mode unavailable"),
            _response({"name": "first", "count": 1, "enabled": True, "tags": []}),
        ],
        model=model,
    )
    StructuredOutputGateway(first).generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=_budget(calls=2, downgrade=1),
    )
    second = FakeProvider(
        [_response({"name": "second", "count": 2, "enabled": True, "tags": []})],
        model=model,
    )

    result = StructuredOutputGateway(second).generate(
        _messages(), contract=EXAMPLE_CONTRACT
    )

    assert result.name == "second"
    assert second.calls[0]["response_format"] == {"type": "text"}


def test_tool_call_arguments_are_canonical_structured_content() -> None:
    capabilities = StructuredCapabilities(
        preferred_modes=(StructuredMode.TOOL_CALL, StructuredMode.TEXT_JSON),
        supports_tool_arguments=True,
    )
    response = ChatResponse(
        content="",
        model="tool-model",
        finish_reason="tool_calls",
        tool_calls=[
            {
                "type": "function",
                "function": {
                    "name": "tests_structured_example",
                    "arguments": json.dumps(
                        {"name": "tool", "count": 7, "enabled": True, "tags": []}
                    ),
                },
            }
        ],
    )
    provider = FakeProvider(
        [response],
        provider_name="tool-provider",
        model="tool-arguments-phase9",
        capabilities=capabilities,
    )

    result = StructuredOutputGateway(provider).generate(
        _messages(), contract=EXAMPLE_CONTRACT
    )

    assert result.name == "tool"
    assert provider.calls[0]["tools"][0]["type"] == "function"


def test_fenced_and_surrounded_json_is_conservatively_extracted() -> None:
    provider = FakeProvider(
        [
            _response(
                "```json\n"
                '{"name":"gamma","count":2,"enabled":true,"tags":[]}'
                "\n```"
            )
        ],
        model="fenced-json",
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
        ],
        model="schema-correction",
    )
    gateway = StructuredOutputGateway(provider)

    result = gateway.generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=_budget(calls=2, validation=1),
    )

    assert result.count == 4
    retry_messages = provider.calls[1]["messages"]
    correction_message = next(
        message
        for message in retry_messages
        if "STRUCTURED_OUTPUT_CORRECTION" in message.content
    )
    correction = correction_message.content
    assert correction_message.role == "system"
    assert [m.role for m in retry_messages if m.role == "user"] == ["user"]
    assert retry_messages[-1].role == "user"
    assert retry_messages[-1].content == _messages()[0].content
    assert "STRUCTURED_OUTPUT_CORRECTION" in correction
    assert '"path": ["count"]' in correction
    assert gateway.last_diagnostics is not None
    assert gateway.last_diagnostics.validation_regenerations == 1


def test_semantic_failure_is_regenerated_when_contract_allows_it() -> None:
    def validate(value: ExamplePayload) -> None:
        if value.count != 5:
            raise ValueError("count_must_equal_five")

    contract = StructuredContract(
        contract_id="tests.structured.semantic",
        version=1,
        output_model=ExamplePayload,
        semantic_validator=validate,
    )
    provider = FakeProvider(
        [
            _response({"name": "semantic", "count": 3, "enabled": True, "tags": []}),
            _response({"name": "semantic", "count": 5, "enabled": True, "tags": []}),
        ],
        model="semantic-correction",
    )

    result = StructuredOutputGateway(provider).generate(
        _messages(),
        contract=contract,
        retry_budget=_budget(calls=2, validation=1),
    )

    assert result.count == 5
    assert "StructuredSemanticError" in provider.calls[1]["messages"][-1].content


def test_correction_attempt_remaining_invalid_returns_typed_failure() -> None:
    provider = FakeProvider(
        [
            _response({"name": "bad", "count": "wrong", "enabled": True}),
            _response({"name": "bad", "count": "still-wrong", "enabled": True}),
        ],
        model="correction-exhausted",
    )

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=_budget(calls=2, validation=1),
    )

    assert isinstance(outcome.error, StructuredSchemaError)
    assert outcome.diagnostics.provider_calls == 2


def test_semantic_failure_without_regeneration_is_typed() -> None:
    def reject(_value: ExamplePayload) -> None:
        raise ValueError("domain_reference_invalid")

    contract = StructuredContract(
        contract_id="tests.structured.semantic-final",
        version=1,
        output_model=ExamplePayload,
        semantic_validator=reject,
        regenerate_on_semantic_failure=False,
    )
    provider = FakeProvider(
        [_response({"name": "semantic", "count": 1, "enabled": True, "tags": []})],
        model="semantic-final",
    )

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(), contract=contract, retry_budget=_budget()
    )

    assert isinstance(outcome.error, StructuredSemanticError)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"name": "missing", "enabled": True, "tags": []},
        {"name": "extra", "count": 1, "enabled": True, "tags": [], "extra": 1},
        {"name": "wrong", "count": [], "enabled": True, "tags": []},
    ],
)
def test_invalid_root_and_schema_shapes_are_rejected(payload) -> None:
    provider = FakeProvider([_response(payload)], model=f"invalid-shape-{type(payload).__name__}")

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(), contract=EXAMPLE_CONTRACT, retry_budget=_budget()
    )

    assert outcome.succeeded is False
    assert isinstance(outcome.error, (StructuredDecodeError, StructuredSchemaError))


def test_invalid_enum_is_rejected() -> None:
    contract = StructuredContract(
        contract_id="tests.structured.enum",
        version=1,
        output_model=EnumPayload,
    )
    provider = FakeProvider([_response({"mode": "unknown"})], model="invalid-enum")

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(), contract=contract, retry_budget=_budget()
    )

    assert isinstance(outcome.error, StructuredSchemaError)


def test_invalid_json_is_a_failure_not_an_empty_object() -> None:
    provider = FakeProvider([_response("not json")], model="invalid-json")
    gateway = StructuredOutputGateway(provider)

    outcome = gateway.try_generate(
        _messages(), contract=EXAMPLE_CONTRACT, retry_budget=_budget()
    )

    assert outcome.value is None
    assert isinstance(outcome.error, StructuredDecodeError)


def test_empty_response_is_transport_failure_not_valid_emptiness() -> None:
    provider = FakeProvider(
        [ChatResponse(content="", model="test-model")],
        model="empty-response",
    )

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(), contract=EXAMPLE_CONTRACT, retry_budget=_budget()
    )

    assert isinstance(outcome.error, StructuredOutputExhausted)
    assert isinstance(outcome.error.last_error, ProviderEmptyResponse)


def test_valid_empty_payload_remains_distinct_from_failure() -> None:
    contract = StructuredContract(
        contract_id="tests.structured.empty",
        version=1,
        output_model=EmptyPayload,
    )
    provider = FakeProvider([_response({"rows": []})], model="valid-empty")

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(), contract=contract
    )

    assert outcome.succeeded is True
    assert outcome.value == EmptyPayload(rows=[])
    assert outcome.error is None


def test_strict_boolean_rejects_string_boolean() -> None:
    provider = FakeProvider(
        [_response({"name": "epsilon", "count": 1, "enabled": "false", "tags": []})],
        model="strict-boolean",
    )

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(), contract=EXAMPLE_CONTRACT, retry_budget=_budget()
    )

    assert isinstance(outcome.error, StructuredSchemaError)


def test_token_exhaustion_is_not_parsed_as_valid_json() -> None:
    provider = FakeProvider(
        [_response('{"name":"partial"', finish_reason="length")],
        model="token-exhaustion",
    )

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(), contract=EXAMPLE_CONTRACT, retry_budget=_budget()
    )

    assert outcome.succeeded is False
    assert isinstance(outcome.error, StructuredOutputExhausted)
    assert "failed after 1 provider call" in str(outcome.error)


def test_absolute_deadline_can_expire_before_provider_call() -> None:
    provider = FakeProvider(
        [_response({"name": "late", "count": 1, "enabled": True, "tags": []})],
        model="deadline-expired",
    )

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=_budget(deadline=1e-12),
    )

    assert isinstance(outcome.error, StructuredOutputExhausted)
    assert isinstance(outcome.error.last_error, ProviderTimeout)
    assert provider.calls == []


def test_provider_call_budget_caps_validation_attempts() -> None:
    provider = FakeProvider(
        [
            _response("not-json"),
            _response("still-not-json"),
            _response({"name": "too-late", "count": 1, "enabled": True, "tags": []}),
        ],
        model="provider-call-budget",
    )

    outcome = StructuredOutputGateway(provider).try_generate(
        _messages(),
        contract=EXAMPLE_CONTRACT,
        retry_budget=_budget(calls=2, validation=5),
    )

    assert isinstance(outcome.error, StructuredDecodeError)
    assert outcome.diagnostics.provider_calls == 2
    assert len(provider.calls) == 2
