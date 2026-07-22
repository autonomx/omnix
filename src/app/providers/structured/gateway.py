"""Central provider-independent structured-output gateway."""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import replace
from time import monotonic
from typing import Any, Generic, Mapping, Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from app.providers.base import BaseProvider, ChatMessage, ChatResponse

from .contracts import (
    StructuredCapabilities,
    StructuredContract,
    StructuredDiagnostics,
    StructuredMode,
    StructuredOutcome,
    StructuredRetryBudget,
)
from .errors import (
    ProviderEmptyResponse,
    ProviderTimeout,
    ProviderTransportError,
    ProviderTruncatedResponse,
    StructuredDecodeError,
    StructuredOutputError,
    StructuredOutputExhausted,
    StructuredSchemaError,
    StructuredSemanticError,
    StructuredValidationIssue,
    UnsupportedStructuredMode,
)
from .parsing import canonical_structured_text, decode_json_object
from .schema_projection import project_provider_schema

T = TypeVar("T", bound=BaseModel)


class _NegativeCapabilityCache:
    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._values: dict[tuple[str, str, str, StructuredMode], float] = {}
        self._lock = threading.Lock()

    def mark_unsupported(self, key: tuple[str, str, str], mode: StructuredMode) -> None:
        with self._lock:
            self._values[(*key, mode)] = monotonic() + self.ttl_seconds

    def is_unsupported(self, key: tuple[str, str, str], mode: StructuredMode) -> bool:
        now = monotonic()
        compound = (*key, mode)
        with self._lock:
            expires = self._values.get(compound)
            if expires is None:
                return False
            if expires <= now:
                self._values.pop(compound, None)
                return False
            return True


_NEGATIVE_CAPABILITIES = _NegativeCapabilityCache()


def _validation_issues(error: ValidationError) -> tuple[StructuredValidationIssue, ...]:
    issues: list[StructuredValidationIssue] = []
    for row in error.errors(include_url=False):
        context = row.get("ctx")
        issues.append(
            StructuredValidationIssue(
                path=tuple(row.get("loc") or ()),
                error_type=str(row.get("type") or "validation_error"),
                message=str(row.get("msg") or "validation failed"),
                context=dict(context) if isinstance(context, Mapping) else None,
            )
        )
    return tuple(issues)


def _unsupported_mode_error(error: Exception) -> bool:
    if isinstance(error, UnsupportedStructuredMode):
        return True
    text = str(error).casefold()
    return any(
        marker in text
        for marker in (
            "response_format",
            "json_schema",
            "json_object",
            "structured output",
            "tool_choice",
            "tools are not supported",
        )
    )


def _provider_identity(provider: Any, model: str) -> tuple[str, str, str]:
    provider_name = str(getattr(provider, "provider_name", provider.__class__.__name__) or "")
    config = getattr(provider, "config", None)
    base_url = str(getattr(config, "base_url", "") or "")
    return provider_name.casefold(), base_url, model


def _provider_capabilities(provider: Any, model: str) -> StructuredCapabilities:
    method = getattr(provider, "get_structured_capabilities", None)
    if callable(method):
        try:
            value = method(model=model or None)
        except TypeError:
            value = method()
        if isinstance(value, StructuredCapabilities):
            return value
    return StructuredCapabilities.default_for_provider(
        str(getattr(provider, "provider_name", "") or "")
    )


def _response_options(
    contract: StructuredContract[Any],
    *,
    mode: StructuredMode,
    provider_name: str,
    capabilities: StructuredCapabilities,
) -> dict[str, Any]:
    schema = project_provider_schema(
        contract.output_model.model_json_schema(),
        mode=mode,
        provider_name=provider_name,
        schema_profile=contract.schema_profile,
    )
    if mode is StructuredMode.JSON_SCHEMA:
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": contract.provider_schema_name,
                    "strict": capabilities.supports_strict_schema,
                    "schema": schema,
                },
            }
        }
    if mode is StructuredMode.JSON_OBJECT:
        return {"response_format": {"type": "json_object"}}
    if mode is StructuredMode.TEXT_JSON:
        return {"response_format": {"type": "text"}}
    if mode is StructuredMode.TOOL_CALL:
        tool_name = contract.provider_schema_name
        return {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": f"Return {contract.qualified_id}",
                        "parameters": schema,
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
        }
    raise UnsupportedStructuredMode(f"unsupported structured mode: {mode.value}")


