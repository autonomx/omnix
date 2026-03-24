"""
LM Studio Provider Plugin

Implements the BaseProvider interface for local LM Studio servers.
LM Studio provides an OpenAI-compatible API on a configurable port.
"""

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout as RequestsTimeout, HTTPError as RequestsHTTPError
from typing import List, Optional, Dict, Any, Iterator, Union
from dataclasses import field

from .base import BaseProvider, ChatMessage, ChatResponse, ModelInfo, ProviderConfig, ProviderCapability, AuthenticationError, ConnectionError, ModelNotFoundError, ProviderError


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
        self.config.base_url = self.config.base_url.rstrip('/')

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
            response.raise_for_status()
            return response
        except RequestsConnectionError as e:
            raise ConnectionError(f"Failed to connect to LM Studio at {url}: {e}")
        except RequestsTimeout as e:
            raise ConnectionError(f"Connection to LM Studio timed out: {e}")
        except RequestsHTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError(f"Authentication failed: {e}")
            else:
                raise ConnectionError(f"HTTP error {e.response.status_code}: {e}")
        except Exception as e:
            raise ConnectionError(f"Unexpected error: {e}")

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
        if not messages:
            raise ValueError("Messages list cannot be empty")

        # Prepare payload
        payload = {
            "model": model or self.config.model,
            "messages": [msg.to_dict() for msg in messages],
            "stream": stream,
        }

        # Add optional parameters
        for key in ["temperature", "max_tokens", "top_p", "repeat_penalty", "presence_penalty", "frequency_penalty"]:
            if key in kwargs:
                payload[key] = kwargs[key]
            elif key in self.config.extra_params:
                payload[key] = self.config.extra_params[key]

        # Make request
        if stream:
            return self._stream_completion(payload)
        else:
            return self._non_stream_completion(payload)

    def _non_stream_completion(self, payload: Dict[str, Any]) -> ChatResponse:
        """Handle non-streaming completion."""
        response = self._make_request('post', '/v1/chat/completions', json=payload)

        try:
            data = response.json()
        except ValueError as e:
            raise ConnectionError(f"Invalid JSON response: {e}")

        choices = data.get('choices', [])
        if not choices:
            raise ConnectionError("No choices in response")

        message = choices[0].get('message', {})
        content = message.get('content', '')

        # Handle OpenRouter-style thinking/reasoning
        thinking = message.get('reasoning') or message.get('thinking')

        return ChatResponse(
            content=content,
            model=data.get('model', payload.get('model', '')),
            usage=data.get('usage'),
            thinking=thinking,
            reasoning=thinking,
            finish_reason=choices[0].get('finish_reason'),
            raw_response=data
        )

    def _stream_completion(self, payload: Dict[str, Any]) -> Iterator[ChatResponse]:
        """Handle streaming completion."""
        try:
            response = self._make_request('post', '/v1/chat/completions', json=payload, stream=True)
        except Exception as e:
            raise ConnectionError(f"Failed to start stream: {e}")

        content_buffer = ""
        thinking_buffer = ""

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
                    import json
                    data = json.loads(data_str)
                    if not isinstance(data, dict):
                        continue

                    delta = data.get('choices', [{}])[0].get('delta', {})

                    # Accumulate content and thinking
                    if 'reasoning' in delta:
                        thinking_buffer += delta['reasoning']
                    if 'content' in delta:
                        content_buffer += delta['content']

                    yield ChatResponse(
                        content=delta.get('content', ''),
                        model=payload.get('model', ''),
                        thinking=delta.get('reasoning'),
                        reasoning=delta.get('reasoning'),
                        raw_response=data
                    )
                except (ValueError, SyntaxError, KeyError, IndexError):
                    continue

            # Final response with accumulated content
            yield ChatResponse(
                content="",  # Empty content for final yield, content already streamed
                model=payload.get('model', ''),
                thinking=thinking_buffer if thinking_buffer else None,
                reasoning=thinking_buffer if thinking_buffer else None,
                raw_response=None
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
            # Try the models endpoint as a health check
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
            Dictionary with configuration fields for frontend
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