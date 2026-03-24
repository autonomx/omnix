"""
OpenRouter Provider Plugin

Implements the BaseProvider interface for OpenRouter API.
OpenRouter provides access to various LLM models through a unified API.
"""

import requests
from typing import List, Optional, Dict, Any, Iterator, Union

from .base import BaseProvider, ChatMessage, ChatResponse, ModelInfo, ProviderConfig, ProviderCapability, AuthenticationError, ConnectionError, ModelNotFoundError


class OpenRouterProvider(BaseProvider):
    """
    Provider for OpenRouter API.
    
    OpenRouter offers a unified API for many different LLM models from various providers.
    Requires an API key for authentication.
    """
    
    provider_name = "openrouter"
    provider_display_name = "OpenRouter"
    provider_description = "OpenRouter API with access to multiple LLM providers"
    default_capabilities = [ProviderCapability.CHAT, ProviderCapability.STREAMING, ProviderCapability.MODELS]
    
    API_BASE_URL = "https://openrouter.ai/api/v1"
    MODELS_URL = "https://openrouter.ai/api/v1/models"
    
    def _validate_config(self):
        """Validate OpenRouter configuration."""
        if not self.config.base_url:
            self.config.base_url = self.API_BASE_URL
        if not self.config.api_key:
            raise AuthenticationError("OpenRouter requires an API key")
        # Ensure base_url doesn't have trailing slash
        self.config.base_url = self.config.base_url.rstrip('/')
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make an HTTP request to the OpenRouter API.
        
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
        
        # Add authorization header
        headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        # Add required OpenRouter headers if not present
        if "HTTP-Referer" not in headers:
            headers["HTTP-Referer"] = "http://localhost:5000"
        if "X-Title" not in headers:
            headers["X-Title"] = "Omnix"
        
        try:
            response = requests.request(method, url, headers=headers, timeout=self.config.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to OpenRouter at {url}: {e}")
        except requests.exceptions.Timeout as e:
            raise ConnectionError(f"Connection to OpenRouter timed out: {e}")
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
        Generate a chat completion using OpenRouter.
        
        Args:
            messages: List of chat messages
            model: Optional model override
            stream: Whether to stream the response
            **kwargs: Additional parameters (temperature, max_tokens, thinking_budget, etc.)
            
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
        
        # Handle thinking budget (OpenRouter's extra_options)
        thinking_budget = kwargs.get('thinking_budget', self.config.extra_params.get('thinking_budget', 0))
        if thinking_budget and thinking_budget > 0:
            payload["extra_options"] = {"max_tokens": thinking_budget}
        
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
            raise ConnectionError("No choices in OpenRouter response")
        
        message = choices[0].get('message', {})
        content = message.get('content', '')
        
        # OpenRouter uses 'reasoning' field for thinking
        thinking = message.get('reasoning')
        
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
                    import json
                    data = json.loads(data_str)
                    if not isinstance(data, dict):
                        continue
                        
                    delta = data.get('choices', [{}])[0].get('delta', {})
                    
                    yield ChatResponse(
                        content=delta.get('content', ''),
                        model=payload.get('model', ''),
                        thinking=delta.get('reasoning'),
                        reasoning=delta.get('reasoning'),
                        raw_response=data
                    )
                except (ValueError, KeyError, IndexError):
                    continue
                    
        except Exception as e:
            raise ConnectionError(f"Stream error: {e}")
    
    def get_models(self) -> List[ModelInfo]:
        """
        Get list of available models from OpenRouter.
        This can be filtered based on provider's available models.
        
        Returns:
            List of ModelInfo objects
            
        Raises:
            ConnectionError: If unable to fetch models
            AuthenticationError: If authentication fails
        """
        try:
            response = self._make_request('get', '/models')
            data = response.json()
            
            models = []
            for model_data in data.get('data', []):
                # OpenRouter returns model info with id, name, description, etc.
                model_info = ModelInfo(
                    id=model_data.get('id', ''),
                    name=model_data.get('name', model_data.get('id', '')),
                    provider=self.provider_name,
                    context_length=model_data.get('context_length'),
                    description=model_data.get('description', ''),
                    metadata={
                        'owned_by': model_data.get('owned_by', ''),
                        'top_provider': model_data.get('top_provider', False),
                        'pricing': model_data.get('pricing', {}),
                    }
                )
                models.append(model_info)
            
            return models
            
        except Exception as e:
            if isinstance(e, (AuthenticationError, ConnectionError)):
                raise
            raise ConnectionError(f"Failed to fetch models from OpenRouter: {e}")
    
    def test_connection(self) -> bool:
        """
        Test connection to OpenRouter.
        
        Returns:
            True if connection successful (API key valid), False otherwise
        """
        try:
            # Test with models endpoint
            response = self._make_request('get', '/models', timeout=5)
            return response.status_code == 200
        except AuthenticationError:
            raise  # Re-raise auth errors - API key is invalid
        except Exception:
            return False
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get configuration schema for OpenRouter provider.
        
        Returns:
            Dictionary with configuration fields for frontend
        """
        return {
            "provider_type": self.provider_name,
            "display_name": self.provider_display_name,
            "description": self.provider_description,
            "fields": [
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Key",
                    "required": True,
                    "description": "OpenRouter API key"
                },
                {
                    "name": "model",
                    "type": "select",
                    "label": "Model",
                    "required": True,
                    "description": "Select a model",
                    "options": []  # Will be populated dynamically from /models endpoint
                },
                {
                    "name": "thinking_budget",
                    "type": "number",
                    "label": "Thinking Budget (tokens)",
                    "default": 0,
                    "required": False,
                    "description": "Additional tokens for thinking/reasoning (0 to disable)"
                }
            ]
        }
    
    def supports_thinking_budget(self) -> bool:
        """
        OpenRouter supports thinking budget via extra_options.
        
        Returns:
            True
        """
        return True