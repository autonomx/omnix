"""
OpenAI-Compatible Provider Plugin

Implements the BaseProvider interface for OpenAI-compatible APIs.
This provider allows users to connect to any OpenAI-compatible API (Azure OpenAI, custom deployments, etc.)
by providing a URL, API key, model ID, and custom headers.
"""

import json
from typing import Any, Dict, Iterator, List, Optional, Union

import requests

from .base import (
    AuthenticationError,
    BaseProvider,
    ChatMessage,
    ChatResponse,
    ConnectionError,
    ModelInfo,
    ModelNotFoundError,
    ProviderCapability,
    ProviderConfig,
)


class OpenAICompatibleProvider(BaseProvider):
    """
    Provider for OpenAI-compatible APIs.
    
    This provider allows connection to any API that follows the OpenAI API specification,
    such as Azure OpenAI, custom deployments, or other compatible services.
    """
    
    provider_name = "openai_compatible"
    provider_display_name = "OpenAI Compatible"
    provider_description = "OpenAI-compatible API (Azure OpenAI, custom deployments, etc.)"
    default_capabilities = [ProviderCapability.CHAT, ProviderCapability.STREAMING, ProviderCapability.MODELS]
    
    def _validate_config(self):
        """Validate OpenAI-compatible configuration."""
        if not self.config.base_url:
            raise ValueError("OpenAI-compatible provider requires a base URL")
        if not self.config.api_key:
            raise AuthenticationError("OpenAI-compatible provider requires an API key")
        if not self.config.model:
            raise ValueError("OpenAI-compatible provider requires a model ID")
        
        # Ensure base_url doesn't have trailing slash
        self.config.base_url = self.config.base_url.rstrip('/')
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make an HTTP request to the OpenAI-compatible API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object
            
        Raises:
            AuthenticationError: If authentication fails
            ConnectionError: If connection fails
        """
        url = f"{self.config.base_url}{endpoint}"
        headers = kwargs.pop('headers', {})
        
        # Add authorization header (can be overridden by custom headers)
        if 'Authorization' not in headers:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        # Add content type
        headers["Content-Type"] = "application/json"
        
        # Add custom headers from extra_params
        custom_headers = self.config.extra_params.get('custom_headers', {})
        if isinstance(custom_headers, dict):
            headers.update(custom_headers)
        
        try:
            response = requests.request(method, url, headers=headers, timeout=self.config.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to {url}: {e}")
        except requests.exceptions.Timeout as e:
            raise ConnectionError(f"Connection to {url} timed out: {e}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [401, 403]:
                raise AuthenticationError(f"Authentication failed: {e}")
            elif e.response.status_code == 404:
                raise ModelNotFoundError(f"Resource not found: {e}")
            elif e.response.status_code == 429:
                from .exceptions import RateLimitError
                raise RateLimitError(f"Rate limit exceeded: {e}")
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
        Generate a chat completion using OpenAI-compatible API.
        
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
        
        # Build payload
        payload = {
            "model": model or self.config.model,
            "messages": [msg.to_dict() for msg in messages],
            "stream": stream,
        }
        
        # Add optional parameters
        optional_params = ["temperature", "top_p", "max_tokens", "top_k", "presence_penalty", "frequency_penalty"]
        for key in optional_params:
            if key in kwargs:
                payload[key] = kwargs[key]
            elif key in self.config.extra_params:
                payload[key] = self.config.extra_params[key]
        
        # Add any additional parameters from extra_params
        for key, value in self.config.extra_params.items():
            if key not in ['custom_headers', 'thinking_budget'] and key not in payload:
                payload[key] = value
        
        # Handle thinking budget if supported (some APIs might use different field names)
        thinking_budget = kwargs.get('thinking_budget', self.config.extra_params.get('thinking_budget', 0))
        if thinking_budget and thinking_budget > 0:
            # Try common field names for thinking/reasoning tokens
            if 'max_completion_tokens' in payload:
                payload['max_completion_tokens'] = thinking_budget
            elif 'max_tokens' in payload:
                payload['max_tokens'] = thinking_budget
            else:
                payload['max_tokens'] = thinking_budget
        
        # Make request
        if stream:
            return self._stream_completion(payload)
        else:
            return self._non_stream_completion(payload)
    
    def _non_stream_completion(self, payload: Dict[str, Any]) -> ChatResponse:
        """Handle non-streaming completion."""
        response = self._make_request('post', '/chat/completions', json=payload)
        
        try:
            data = response.json()
        except ValueError as e:
            raise ConnectionError(f"Invalid JSON response: {e}")
        
        choices = data.get('choices', [])
        if not choices:
            raise ConnectionError("No choices in response")
        
        message = choices[0].get('message', {})
        content = message.get('content', '')
        
        # Try to extract thinking/reasoning from various possible fields
        thinking = None
        if 'reasoning' in message:
            thinking = message['reasoning']
        elif 'thinking' in message:
            thinking = message['thinking']
        elif 'analysis' in message:
            thinking = message['analysis']
        elif 'thoughts' in message:
            thinking = message['thoughts']
        
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
            response = self._make_request('post', '/chat/completions', json=payload, stream=True)
        except Exception as e:
            raise ConnectionError(f"Failed to start stream: {e}")
        
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
                        
                    delta = data.get('choices', [{}])[0].get('delta', {})
                    
                    yield ChatResponse(
                        content=delta.get('content', ''),
                        model=payload.get('model', ''),
                        thinking=delta.get('reasoning') or delta.get('thinking') or delta.get('analysis'),
                        reasoning=delta.get('reasoning') or delta.get('thinking') or delta.get('analysis'),
                        raw_response=data
                    )
                except (ValueError, KeyError, IndexError):
                    continue
                    
        except Exception as e:
            raise ConnectionError(f"Stream error: {e}")
    
    def get_models(self) -> List[ModelInfo]:
        """
        Get list of available models from OpenAI-compatible API.
        This attempts to use the standard /models endpoint, but many compatible APIs
        might not implement this, so it returns a basic list with the configured model.
        
        Returns:
            List of ModelInfo objects
            
        Raises:
            ConnectionError: If unable to fetch models
            AuthenticationError: If authentication fails
        """
        models = []
        
        # First try the standard /models endpoint
        try:
            response = self._make_request('get', '/models')
            data = response.json()
            
            for model_data in data.get('data', []):
                model_info = ModelInfo(
                    id=model_data.get('id', ''),
                    name=model_data.get('name', model_data.get('id', '')),
                    provider=self.provider_name,
                    context_length=model_data.get('context_length'),
                    description=model_data.get('description', ''),
                    metadata=model_data.get('metadata', {})
                )
                models.append(model_info)
                
        except Exception as e:
            # If /models endpoint doesn't work, just add the configured model
            # This is common for many OpenAI-compatible APIs
            pass
        
        # Always include the configured model if it's not already in the list
        if self.config.model and not any(m.id == self.config.model for m in models):
            models.append(ModelInfo(
                id=self.config.model,
                name=self.config.model,
                provider=self.provider_name,
                description="Configured model",
                metadata={"configured": True}
            ))
        
        return models
    
    def test_connection(self) -> bool:
        """
        Test connection to OpenAI-compatible API.
        This tries to make a simple request to verify the connection and authentication.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to get models list first
            response = self._make_request('get', '/models', timeout=5)
            return response.status_code == 200
        except AuthenticationError:
            raise  # Re-raise auth errors - API key is invalid
        except Exception:
            # If /models doesn't work, try a simple chat completion with minimal payload
            try:
                payload = {
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 1
                }
                response = self._make_request('post', '/chat/completions', json=payload, timeout=5)
                return response.status_code == 200
            except Exception:
                return False
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get configuration schema for OpenAI-compatible provider.
        
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
                    "type": "text",
                    "label": "API Base URL",
                    "required": True,
                    "description": "Base URL for the OpenAI-compatible API (e.g., https://your-api.com/v1)"
                },
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Key",
                    "required": True,
                    "description": "API key for authentication"
                },
                {
                    "name": "model",
                    "type": "text",
                    "label": "Model ID",
                    "required": True,
                    "description": "Model identifier (e.g., gpt-4, gpt-3.5-turbo, your-custom-model)"
                },
                {
                    "name": "custom_headers",
                    "type": "object",
                    "label": "Custom Headers",
                    "required": False,
                    "description": "Additional headers to send with requests (key-value pairs)",
                    "properties": {
                        "key": {"type": "text", "label": "Header Name"},
                        "value": {"type": "text", "label": "Header Value"}
                    }
                },
                {
                    "name": "thinking_budget",
                    "type": "number",
                    "label": "Thinking Budget (tokens)",
                    "default": 0,
                    "required": False,
                    "description": "Additional tokens for thinking/reasoning (0 to disable)"
                },
                {
                    "name": "timeout",
                    "type": "number",
                    "label": "Timeout (seconds)",
                    "default": 300,
                    "required": False,
                    "description": "Request timeout in seconds"
                }
            ]
        }
    
    def supports_thinking_budget(self) -> bool:
        """
        OpenAI-compatible APIs typically support thinking budget via max_tokens.
        
        Returns:
            True
        """
        return True