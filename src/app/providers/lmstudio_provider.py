"""
LM Studio Provider Plugin

Implements the BaseProvider interface for local LM Studio servers.
LM Studio provides an OpenAI-compatible API on a configurable port.
"""

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

_NATIVE_CHAT_COMPLETIONS_ENDPOINT = "/api/v0/chat/completions"
_OPENAI_CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"


class LMStudioProvider(BaseProvider):
    """
    Provider for local LM Studio instances.

    LM Studio runs a local OpenAI-compatible API server on a configurable port.
    No authentication required, just point to the base URL.
    """

    provider_name = "lmstudio"
    provider_display_name = "LM Studio"
    provider_description = "Local LM Studio instance with OpenAI-compatible API"
    default_capabilities = [ProviderCapability.CHAT, ProviderCapability.STREAMING, ProviderCapability.MODELS]

    def _validate_config(self):
        """Validate LM Studio configuration."""
        if not self.config.base_url:
            self.config.base_url = "http://localhost:1234"
        # Ensure base_url doesn't have trailing slash
        self.config.base_url = self._normalize_local_base_url(
            self.config.base_url.rstrip('/')
        )

    @staticmethod
    def _normalize_local_base_url(base_url: str) -> str:
        """Avoid the recurring Windows localhost IPv6 fallback penalty."""

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
        """
        Make an HTTP request to the LM Studio API.

        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            ConnectionError: If connection fails
        """
        url = f"{self.config.base_url}{endpoint}"
        # Allow timeout override via kwargs
        timeout = kwargs.pop('timeout', self.config.timeout)
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
                raise ConnectionError(
                    f"HTTP error {response.status_code}: {exc}; response_body={body}"
                ) from exc
            return response
        except RequestsConnectionError as e:
            raise ConnectionError(f"Failed to connect to LM Studio at {url}: {e}")
        except RequestsTimeout as e:
            raise ConnectionError(f"Connection to LM Studio timed out: {e}")
        except RequestsHTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError(f"Authentication failed: {e}")
            raise ConnectionError(f"HTTP error {e.response.status_code}: {e}")
        except Exception as e:
            if isinstance(e, ConnectionError):
                raise
            raise ConnectionError(f"Unexpected error: {e}")

    def _make_chat_completion_request(
        self,
        payload: Dict[str, Any],
        *,
        stream: bool,
        include_metrics: bool,
    ) -> requests.Response:
        """Use the stats-bearing native endpoint only for explicit metric requests."""
        if not include_metrics:
            return self._make_request(
                'post',
                _OPENAI_CHAT_COMPLETIONS_ENDPOINT,
                json=payload,
                stream=stream,
            )

        endpoint = self._metrics_chat_completion_endpoint()
        try:
            return self._make_request(
                'post',
                endpoint,
                json=payload,
                stream=stream,
            )
        except ConnectionError as exc:
            if endpoint != _NATIVE_CHAT_COMPLETIONS_ENDPOINT or "HTTP error 404" not in str(exc):
                raise
            fallback_payload = dict(payload)
            if stream:
                fallback_payload["stream_options"] = {"include_usage": True}
            return self._make_request(
                'post',
                _OPENAI_CHAT_COMPLETIONS_ENDPOINT,
                json=fallback_payload,
                stream=stream,
            )

    def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[ChatResponse, Iterator[ChatResponse]]:
        """
        Generate a chat completion using LM Studio.

        Args:
            messages: List of chat messages
            model: Optional model override
            stream: Whether to stream the response
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            ChatResponse or iterator of ChatResponse chunks

        Raises:
            AuthenticationError: If authentication fails
            ConnectionError: If connection fails
            ModelNotFoundError: If model doesn't exist
        """
        _trace_row = provider_call_enter(
            provider="lmstudio",
            method="chat_completion",
            model=model,
            messages=messages,
            extra={
                "stream": bool(stream),
                "kwargs_keys": sorted(list(kwargs.keys())),
            },
        )
        try:
            if not messages:
                raise ValueError("Messages list cannot be empty")

            resolved_model = model or self.config.model
            include_metrics = bool(kwargs.get("include_metrics", False))
            payload = {
                "messages": [msg.to_dict() for msg in messages],
                "temperature": kwargs.get("temperature", 0.7),
                "stream": stream,
            }

            # LM Studio can reject an empty model string with HTTP 400.
            # If no model is configured, omit the field and let the server use
            # its currently loaded model.
            if resolved_model:
                payload["model"] = resolved_model

            # Add other optional parameters only if explicitly provided.
            # include_metrics is an Omnix adapter option, not an LM Studio field.
            for key in ["max_tokens", "top_p", "response_format", "chat_template_kwargs"]:
                if key in kwargs:
                    payload[key] = kwargs[key]

            if stream:
                result = self._stream_completion(
                    payload,
                    include_metrics=include_metrics,
                )
            else:
                result = self._non_stream_completion(
                    payload,
                    include_metrics=include_metrics,
                )
            provider_call_exit(_trace_row, ok=True)
            return result
        except Exception as exc:
            provider_call_exit(_trace_row, ok=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def _non_stream_completion(
        self,
        payload: Dict[str, Any],
        *,
        include_metrics: bool = False,
    ) -> ChatResponse:
        """Handle non-streaming completion."""
        response = self._make_chat_completion_request(
            payload,
            stream=False,
            include_metrics=include_metrics,
        )

        try:
            data = response.json()
        except ValueError as e:
            raise ConnectionError(f"Invalid JSON response: {e}")

        choices = data.get('choices', [])
        if not choices:
            raise ConnectionError("No choices in response")

        message = choices[0].get('message', {})
        content = message.get('content', '')
        thinking = message.get('reasoning') or message.get('thinking')

        return ChatResponse(
            content=content,
            model=data.get('model', payload.get('model', '')),
            usage=data.get('usage'),
            thinking=thinking,
            reasoning=thinking,
            finish_reason=choices[0].get('finish_reason'),
            raw_response=data,
        )

    def _stream_completion(
        self,
        payload: Dict[str, Any],
        *,
        include_metrics: bool = False,
    ) -> Iterator[ChatResponse]:
        """Handle streaming completion and retain the final usage or stats chunk."""
        try:
            response = self._make_chat_completion_request(
                payload,
                stream=True,
                include_metrics=include_metrics,
            )
        except Exception as e:
            raise ConnectionError(f"Failed to start stream: {e}")

        thinking_buffer = ""
        usage: Dict[str, Any] | None = None
        finish_reason: str | None = None
        resolved_model = str(payload.get('model') or '')
        last_response: Dict[str, Any] | None = None

        try:
            for line in response.iter_lines():
                if not line:
                    continue

                line_str = line.decode('utf-8') if isinstance(line, bytes) else line
                if not line_str.startswith('data: '):
                    continue

                data_str = line_str[6:].strip()
                if data_str == '[DONE]':
                    break

                try:
                    data = json.loads(data_str)
                    if not isinstance(data, dict):
                        continue

                    choices = data.get('choices')
                    choice = (
                        choices[0]
                        if isinstance(choices, list)
                        and choices
                        and isinstance(choices[0], dict)
                        else {}
                    )
                    delta = choice.get('delta') if isinstance(choice.get('delta'), dict) else {}

                    reasoning = delta.get('reasoning')
                    if isinstance(reasoning, str):
                        thinking_buffer += reasoning
                    content = delta.get('content')
                    if not isinstance(content, str):
                        content = ''

                    chunk_usage = data.get('usage')
                    if isinstance(chunk_usage, dict):
                        usage = chunk_usage
                    chunk_finish_reason = choice.get('finish_reason')
                    if chunk_finish_reason:
                        finish_reason = str(chunk_finish_reason)
                    resolved_model = str(data.get('model') or resolved_model)
                    last_response = data

                    yield ChatResponse(
                        content=content,
                        model=resolved_model,
                        usage=chunk_usage if isinstance(chunk_usage, dict) else None,
                        thinking=reasoning if isinstance(reasoning, str) else None,
                        reasoning=reasoning if isinstance(reasoning, str) else None,
                        finish_reason=str(chunk_finish_reason) if chunk_finish_reason else None,
                        raw_response=data,
                    )
                except (ValueError, SyntaxError, KeyError, IndexError, TypeError):
                    continue

            # Final response carries usage, finish reason, and a stats-bearing
            # final payload even when it has no text content.
            yield ChatResponse(
                content="",
                model=resolved_model,
                usage=usage,
                thinking=thinking_buffer if thinking_buffer else None,
                reasoning=thinking_buffer if thinking_buffer else None,
                finish_reason=finish_reason,
                raw_response=last_response,
            )

        except Exception as e:
            raise ConnectionError(f"Stream error: {e}")

    def get_models(self) -> List[ModelInfo]:
        """
        Get list of available models from LM Studio.

        Returns:
            List of ModelInfo objects

        Raises:
            ConnectionError: If unable to fetch models
        """
        try:
            response = self._make_request('get', '/v1/models')
            data = response.json()

            models = []
            for model_data in data.get('data', []):
                model_info = ModelInfo(
                    id=model_data.get('id', ''),
                    name=model_data.get('id', ''),
                    provider=self.provider_name,
                    context_length=model_data.get('context_length'),
                    description=model_data.get('description', ''),
                    metadata={
                        'owned_by': model_data.get('owned_by', ''),
                        'permission': model_data.get('permission', []),
                    }
                )
                models.append(model_info)

            # If no models or empty data, also try the alternate endpoint
            if not models:
                models = self._get_models_alternate()

            return models

        except Exception as e:
            raise ConnectionError(f"Failed to fetch models: {e}")

    def _get_models_alternate(self) -> List[ModelInfo]:
        """Try alternate LM Studio endpoint for models."""
        try:
            response = self._make_request('get', '/api/v0/models')
            data = response.json()

            models = []
            for model_data in data:
                if isinstance(model_data, dict):
                    model_info = ModelInfo(
                        id=model_data.get('model', model_data.get('id', '')),
                        name=model_data.get('name', model_data.get('model', '')),
                        provider=self.provider_name,
                        context_length=model_data.get('context_length'),
                        description=model_data.get('description', ''),
                        metadata={}
                    )
                    models.append(model_info)

            return models
        except Exception:
            return []

    def test_connection(self) -> bool:
        """
        Test connection to LM Studio.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self._make_request('get', '/v1/models', timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def requires_api_key(self) -> bool:
        """LM Studio doesn't require an API key."""
        return False

    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get configuration schema for LM Studio provider.

        Returns:
            Dictionary with configuration fields and metadata
        """
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
                    "description": "URL of the LM Studio server"
                },
                {
                    "name": "model",
                    "type": "string",
                    "label": "Default Model",
                    "required": False,
                    "description": "Default model to use (optional)"
                }
            ]
        }
