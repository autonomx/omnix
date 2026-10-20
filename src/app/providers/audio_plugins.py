"""
Audio Provider Plugin Implementations

This module contains concrete implementations of audio providers:
- ParakeetSTT: Wraps FasterWhisper/Parakeet STT service
"""

import json
import logging
import os
from app.config.env import environment_copy
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


from app.runtime.http_client import PooledHttpClient, shared_http_client
from app.security.service_token import service_headers
from app.runtime.config import get_runtime_config

from .audio_base import (
    AudioProviderCapability,
    BaseSTTProvider,
)

logger = logging.getLogger(__name__)

DEFAULT_PARAKEET_BASE_URL = "http://127.0.0.1:5201"
LEGACY_PARAKEET_BASE_URLS = {"http://localhost:8000", "http://127.0.0.1:8000"}


def _stt_http() -> PooledHttpClient:
    """The pooled client for the speech-to-text service (WP-7.2)."""
    return shared_http_client("stt-service")


def _parakeet_base_url(config: Dict[str, Any]) -> str:
    """Resolve the dedicated STT service, migrating the retired gateway URL."""
    configured = str(config.get("base_url") or "").strip().rstrip("/")
    endpoint = get_runtime_config().stt
    if endpoint is not None:
        return endpoint.url.removesuffix("/transcribe")
    if configured.endswith("/transcribe"):
        configured = configured.removesuffix("/transcribe")
    if configured and configured not in {
        *LEGACY_PARAKEET_BASE_URLS, DEFAULT_PARAKEET_BASE_URL, "http://localhost:5201",
    }:
        # Mutable provider settings cannot select an audience for the service secret.
        # A remote/custom sidecar must be configured by the serving process owner.
        raise RuntimeError("stt_service_endpoint_not_configured")
    return DEFAULT_PARAKEET_BASE_URL