def _correction_message(
    contract: StructuredContract[Any],
    error: StructuredOutputError,
) -> ChatMessage:
    issues = getattr(error, "issues", ())
    payload = {
        "contract_id": contract.contract_id,
        "contract_version": contract.version,
        "reason": type(error).__name__,
        "message": str(error),
        "errors": [issue.as_dict() for issue in issues],
        "instruction": (
            "Regenerate the complete response. Return exactly one JSON object matching "
            "the contract. Do not explain, patch, omit invalid rows, or wrap the object."
        ),
    }
    return ChatMessage(
        role="user",
        content="STRUCTURED_OUTPUT_CORRECTION:\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )


class StructuredOutputGateway(Generic[T]):
    """Obtain, decode, and validate one provider-independent structured value."""

    def __init__(self, provider: BaseProvider | Any) -> None:
        self.provider = provider
        self.last_diagnostics: StructuredDiagnostics | None = None

    def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        contract: StructuredContract[T],
        model: str | None = None,
        retry_budget: StructuredRetryBudget | None = None,
        provider_options: Mapping[str, Any] | None = None,
    ) -> T:
        outcome = self.try_generate(
            messages,
            contract=contract,
            model=model,
            retry_budget=retry_budget,
            provider_options=provider_options,
        )
        if outcome.error is not None:
            raise outcome.error
        assert outcome.value is not None
        return outcome.value

    def try_generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        contract: StructuredContract[T],
        model: str | None = None,
        retry_budget: StructuredRetryBudget | None = None,
        provider_options: Mapping[str, Any] | None = None,
    ) -> StructuredOutcome[T]:
        budget = retry_budget or StructuredRetryBudget()
        config = getattr(self.provider, "config", None)
        resolved_model = str(model or getattr(config, "model", "") or "")
        provider_name = str(
            getattr(self.provider, "provider_name", self.provider.__class__.__name__) or ""
        )
        identity = _provider_identity(self.provider, resolved_model)
        capabilities = _provider_capabilities(self.provider, resolved_model)
        modes = tuple(
            mode
            for mode in capabilities.preferred_modes
            if not _NEGATIVE_CAPABILITIES.is_unsupported(identity, mode)
        ) or (StructuredMode.TEXT_JSON,)
        schema_text = json.dumps(
            contract.output_model.model_json_schema(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        schema_hash = hashlib.sha256(schema_text.encode("utf-8")).hexdigest()
        started = monotonic()
        deadline = started + budget.deadline_seconds
        provider_calls = 0
        transport_retries = 0
        format_downgrades = 0
        validation_regenerations = 0
        attempted_modes: list[StructuredMode] = []
        selected_mode: StructuredMode | None = None
        finish_reason = ""
        usage: dict[str, Any] = {}
        raw_length = 0
        raw_hash = ""
        last_error: Exception | None = None
        working_messages = list(messages)
        mode_index = 0

        def diagnostics() -> StructuredDiagnostics:
            return StructuredDiagnostics(
                contract_id=contract.contract_id,
                contract_version=contract.version,
                schema_hash=schema_hash,
                provider=provider_name,
                model=resolved_model,
                selected_mode=selected_mode,
                attempted_modes=tuple(attempted_modes),
                provider_calls=provider_calls,
                transport_retries=transport_retries,
                format_downgrades=format_downgrades,
                validation_regenerations=validation_regenerations,
                finish_reason=finish_reason,
                latency_ms=round((monotonic() - started) * 1000.0, 3),
                usage=usage,
                raw_response_length=raw_length,
                raw_response_hash=raw_hash,
            )

        while provider_calls < budget.max_provider_calls and mode_index < len(modes):
            if monotonic() >= deadline:
                last_error = ProviderTimeout(
                    f"structured operation {contract.qualified_id} exceeded its deadline"
                )
                break
            mode = modes[mode_index]
            selected_mode = mode
            attempted_modes.append(mode)
            options = dict(provider_options or {})
            options.setdefault("temperature", contract.temperature)
            if contract.max_tokens is not None:
                options.setdefault("max_tokens", contract.max_tokens)
            options.update(
                _response_options(
                    contract,
                    mode=mode,
                    provider_name=provider_name,
                    capabilities=capabilities,
                )
            )
            provider_calls += 1
            try:
                response = self.provider.chat_completion(
                    list(working_messages),
                    model=resolved_model or None,
                    stream=False,
                    **options,
                )
                if not isinstance(response, ChatResponse):
                    raise ProviderTransportError(
                        "structured provider returned a streaming or invalid response"
                    )
                finish_reason = str(response.finish_reason or "")
                usage = dict(response.usage or {})
                if finish_reason.casefold() in {"length", "max_tokens", "token_limit"}:
                    raise ProviderTruncatedResponse(
                        f"structured provider truncated {contract.qualified_id}"
                    )
                raw_text = canonical_structured_text(response)
                raw_length = len(raw_text)
                raw_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
                payload = decode_json_object(raw_text)
                try:
                    value = contract.output_model.model_validate(payload)
                except ValidationError as exc:
                    raise StructuredSchemaError(
                        f"{contract.qualified_id} failed schema validation",
                        _validation_issues(exc),
                    ) from exc
                if contract.semantic_validator is not None:
                    try:
                        contract.semantic_validator(value)
                    except StructuredSemanticError:
                        raise
                    except Exception as exc:
                        raise StructuredSemanticError(
                            f"{contract.qualified_id} failed semantic validation: {exc}"
                        ) from exc
                result_diagnostics = diagnostics()
                self.last_diagnostics = result_diagnostics
                return StructuredOutcome.success(value, result_diagnostics)
            except Exception as exc:
                last_error = exc
                if _unsupported_mode_error(exc):
                    _NEGATIVE_CAPABILITIES.mark_unsupported(identity, mode)
                    if format_downgrades < budget.max_format_downgrades:
                        format_downgrades += 1
                        mode_index += 1
                        continue
                if isinstance(exc, (StructuredDecodeError, StructuredSchemaError)) or (
                    isinstance(exc, StructuredSemanticError)
                    and contract.regenerate_on_semantic_failure
                ):
                    if validation_regenerations < budget.max_validation_regenerations:
                        validation_regenerations += 1
                        working_messages = [*messages, _correction_message(contract, exc)]
                        continue
                if isinstance(
                    exc,
                    (
                        ProviderTransportError,
                        ProviderEmptyResponse,
                        ProviderTimeout,
                        ProviderTruncatedResponse,
                    ),
                ) and transport_retries < budget.max_transport_retries:
                    transport_retries += 1
                    continue
                break

        if isinstance(last_error, StructuredOutputError):
            final_error: Exception = last_error
        else:
            final_error = StructuredOutputExhausted(
                f"structured operation {contract.qualified_id} failed after "
                f"{provider_calls} provider call(s)",
                last_error=last_error,
            )
        result_diagnostics = diagnostics()
        self.last_diagnostics = result_diagnostics
        return StructuredOutcome.failure(final_error, result_diagnostics)
