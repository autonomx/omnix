"""Audiobook model calls through the structured-output gateway (WP-8.4).

The audiobook classifiers expect one JSON object per call. The gateway decodes
it (exactly one bare object, as before), detects truncation and records
diagnostics; the callers' parsers check each task's fields and repair known
mistakes.

The request reaching the provider is the one the classifiers sent before the
gateway: no response format, no temperature, no model override. Provider-native
JSON modes would change how reasoning models answer these prompts and need a
quality evaluation first.

One markdown code fence around the whole reply is taken off before decoding:
Haiku 4.5 through the Claude CLI fenced every story batch despite the prompt,
and each batch was rejected. An open ``{"type": "object"}`` schema was tried
instead and made it return the answer as a string inside ``{"data": ...}``.
Anything else around the object (prose, a second fence) is still rejected.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.providers import ChatMessage
from app.providers.base import ChatResponse
from app.providers.structured import (
    ProviderEmptyResponse,
    ProviderTruncatedResponse,
    StructuredCapabilities,
    StructuredContract,
    StructuredMode,
    StructuredOutputError,
    StructuredOutputExhausted,
    StructuredOutputGateway,
    StructuredRetryBudget,
)


class _JsonObject(BaseModel):
    """One JSON object; the caller's parser validates its fields."""

    model_config = ConfigDict(extra="allow")


_WHOLE_REPLY_FENCE = re.compile(r"\A```(?:json)?[ \t]*\r?\n(.*?)\r?\n[ \t]*```\Z", re.DOTALL | re.IGNORECASE)


def _unfenced(content: Any) -> Any:
    """The reply inside one code fence that wraps all of it; any other reply unchanged."""
    if not isinstance(content, str):
        return content
    match = _WHOLE_REPLY_FENCE.match(content.strip())
    return match.group(1) if match else content


class UnusableReply(ValueError):
    """A reply that is not one usable JSON object; ``reply`` is its text, kept for the classification log."""

    def __init__(self, message: str, reply: Any = None) -> None:
        super().__init__(message)
        self.reply = reply


class _UnchangedRequestProvider:
    """Present a provider to the gateway without changing the request it receives."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self.served_model: str | None = None
        self.last_reply: Any = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    def get_structured_capabilities(self, model: str | None = None) -> StructuredCapabilities:
        return StructuredCapabilities(preferred_modes=(StructuredMode.TEXT_JSON,))

    def chat_completion(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        for added in ("response_format", "temperature", "model"):
            kwargs.pop(added, None)
        response = self._provider.chat_completion(messages=messages, **kwargs)
        self.served_model = getattr(response, "model", None)
        self.last_reply = getattr(response, "content", None)
        if isinstance(response, ChatResponse):
            response.content = _unfenced(response.content)
            return response
        return ChatResponse(
            content=_unfenced(getattr(response, "content", "") or ""),
            model=self.served_model or "",
            usage=getattr(response, "usage", None),
            finish_reason=getattr(response, "finish_reason", None),
        )


def json_object_call(
    provider: Any,
    messages: list[ChatMessage],
    *,
    contract_id: str,
    request_timeout_seconds: float,
    options: dict[str, Any],
    thinking: bool = True,
) -> tuple[dict[str, Any], str | None]:
    """Make one provider call for a JSON object; return it and the serving model.

    One provider call per request: the callers own retries, repairs and
    escalation. Unusable output (not one JSON object, empty, truncated) raises
    ``UnusableReply``, a ``ValueError`` like the parse failure it is, carrying
    the reply's text; a provider failure is raised unchanged, as before the
    gateway.
    """
    unchanged = _UnchangedRequestProvider(provider)
    contract = StructuredContract(
        contract_id=contract_id,
        version=1,
        output_model=_JsonObject,
        regenerate_on_semantic_failure=False,
        exact_json_object=True,
        thinking=thinking,
    )
    budget = StructuredRetryBudget(
        max_provider_calls=1,
        max_transport_retries=0,
        max_format_downgrades=0,
        max_validation_regenerations=0,
        # Longer than the request timeout, so the provider receives all of it.
        deadline_seconds=request_timeout_seconds + 5.0,
    )
    try:
        value = StructuredOutputGateway(unchanged).generate(
            messages,
            contract=contract,
            retry_budget=budget,
            provider_options={"request_timeout_seconds": request_timeout_seconds, **options},
        )
    except StructuredOutputExhausted as exc:
        cause = exc.last_error
        if cause is not None and not isinstance(cause, (ProviderEmptyResponse, ProviderTruncatedResponse)):
            raise cause from None
        raise UnusableReply(
            f"{contract_id} returned an unusable response: {cause or exc}", unchanged.last_reply,
        ) from exc
    except StructuredOutputError as exc:
        raise UnusableReply(
            f"{contract_id} returned an unusable response: {exc}", unchanged.last_reply,
        ) from exc
    return value.model_dump(), unchanged.served_model
