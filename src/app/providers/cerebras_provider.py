"""
Cerebras Provider Plugin

Implements the BaseProvider interface for Cerebras API.
Cerebras provides access to their API hosted on their cloud platform.
"""

import requests
from typing import List, Optional, Dict, Any, Iterator, Union

from .base import BaseProvider, ChatMessage, ChatResponse, ModelInfo, ProviderConfig, ProviderCapability, AuthenticationError, ConnectionError, ModelNotFoundError


class CerebrasProvider(BaseProvider):
    """
    Provider for Cerebras API.
    
    Cerebras offers a cloud API for their LLM models.
    Requires an API key for authentication. Uses standard OpenAI-compatible endpoints.
    """
    
    provider_name = "cerebras"
    provider_display_name = "Cerebras"
    provider_description = "Cerebras Cloud API with access to their LLM models"
    default_capabilities = [ProviderCapability.CHAT, ProviderCapability.STREAMING, ProviderCapability.MODELS]
    
    API_BASE_URL = "https://api.cerebras.ai"
    CHAT_ENDPOINT = "/v1/chat/completions"
    MODELS_ENDPOINT = "/v1/models"
    
    def _validate_config(self):
        """Validate Cerebras configuration."""
        if not self.config.base_url:
            self.config.base_url = self.API_BASE_URL
        if not self.config.api_key:
            raise AuthenticationError("Cerebras requires an API key")
        # Ensure base_url doesn't have trailing slash
        self.config.base_url = self.config.base_url.rstrip('/')
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make an HTTP request to the Cerebras API.
        
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
        headers["Content-Type"] = "application/json"
        
        # Handle timeout parameter - use passed timeout or fallback to config timeout
        timeout = kwargs.pop('timeout', self.config.timeout)
        
        try:
            response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to Cerebras at {url}: {e}")
        except requests.exceptions.Timeout as e:
            raise ConnectionError(f"Connection to Cerebras timed out: {e}")
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
        Generate a chat completion using Cerebras.
        
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
        
        # Cerebras-specific: if 'stream' is True, uses server-sent events
        # Make request
        if stream:
            return self._stream_completion(payload)
        else:
            return self._non_stream_completion(payload)
    
    def _non_stream_completion(self, payload: Dict[str, Any]) -> ChatResponse:
        """Handle non-streaming completion."""
        response = self._make_request('post', self.CHAT_ENDPOINT, json=payload)
        
        try:
            data = response.json()
        except ValueError as e:
            raise ConnectionError(f"Invalid JSON response: {e}")
        
        choices = data.get('choices', [])
        if not choices:
            raise ConnectionError("No choices in Cerebras response")
        
        message = choices[0].get('message', {})
        content = message.get('content', '')
        
        # Cerebras may use 'reasoning' field for thinking (similar to OpenRouter)
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
            response = self._make_request('post', self.CHAT_ENDPOINT, json=payload, stream=True)
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
                        thinking=delta.get('reasoning') or delta.get('thinking'),
                        reasoning=delta.get('reasoning') or delta.get('thinking'),
                        raw_response=data
                    )
                except (ValueError, KeyError, IndexError):
                    continue
                    
        except Exception as e:
            raise ConnectionError(f"Stream error: {e}")
    
    def get_models(self) -> List[ModelInfo]:
        """
        Get list of available models from Cerebras.
        
        Returns:
            List of ModelInfo objects
            
        Raises:
            ConnectionError: If unable to fetch models
            AuthenticationError: If authentication fails
        """
        try:
            response = self._make_request('get', self.MODELS_ENDPOINT)
            data = response.json()
            
            models = []
            for model_data in data.get('data', []):
                model_info = ModelInfo(
                    id=model_data.get('id', ''),
                    name=model_data.get('name', model_data.get('id', '')),
                    provider=self.provider_name,
                    context_length=model_data.get('context_length'),
                    description=model_data.get('description', ''),
                    metadata={
                        'owned_by': model_data.get('owned_by', ''),
                    }
                )
                models.append(model_info)
            
            return models
            
        except Exception as e:
            if isinstance(e, (AuthenticationError, ConnectionError)):
                raise
            raise ConnectionError(f"Failed to fetch models from Cerebras: {e}")
    
    def test_connection(self) -> bool:
        """
        Test connection to Cerebras.
        
        Returns:
            True if connection successful (API key valid), False otherwise
        """
        try:
            # First try the models endpoint (simplest test)
            response = self._make_request('get', self.MODELS_ENDPOINT, timeout=5)
            if response.status_code == 200:
                return True
                
        except AuthenticationError:
            raise  # Re-raise auth errors - API key is invalid
        except Exception:
            pass
        
        try:
            # Fallback: try a minimal chat completion request
            # Use a very simple request that should work with any model
            test_payload = {
                "model": self.config.model or "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 1,
                "temperature": 0.0
            }
            
            response = self._make_request('post', self.CHAT_ENDPOINT, json=test_payload, timeout=10)
            return response.status_code == 200
            
        except AuthenticationError:
            raise  # Re-raise auth errors - API key is invalid
        except Exception:
            return False
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get configuration schema for Cerebras provider.
        
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
                    "description": "Cerebras API key"
                },
                {
                    "name": "model",
                    "type": "select",
                    "label": "Model",
                    "required": True,
                    "description": "Select a model",
                    "options": []  # Will be populated dynamically from /models endpoint
                }
            ]
        }