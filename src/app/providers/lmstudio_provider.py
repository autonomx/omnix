"""LM Studio provider plugin."""
from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional, Union
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError as RequestsHTTPError
from requests.exceptions import Timeout as RequestsTimeout

from .base import (
    AuthenticationError,
    BaseProvider,
    ChatMessage,
    ChatResponse,
    ConnectionError,
    ModelInfo,
    ProviderCapability,
)
from .provider_trace import provider_call_enter, provider_call_exit
from .structured.transport import (
    pop_structured_transport_options,
    raise_if_structured_mode_rejected,
)

_NATIVE_CHAT_COMPLETIONS_ENDPOINT = "/api/v0/chat/completions"
_OPENAI_CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"
_DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class LMStudioProvider(BaseProvider):
    """Provider for local LM Studio OpenAI-compatible servers."""

    provider_name = "lmstudio"
    provider_display_name = "LM Studio"
    provider_description = "Local LM Studio instance with OpenAI-compatible API"
    default_capabilities = [
        ProviderCapability.CHAT,
        ProviderCapability.STREAMING,
        ProviderCapability.MODELS,
    ]

    def _validate_config(self):
        if not self.config.base_url:
            self.config.base_url = "http://localhost:1234"
        self.config.base_url = self._normalize_local_base_url(
            self.config.base_url.rstrip("/")
        )

    @staticmethod
    def _normalize_local_base_url(base_url: str) -> str:
        parsed = urlsplit(base_url)
        if parsed.hostname not in {"localhost", "localhost.localdomain"}:
            return base_url
        port = f":{parsed.port}" if parsed.port is not None else ""
        return urlunsplit(
            (parsed.scheme, f"127.0.0.1{port}", parsed.path, parsed.query, parsed.fragment)
        )

    def _metrics_chat_completion_endpoint(self) -> str:
        configured = str(
            self.config.extra_params.get("metrics_chat_completions_endpoint") or ""
        ).strip()
        if not configured:
            return _NATIVE_CHAT_COMPLETIONS_ENDPOINT
        return configured if configured.startswith("/") else f"/{configured}"

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = f"{self.config.base_url}{endpoint}"
        timeout = kwargs.pop("timeout", self.config.timeout)
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
            try:
                response.raise_for_status()
            except Exception as exc:
                body = ""
                try:
                    body = response.text[:2000]
                except Exception:
                    body = ""
                raise_if_structured_mode_rejected(
                    status_code=response.status_code,
                    response_body=body,
                    error=exc,
                )
                raise ConnectionError(
                    f"HTTP error {response.status_code}: {exc}; response_body={body}"
                ) from exc
            return response
        except RequestsConnectionError as exc:
            raise ConnectionError(f"Failed to connect to LM Studio at {url}: {exc}") from exc
        except RequestsTimeout as exc:
            raise ConnectionError(f"Connection to LM Studio timed out: {exc}") from exc
        except RequestsHTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise AuthenticationError(f"Authentication failed: {exc}") from exc
            raise ConnectionError(f"HTTP error: {exc}") from exc
        except Exception as exc:
            if isinstance(exc, (ConnectionError, AuthenticationError)):
                raise
            raise ConnectionError(f"Unexpected error: {exc}") from exc

    def _make_chat_completion_request(
        self,
        payload: Dict[str, Any],
        *,
        stream: bool,
        include_metrics: bool,
        timeout: float | None = None,
    ) -> requests.Response:
        request_kwargs: Dict[str, Any] = {"json": payload, "stream": stream}
        if timeout is not None:
            request_kwargs["timeout"] = timeout
        if not include_metrics:
            return self._make_request(
                "post",
                _OPENAI_CHAT_COMPLETIONS_ENDPOINT,
                **request_kwargs,
            )
        endpoint = self._metrics_chat_completion_endpoint()
        try:
            return self._make_request("post", endpoint, **request_kwargs)
        except ConnectionError as exc:
            if endpoint != _NATIVE_CHAT_COMPLETIONS_ENDPOINT or "HTTP error 404" not in str(exc):
                raise
            fallback_payload = dict(payload)
            if stream:
                fallback_payload["stream_options"] = {"include_usage": True}
            request_kwargs["json"] = fallback_payload
            return self._make_request(
                "post",
                _OPENAI_CHAT_COMPLETIONS_ENDPOINT,
                **request_kwargs,
            )

    def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs,
    ) -> Union[ChatResponse, Iterator[ChatResponse]]:
        use_configured_model = bool(kwargs.pop("_use_configured_model", True))
        trace_row = provider_call_enter(
            provider="lmstudio",
            method="chat_completion",
            model=model,
            messages=messages,
            extra={
                "stream": bool(stream),
                "kwargs_keys": sorted(kwargs),
                "use_configured_model": use_configured_model,
            },
        )
        try:
            if not messages:
                raise ValueError("Messages list cannot be empty")
            transport = pop_structured_transport_options(kwargs)
            resolved_model = model or (
                self.config.model if use_configured_model else None
            )
            include_metrics = bool(kwargs.get("include_metrics", False))
            payload: Dict[str, Any] = {
                "messages": [message.to_dict() for message in messages],
                "temperature": kwargs.get("temperature", 0.7),
                "stream": stream,
                **transport.payload_options,
            }
            if resolved_model:
                payload["model"] = resolved_model
            for key in ["max_tokens", "top_p", "chat_template_kwargs"]:
                if key in kwargs:
                    payload[key] = kwargs[key]
            timeout = transport.request_timeout_seconds
            result = (
                self._stream_completion(
                    payload,
                    include_metrics=include_metrics,
                    timeout=timeout,
                )
                if stream
                else self._non_stream_completion(
                    payload,
                    include_metrics=include_metrics,
                    timeout=timeout,
                )
            )
            provider_call_exit(trace_row, ok=True)
            return result
        except Exception as exc:
            provider_call_exit(trace_row, ok=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def _non_stream_completion(
        self,
        payload: Dict[str, Any],
        *,
        include_metrics: bool = False,
        timeout: float | None = None,
    ) -> ChatResponse:
        response = self._make_chat_completion_request(
            payload,
            stream=False,
            include_metrics=include_metrics,
            timeout=timeout,
        )
        max_response_bytes = max(
            1,
            int(
                self.config.extra_params.get("max_response_bytes")
                or _DEFAULT_MAX_RESPONSE_BYTES
            ),
        )
        try:
            declared_length = int(response.headers.get("content-length") or 0)
        except (TypeError, ValueError):
            declared_length = 0
        if declared_length > max_response_bytes:
            raise ConnectionError(
                "LM Studio response exceeds configured byte limit: "
                f"{declared_length}>{max_response_bytes}"
            )
        if len(response.content) > max_response_bytes:
            raise ConnectionError(
                "LM Studio response exceeds configured byte limit: "
                f"{len(response.content)}>{max_response_bytes}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ConnectionError(f"Invalid JSON response: {exc}") from exc
        choices = data.get("choices", [])
        if not choices:
            raise ConnectionError("No choices in response")
        message = choices[0].get("message", {})
        thinking = message.get("reasoning") or message.get("thinking")
        tool_calls = message.get("tool_calls")
        return ChatResponse(
            content=message.get("content", ""),
            model=data.get("model", payload.get("model", "")),
            usage=data.get("usage"),
            thinking=thinking,
            reasoning=thinking,
            tool_calls=tool_calls if isinstance(tool_calls, list) else None,
            finish_reason=choices[0].get("finish_reason"),
            raw_response=data,
        )

    def _stream_completion(
        self,
        payload: Dict[str, Any],
        *,
        include_metrics: bool = False,
        timeout: float | None = None,
    ) -> Iterator[ChatResponse]:
        try:
            response = self._make_chat_completion_request(
                payload,
                stream=True,
                include_metrics=include_metrics,
                timeout=timeout,
            )
        except Exception as exc:
            raise ConnectionError(f"Failed to start stream: {exc}") from exc
        thinking_buffer = ""
        usage: Dict[str, Any] | None = None
        finish_reason: str | None = None
        resolved_model = str(payload.get("model") or "")
        last_response: Dict[str, Any] | None = None
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                line_text = line.decode("utf-8") if isinstance(line, bytes) else line
                if not line_text.startswith("data: "):
                    continue
                data_text = line_text[6:].strip()
                if data_text == "[DONE]":
                    break
                try:
                    data = json.loads(data_text)
                    if not isinstance(data, dict):
                        continue
                    choices = data.get("choices")
                    choice = (
                        choices[0]
                        if isinstance(choices, list)
                        and choices
                        and isinstance(choices[0], dict)
                        else {}
                    )
                    delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                    reasoning = delta.get("reasoning")
                    if isinstance(reasoning, str):
                        thinking_buffer += reasoning
                    content = delta.get("content")
                    if not isinstance(content, str):
                        content = ""
                    chunk_usage = data.get("usage")
                    if isinstance(chunk_usage, dict):
                        usage = chunk_usage
                    chunk_finish_reason = choice.get("finish_reason")
                    if chunk_finish_reason:
                        finish_reason = str(chunk_finish_reason)
                    resolved_model = str(data.get("model") or resolved_model)
                    last_response = data
                    yield ChatResponse(
                        content=content,
                        model=resolved_model,
                        usage=chunk_usage if isinstance(chunk_usage, dict) else None,
                        thinking=reasoning if isinstance(reasoning, str) else None,
                        reasoning=reasoning if isinstance(reasoning, str) else None,
                        tool_calls=(
                            delta.get("tool_calls")
                            if isinstance(delta.get("tool_calls"), list)
                            else None
                        ),
                        finish_reason=(
                            str(chunk_finish_reason) if chunk_finish_reason else None
                        ),
                        raw_response=data,
                    )
                except (ValueError, SyntaxError, KeyError, IndexError, TypeError):
                    continue
            yield ChatResponse(
                content="",
                model=resolved_model,
                usage=usage,
                thinking=thinking_buffer if thinking_buffer else None,
                reasoning=thinking_buffer if thinking_buffer else None,
                finish_reason=finish_reason,
                raw_response=last_response,
            )
        except Exception as exc:
            raise ConnectionError(f"Stream error: {exc}") from exc

    def get_models(self) -> List[ModelInfo]:
        try:
            response = self._make_request("get", "/v1/models")
            data = response.json()
            models = [
                ModelInfo(
                    id=model_data.get("id", ""),
                    name=model_data.get("id", ""),
                    provider=self.provider_name,
                    context_length=model_data.get("context_length"),
                    description=model_data.get("description", ""),
                    metadata={
                        "owned_by": model_data.get("owned_by", ""),
                        "permission": model_data.get("permission", []),
                    },
                )
                for model_data in data.get("data", [])
            ]
            return models or self._get_models_alternate()
        except Exception as exc:
            raise ConnectionError(f"Failed to fetch models: {exc}") from exc

    def _get_models_alternate(self) -> List[ModelInfo]:
        try:
            response = self._make_request("get", "/api/v0/models")
            data = response.json()
            models: List[ModelInfo] = []
            for model_data in data:
                if isinstance(model_data, dict):
                    models.append(
                        ModelInfo(
                            id=model_data.get("model", model_data.get("id", "")),
                            name=model_data.get("name", model_data.get("model", "")),
                            provider=self.provider_name,
                            context_length=model_data.get("context_length"),
                            description=model_data.get("description", ""),
                            metadata={},
                        )
                    )
            return models
        except Exception:
            return []

    def test_connection(self) -> bool:
        try:
            response = self._make_request("get", "/v1/models", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def requires_api_key(self) -> bool:
        return False

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "provider_type": self.provider_name,
            "display_name": self.provider_display_name,
            "description": self.provider_description,
            "fields": [
                {
                    "name": "base_url",
                    "type": "string",
                    "label": "Base URL",
                    "default": "http://localhost:1234",
                    "required": True,
                    "description": "URL of the LM Studio server",
                },
                {
                    "name": "model",
                    "type": "string",
                    "label": "Default Model",
                    "required": False,
                    "description": "Fallback model used when LM Studio has no loaded LLM",
                },
            ],
        }