class ParakeetSTT(BaseSTTProvider):
    """Parakeet STT Provider - wraps FasterWhisper/Parakeet STT service."""
    
    @property
    def provider_name(self) -> str:
        """Return the unique name of this provider."""
        return "parakeet"
    
    def start(self) -> Dict[str, Any]:
        if self.process and self.process.poll() is None:
            return {"running": True, "message": "Service already running"}
        
        try:
            source_root = Path(__file__).resolve().parents[2]
            script_path = source_root / "services" / "stt" / "parakeet_stt_server.py"
            if not script_path.exists():
                return {"running": False, "message": f"Server script not found: {script_path}"}
            
            self.process = subprocess.Popen(
                ['python', '-m', 'services.stt.parakeet_stt_server'],
                cwd=str(source_root),
                env={**environment_copy(), "PYTHONPATH": str(source_root)},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            self._start_log_thread()
            
            max_wait = 30
            for _ in range(max_wait):
                if self.health_check():
                    return {"running": True, "message": "Parakeet STT started successfully"}
                time.sleep(1)
            
            self.stop()
            return {"running": False, "message": "Service failed to start within timeout"}
            
        except Exception as e:
            return {"running": False, "message": f"Failed to start: {str(e)}"}
    
    def test_connection(self) -> bool:
        """Test connection to the Parakeet STT service."""
        return self.health_check()
    
    def health_check(self) -> bool:
        try:
            base_url = _parakeet_base_url(self.config)
            response = _stt_http().get(f"{base_url}/health", timeout=5, retry=False)
            return response.status_code == 200
        except Exception:
            return False
            
    def _parse_response(self, response) -> Dict[str, Any]:
        """Helper to robustly parse the server response"""
        logger.debug(f"[PARAKEET-PLUGIN] Server Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            # The response carries the transcript: log its shape only (content-free logs).
            logger.debug("[PARAKEET-PLUGIN] Server response keys: %s", sorted(data) if isinstance(data, dict) else type(data).__name__)
            
            # Be highly permissive of response structure (OpenAI format or Custom)
            text = data.get("text", "")
            segments = data.get("segments", [])
            
            if not text and segments:
                text = ' '.join([s.get('text', '') for s in segments])
                
            # If we got text, it's a success regardless of a 'success' boolean
            if text.strip() or data.get("success"):
                return {
                    "success": True,
                    "text": text.strip(),
                    "segments": segments,
                    "duration": data.get("duration")
                }
            else:
                logger.debug("[PARAKEET-PLUGIN] Silence detected or empty text returned.")
                return {
                    "success": False,
                    "text": "",
                    "segments": [],
                    "duration": 0,
                    "error": "No speech detected in audio"
                }
                
        # Handle failures
        try:
            error_body = response.json()
            logger.warning(f"[PARAKEET-PLUGIN] Server Error JSON: {error_body}")
            error_msg = error_body.get('error', error_body.get('message', response.text))
        except Exception:
            error_msg = f"Status {response.status_code}: {response.text}"
            
        logger.warning(f"[PARAKEET-PLUGIN] Transcription failed: {error_msg}")
        return {"success": False, "error": error_msg}

    def transcribe(self, audio_file_path: str, language: Optional[str] = None, 
                  **kwargs) -> Dict[str, Any]:
        try:
            base_url = _parakeet_base_url(self.config)
            
            with open(audio_file_path, 'rb') as audio_file:
                files = {'file': (os.path.basename(audio_file_path), audio_file, 'audio/wav')}
                data = {}
                if language:
                    data['language'] = language
                data.update(kwargs)
                
                response = _stt_http().post(f"{base_url}/transcribe", files=files, data=data, timeout=120,
                                            headers=service_headers())
            
            return self._parse_response(response)
            
        except Exception as e:
            logger.warning(f"[PARAKEET-PLUGIN] Exception: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def transcribe_timed(self, audio_file_path: str, *, language: str = "", diarize: bool = True,
                         speakers: int = 0) -> dict[str, Any]:
        """A timed, speaker-labelled ``TranscriptDocument`` from the service's batch engine.

        Returns ``{"success": True, "document": ...}`` or
        ``{"success": False, "code": ..., "error": ...}``; ``model_unavailable``
        means Parakeet-TDT or TitaNet is not installed or does not fit in VRAM.
        """
        base_url = _parakeet_base_url(self.config)
        with open(audio_file_path, "rb") as audio_file:
            response = _stt_http().post(
                f"{base_url}/transcribe/timed",
                files={"file": (os.path.basename(audio_file_path), audio_file, "application/octet-stream")},
                data={"language": language, "diarize": "true" if diarize else "false", "speakers": str(int(speakers))},
                timeout=1800,
                headers=service_headers(),
            )
        # Outcomes to act on arrive as 200 envelopes ({"ok": false, "code", "message"}): the
        # service's middleware replaces error bodies with a bare {"error": <code>}.
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") is False:
                return {"success": False, "code": str(data.get("code") or "model_service_error"),
                        "error": str(data.get("message") or "Timed transcription failed")}
            return {"success": True, "document": data}
        if response.status_code == 404:
            return {"success": False, "code": "unsupported",
                    "error": "The STT service has no timed transcription; update and restart it"}
        try:
            code = str(response.json().get("error") or "model_service_error")
        except ValueError:
            code = "model_service_error"
        return {"success": False, "code": code, "error": f"The STT service refused the request ({code})"}

    def warm_timed(self) -> dict[str, Any]:
        """Ask the service to load its batch engine now (push-to-talk opened); ``{"ready", "detail"}``."""
        try:
            response = _stt_http().post(f"{_parakeet_base_url(self.config)}/transcribe/timed/warm", timeout=300,
                                        headers=service_headers())
        except Exception as exc:
            logger.info("[PARAKEET-PLUGIN] Warm-up failed: %s", exc)
            return {"ready": False, "detail": "The speech-to-text service is not reachable"}
        if response.status_code == 404:
            return {"ready": False, "detail": "The STT service has no batch engine warm-up; update and restart it"}
        if response.status_code != 200:
            return {"ready": False, "detail": f"The STT service refused the warm-up ({response.status_code})"}
        data = response.json()
        if data.get("ok") is False:
            return {"ready": False, "detail": str(data.get("message") or "The batch engine could not load")}
        return {"ready": True, "detail": ""}

    def transcribe_raw(self, audio_data: bytes, sample_rate: int = 16000,
                      language: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        try:
            base_url = _parakeet_base_url(self.config)
            
            import tempfile
            import wave

            import numpy as np
            
            # Convert raw Float32 audio to proper WAV file
            float32_data = np.frombuffer(audio_data, dtype=np.float32)
            int16_data = (float32_data * 32767).astype(np.int16)
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
                with wave.open(temp_audio.name, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(int16_data.tobytes())
                temp_audio_path = temp_audio.name
                
            try:
                with open(temp_audio_path, 'rb') as f:
                    files = {'file': ('audio.wav', f, 'audio/wav')}
                    data = {}
                    if language:
                        data['language'] = language
                    data.update(kwargs)
                    
                    logger.debug(f"[PARAKEET-PLUGIN] Sending audio to {base_url}/transcribe. Size: {len(audio_data)} bytes, {len(int16_data)} samples, {sample_rate}Hz")
                    response = _stt_http().post(f"{base_url}/transcribe", files=files, data=data, timeout=120,
                                                headers=service_headers())
                    
                return self._parse_response(response)
            finally:
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
        
        except Exception as e:
            logger.warning(f"[PARAKEET-PLUGIN] Raw exception: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def transcribe_stream(self, audio_chunks: Iterator[bytes]) -> Iterator[Dict[str, Any]]:
        """
        Stream STT transcription partials using WebSocket or chunked HTTP.
        
        Args:
            audio_chunks: Iterator of audio chunks (bytes)
            
        Yields:
            Dict with 'partial' or 'final' keys containing text
        """
        try:
            base_url = _parakeet_base_url(self.config)
            
            # Try WebSocket first for real-time streaming
            try:
                import websocket
                ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
                ws_url += "/ws/transcribe"
                
                ws = websocket.create_connection(ws_url, timeout=10, header=service_headers(), redirect_limit=0)
                
                # Send audio chunks
                for chunk in audio_chunks:
                    ws.send_binary(chunk)
                    # Receive partial results
                    try:
                        result = ws.recv()
                        if result:
                            yield json.loads(result)
                    except websocket.WebSocketTimeoutException:
                        # No partial result yet, continue
                        continue
                
                # Signal end of stream
                ws.send("EOF")
                
                # Receive final result
                try:
                    final_result = ws.recv()
                    if final_result:
                        yield json.loads(final_result)
                except websocket.WebSocketTimeoutException:
                    pass
                
                ws.close()
                
            except (ImportError, Exception) as ws_error:
                logger.warning(f"[PARAKEET-PLUGIN] WebSocket failed ({ws_error}), falling back to HTTP streaming")
                
                # Fallback to HTTP streaming
                # This is a simplified implementation - in practice, you'd want to use
                # a proper streaming HTTP client or implement chunked uploads
                for chunk in audio_chunks:
                    # For now, just transcribe each chunk individually
                    # This provides a basic streaming experience
                    result = self.transcribe_raw(chunk, sample_rate=16000)
                    if result.get('success') and result.get('text'):
                        yield {"partial": result['text']}
                
                # Return final result
                yield {"final": ""}
                
        except Exception as e:
            logger.warning(f"[PARAKEET-PLUGIN] Streaming STT error: {e}")
            yield {"error": str(e)}
    
    def get_capabilities(self) -> List[AudioProviderCapability]:
        return [
            AudioProviderCapability.STREAMING,
            AudioProviderCapability.BATCH_PROCESSING,
            AudioProviderCapability.MULTILINGUAL
        ]
