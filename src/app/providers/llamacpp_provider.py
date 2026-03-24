"""
Llama.cpp Provider Plugin

Implements the BaseProvider interface for local Llama.cpp servers.
This provider manages the llama.cpp binary and model serving.
"""

import os
import time
import subprocess
import threading
import requests
from typing import List, Optional, Dict, Any, Iterator, Union
from pathlib import Path

from .base import BaseProvider, ChatMessage, ChatResponse, ModelInfo, ProviderConfig, ProviderCapability, AuthenticationError, ConnectionError, ModelNotFoundError

# Import the installer
from app.llamacpp_installer import get_installer


class LlamaCppProvider(BaseProvider):
    """
    Provider for local Llama.cpp server.
    
    Manages the llama.cpp binary, server lifecycle, and model serving.
    Can download and manage models locally.
    """
    
    provider_name = "llamacpp"
    provider_display_name = "Llama.cpp"
    provider_description = "Local Llama.cpp server with binary management"
    default_capabilities = [ProviderCapability.CHAT, ProviderCapability.STREAMING, ProviderCapability.MODELS]
    
    # Known server binary names
    SERVER_BINARY_NAMES = ["llama-server.exe", "llama-server", "llama.exe", "llama"]
    
    def _validate_config(self):
        """Validate Llama.cpp configuration."""
        if not self.config.base_url:
            self.config.base_url = "http://localhost:8080"
        # Ensure base_url doesn't have trailing slash
        self.config.base_url = self.config.base_url.rstrip('/')
        
        # Set default model_dir if not specified
        if not self.config.extra_params.get('model_dir'):
            base_dir = Path(__file__).parent.parent.parent
            download_location = self.config.extra_params.get('download_location', 'server')
            self.config.extra_params['model_dir'] = str(base_dir / 'resources' / 'models' / download_location)
    
    def _find_server_binary(self) -> Optional[Path]:
        """
        Find the llama.cpp server binary.
        
        Returns:
            Path to binary or None if not found
        """
        model_dir = Path(self.config.extra_params.get('model_dir', ''))
        server_dir = model_dir if model_dir.name == 'server' else model_dir.parent / 'server'
        
        for binary_name in self.SERVER_BINARY_NAMES:
            binary_path = server_dir / binary_name
            if binary_path.exists():
                return binary_path
        
        return None
    
    def _is_server_running(self) -> bool:
        """
        Check if the llama.cpp server is running.
        
        Returns:
            True if server responds to health check, False otherwise
        """
        try:
            response = requests.get(f"{self.config.base_url}/v1/models", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def _start_server(self, model_path: str) -> Optional[int]:
        """
        Start the llama.cpp server with a model.
        
        Args:
            model_path: Path to the model file
            
        Returns:
            Process ID if started successfully, None otherwise
        """
        binary = self._find_server_binary()
        if not binary:
            raise ConnectionError("Llama.cpp server binary not found")
        
        # Extract port from base_url
        try:
            port = int(self.config.base_url.split(':')[-1])
        except:
            port = 8080  # Default port
        
        # Check if already running on port
        try:
            # Try to kill existing process on the port (platform-specific)
            import platform
            if platform.system() == "Windows":
                # Windows: Use netstat and taskkill without awk
                try:
                    # Get process ID using netstat
                    result = subprocess.run(f'netstat -ano | findstr :{port}', shell=True, capture_output=True, text=True)
                    if result.stdout:
                        # Extract PID from the output (last column)
                        lines = result.stdout.strip().split('\n')
                        for line in lines:
                            parts = line.split()
                            if len(parts) >= 5 and 'LISTENING' in line:
                                pid = parts[-1]
                                # Kill the process
                                subprocess.run(f'taskkill /F /PID {pid} 2>nul', shell=True)
                except:
                    pass
            else:
                subprocess.run(f"lsof -ti:{port} | xargs kill -9 2>/dev/null", shell=True)
            time.sleep(1)
        except:
            pass
        
        try:
            # Start the server with absolute paths to avoid Windows path issues
            # Using -ngl 99 for maximum GPU utilization on modern GPUs
            proc = subprocess.Popen(
                [str(binary), "-m", str(model_path.resolve()), "-c", "4096", "-ngl", "99", "--host", "0.0.0.0", "--port", str(port)],
                cwd=binary.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1
            )
            return proc.pid
        except Exception as e:
            raise ConnectionError(f"Failed to start server: {e}")
    
    def _stop_server(self) -> bool:
        """
        Stop the running llama.cpp server.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            port = int(self.config.base_url.split(':')[-1])
            import platform
            if platform.system() == "Windows":
                subprocess.run(f'netstat -ano | findstr :{port} | findstr LISTENING | awk \'{{print $5}}\' | xargs taskkill /F /PID 2>nul', shell=True)
            else:
                subprocess.run(f"lsof -ti:{port} | xargs kill -9 2>/dev/null", shell=True)
            return True
        except:
            return False
    
    def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[ChatResponse, Iterator[ChatResponse]]:
        """
        Generate a chat completion using Llama.cpp.
        
        Args:
            messages: List of chat messages
            model: Optional model override
            stream: Whether to stream the response
            **kwargs: Additional parameters
            
        Returns:
            ChatResponse or iterator of ChatResponse chunks
            
        Raises:
            ConnectionError: If server not running or fails to start
            ModelNotFoundError: If model doesn't exist
            AuthenticationError: Not applicable for local server
        """
        if not messages:
            raise ValueError("Messages list cannot be empty")
        
        # Resolve model path
        model_name = model or self.config.model
        if not model_name:
            raise ModelNotFoundError("No model specified")
        
        model_dir = Path(self.config.extra_params.get('model_dir', ''))
        
        # Check possible locations for the model
        possible_paths = []
        
        # If model_name is an absolute path, use it directly
        if os.path.isabs(model_name):
            possible_paths.append(Path(model_name))
        else:
            # Search in the model directory for files matching the name
            # This handles cases where the model might be in subdirectories
            for file_path in model_dir.rglob("*.gguf"):
                if file_path.name == model_name:
                    possible_paths.append(file_path)
                    break
            # Also check direct match in model_dir
            direct_path = model_dir / model_name
            if direct_path.exists():
                possible_paths.append(direct_path)
        
        model_path = None
        for path in possible_paths:
            if path and path.exists():
                model_path = path
                break
        
        if not model_path:
            raise ModelNotFoundError(f"Model not found: {model_name}")
        
        # Ensure server is running
        if not self._is_server_running():
            pid = self._start_server(str(model_path))
            if not pid:
                raise ConnectionError("Failed to start llama.cpp server")
            # Wait for server to be ready
            time.sleep(2)
            if not self._is_server_running():
                raise ConnectionError("Server started but not responding")
        
        # Build payload
        payload = {
            "model": model_name,
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
        try:
            response = requests.post(f"{self.config.base_url}/v1/chat/completions", json=payload, timeout=self.config.timeout)
            response.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to llama.cpp server: {e}")
        except requests.exceptions.Timeout as e:
            raise ConnectionError(f"Request to llama.cpp timed out: {e}")
        except requests.exceptions.HTTPError as e:
            raise ConnectionError(f"HTTP error: {e}")
        
        try:
            data = response.json()
        except ValueError as e:
            raise ConnectionError(f"Invalid JSON response: {e}")
        
        choices = data.get('choices', [])
        if not choices:
            raise ConnectionError("No choices in response")
        
        message = choices[0].get('message', {})
        content = message.get('content', '')
        
        return ChatResponse(
            content=content,
            model=data.get('model', payload.get('model', '')),
            usage=data.get('usage'),
            finish_reason=choices[0].get('finish_reason'),
            raw_response=data
        )
    
    def _stream_completion(self, payload: Dict[str, Any]) -> Iterator[ChatResponse]:
        """Handle streaming completion."""
        try:
            response = requests.post(f"{self.config.base_url}/v1/chat/completions", json=payload, timeout=self.config.timeout, stream=True)
            response.raise_for_status()
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
                        raw_response=data
                    )
                except (ValueError, KeyError, IndexError):
                    continue
                    
        except Exception as e:
            raise ConnectionError(f"Stream error: {e}")
    
    def get_models(self) -> List[ModelInfo]:
        """
        Get list of available models from local filesystem.
        
        Returns:
            List of ModelInfo objects
            
        Raises:
            ConnectionError: If unable to access model directory
        """
        try:
            model_dir = Path(self.config.extra_params.get('model_dir', ''))
            if not model_dir.exists():
                return []
            
            # Search for .gguf files in model directory
            models = []
            gguf_files = list(model_dir.rglob("*.gguf"))
            
            for gguf_file in gguf_files[:100]:  # Limit to 100 models
                # Try to get file size for metadata
                try:
                    size = gguf_file.stat().st_size
                except:
                    size = 0
                
                model_info = ModelInfo(
                    id=gguf_file.name,  # Use just the filename as ID
                    name=gguf_file.name,
                    provider=self.provider_name,
                    context_length=None,  # Unknown without loading the model
                    description=f"Local GGUF model",
                    metadata={
                        'path': str(gguf_file),
                        'size': size,
                        'size_formatted': self._format_size(size)
                    }
                )
                models.append(model_info)
            
            return models
            
        except Exception as e:
            raise ConnectionError(f"Failed to list models: {e}")
    
    def test_connection(self) -> bool:
        """
        Test connection to llama.cpp server.
        
        Returns:
            True if server is running and responding, False otherwise
        """
        try:
            return self._is_server_running()
        except:
            return False
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get configuration schema for Llama.cpp provider.
        
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
                    "label": "Server URL",
                    "default": "http://localhost:8080",
                    "required": True,
                    "description": "URL of the llama.cpp server"
                },
                {
                    "name": "model",
                    "type": "select",
                    "label": "Model",
                    "required": False,
                    "description": "Select a model (auto-discovered from models directory)"
                },
                {
                    "name": "download_location",
                    "type": "select",
                    "label": "Models Location",
                    "default": "server",
                    "required": False,
                    "description": "Where to store downloaded models",
                    "options": [
                        {"value": "server", "label": "models/server (recommended)"},
                        {"value": "llm", "label": "models/llm"}
                    ]
                },
                {
                    "name": "auto_start",
                    "type": "boolean",
                    "label": "Auto-start Server",
                    "default": False,
                    "required": False,
                    "description": "Automatically start server when provider is selected"
                }
            ]
        }
    
    def _format_size(self, bytes_size: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"
    
    def get_capabilities(self) -> List[ProviderCapability]:
        """
        Get list of capabilities supported by this provider.
        
        Returns:
            List of ProviderCapability enums
        """
        return self.default_capabilities.copy()
    
    def requires_api_key(self) -> bool:
        """Llama.cpp doesn't require an API key."""
        return False