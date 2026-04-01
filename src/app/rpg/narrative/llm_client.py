"""LLM Client — LLM Integration for Narrative Generation.

This module provides a concrete LLM client wrapper that can be used
with the NarrativeGenerator for rich narrative generation.

Purpose:
    Replace mock LLM with actual LLM service (OpenAI API or compatible)
    for rich, context-aware narrative generation.

Usage:
    client = LLMClient(api_key="...", model="gpt-4o-mini")
    generator = NarrativeGenerator(llm=client.generate)
    narration = generator.generate(events, context)

Supported Backends:
    - OpenAI API (openai package)
    - Compatible APIs (any OpenAI-compatible endpoint)
    - Local servers (llama.cpp, vLLM, Ollama) via base_url config
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG: Dict[str, Any] = {
    "model": "gpt-4o-mini",
    "temperature": 0.8,
    "max_tokens": 500,
    "top_p": 1.0,
    "timeout": 30,
}


class LLMClient:
    """LLM client for narrative generation.
    
    Wraps an LLM service (OpenAI API or compatible) into a simple
    callable interface that NarrativeGenerator can use.
    
    Supported backends:
    - OpenAI API (default)
    - Any OpenAI-compatible API (via base_url)
    - Local servers (llama.cpp, vLLM, Ollama)
    
    Attributes:
        api_key: API key for authentication. Can be None for local servers.
        base_url: Custom API endpoint URL.
        model: Model name/ID to use for generation.
        temperature: Creativity temperature (0.0-2.0).
        max_tokens: Maximum tokens for response.
        client: Underlying API client instance.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.8,
        max_tokens: int = 500,
        timeout: int = 30,
        **kwargs: Any,
    ):
        """Initialize the LLM client.
        
        Args:
            api_key: API key. If None, tries OPENAI_API_KEY env var.
            base_url: Custom API endpoint. If None, uses OpenAI default.
            model: Model name to use.
            temperature: Creativity temperature (0.0-2.0).
            max_tokens: Maximum tokens for response.
            timeout: Request timeout in seconds.
            **kwargs: Additional client configuration.
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.extra_kwargs = kwargs
        
        # Initialize the OpenAI client (lazy)
        self._client = None
        self._api_key = api_key
        self._base_url = base_url
    
    def _get_client(self):
        """Get or create the OpenAI client instance.
        
        Returns:
            OpenAI client instance.
        """
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "openai package is required for LLMClient. "
                    "Install with: pip install openai"
                )
            
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self.timeout,
            )
        return self._client
    
    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from a prompt using the LLM.
        
        This is the main generation method, compatible with NarrativeGenerator's
        expected callable signature: `llm(prompt: str) -> str`.
        
        Args:
            prompt: The prompt to generate from.
            **kwargs: Override generation parameters for this request.
        
        Returns:
            Generated text string.
        
        Raises:
            RuntimeError: If the LLM request fails.
        """
        try:
            client = self._get_client()
            
            # Merge parameters
            temperature = kwargs.pop("temperature", self.temperature)
            max_tokens = kwargs.pop("max_tokens", self.max_tokens)
            model = kwargs.pop("model", self.model)
            
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                **{**self.extra_kwargs, **kwargs},
            )
            
            # Extract text from response
            if response.choices and response.choices[0].message:
                text = response.choices[0].message.content
                if text:
                    return text.strip()
            
            logger.warning("LLM returned empty response")
            return ""
            
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise RuntimeError(f"LLM generation error: {e}")
    
    def generate_json(
        self,
        prompt: str,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate structured JSON output from a prompt.
        
        Useful for intent classification, structured output, etc.
        
        Args:
            prompt: The prompt to generate from.
            response_format: Optional JSON schema for response structure.
        
        Returns:
            Parsed JSON dict from the response.
        """
        try:
            client = self._get_client()
            
            messages = [
                {
                    "role": "system",
                    "content": "Respond ONLY with valid JSON. Do not include any other text."
                },
                {"role": "user", "content": prompt},
            ]
            
            call_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.1,  # Low temperature for JSON
                "timeout": self.timeout,
            }
            
            if response_format:
                call_kwargs["response_format"] = response_format
            
            response = client.chat.completions.create(**call_kwargs)
            
            if response.choices and response.choices[0].message:
                text = response.choices[0].message.content
                if text:
                    # Clean up markdown code blocks
                    if text.startswith("```"):
                        text = text.split("```")[1]
                        if text.startswith("json"):
                            text = text[4:]
                        text = text.strip()
                    return json.loads(text)
            
            return {}
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON: {e}")
            return {}
        except Exception as e:
            logger.error(f"LLM JSON request failed: {e}")
            raise RuntimeError(f"LLM JSON generation error: {e}")
    
    def generate_batch(self, prompts: List[str], **kwargs: Any) -> List[str]:
        """Generate text for multiple prompts in batch.
        
        Args:
            prompts: List of prompts to generate from.
            **kwargs: Generation parameters.
        
        Returns:
            List of generated texts.
        """
        results = []
        for prompt in prompts:
            results.append(self.generate(prompt, **kwargs))
        return results
    
    def get_available_models(self) -> List[str]:
        """Get list of available models from the API.
        
        Returns:
            List of model name strings.
        """
        try:
            client = self._get_client()
            models = client.models.list()
            return [m.id for m in models.data]
        except Exception:
            return [self.model]
    
    def close(self) -> None:
        """Close the client and release resources."""
        if self._client is not None and hasattr(self._client, "close"):
            self._client.close()
            self._client = None
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close()
    
    def __call__(self, prompt: str, **kwargs: Any) -> str:
        """Make the client callable directly: client(prompt).
        
        Args:
            prompt: The prompt string.
            **kwargs: Override parameters.
        
        Returns:
            Generated text.
        """
        return self.generate(prompt, **kwargs)