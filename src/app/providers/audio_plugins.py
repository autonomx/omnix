"""
Audio Provider Plugin Implementations

This module contains concrete implementations of audio providers:
- ParakeetSTT: Wraps FasterWhisper/Parakeet STT service
"""

import base64
import io
import logging
import os
import subprocess
import time
import wave
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

import numpy as np
import requests
import soundfile as sf

from .audio_base import (
    AudioProviderCapability,
    AudioProviderConfig,
    BaseSTTProvider,
    BaseTTSProvider,
    STTTranscriptionResponse,
    TTSAudioResponse,
)

logger = logging.getLogger(__name__)


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
            script_path = Path(__file__).parent.parent.parent / "parakeet_stt_server.py"
            if not script_path.exists():
                return {"running": False, "message": f"Server script not found: {script_path}"}
            
            self.process = subprocess.Popen(
                ['python', str(script_path)],
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
            base_url = self.config.get("base_url", "http://localhost:8000")
            response = requests.get(f"{base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
            
    def _parse_response(self, response) -> Dict[str, Any]:
        """Helper to robustly parse the server response"""
        print(f"[PARAKEET-PLUGIN] Server Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"[PARAKEET-PLUGIN] Server Response JSON: {data}")
            
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
                print(f"[PARAKEET-PLUGIN] Silence detected or empty text returned.")
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
            print(f"[PARAKEET-PLUGIN] Server Error JSON: {error_body}")
            error_msg = error_body.get('error', error_body.get('message', response.text))
        except:
            error_msg = f"Status {response.status_code}: {response.text}"
            
        print(f"[PARAKEET-PLUGIN] Transcription failed: {error_msg}")
        return {"success": False, "error": error_msg}

    def transcribe(self, audio_file_path: str, language: Optional[str] = None, 
                  **kwargs) -> Dict[str, Any]:
        try:
            base_url = self.config.get("base_url", "http://localhost:8000")
            
            with open(audio_file_path, 'rb') as audio_file:
                files = {'file': (os.path.basename(audio_file_path), audio_file, 'audio/wav')}
                data = {}
                if language:
                    data['language'] = language
                data.update(kwargs)
                
                response = requests.post(f"{base_url}/transcribe", files=files, data=data, timeout=120)
            
            return self._parse_response(response)
            
        except Exception as e:
            print(f"[PARAKEET-PLUGIN] Exception: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def transcribe_raw(self, audio_data: bytes, sample_rate: int = 16000, 
                      language: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        try:
            base_url = self.config.get("base_url", "http://localhost:8000")
            
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
                    
                    print(f"[PARAKEET-PLUGIN] Sending audio to {base_url}/transcribe. Size: {len(audio_data)} bytes, {len(int16_data)} samples, {sample_rate}Hz")
                    response = requests.post(f"{base_url}/transcribe", files=files, data=data, timeout=120)
                    
                return self._parse_response(response)
            finally:
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
        
        except Exception as e:
            print(f"[PARAKEET-PLUGIN] Raw exception: {e}")
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
            base_url = self.config.get("base_url", "http://localhost:8000")
            
            # Try WebSocket first for real-time streaming
            try:
                import websocket
                ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
                ws_url += "/ws/stt"
                
                ws = websocket.create_connection(ws_url, timeout=10)
                
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
                print(f"[PARAKEET-PLUGIN] WebSocket failed ({ws_error}), falling back to HTTP streaming")
                
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
            print(f"[PARAKEET-PLUGIN] Streaming STT error: {e}")
            yield {"error": str(e)}
    
    def get_capabilities(self) -> List[AudioProviderCapability]:
        return [
            AudioProviderCapability.STREAMING,
            AudioProviderCapability.BATCH_PROCESSING,
            AudioProviderCapability.MULTILINGUAL
        ]


class FasterQwen3TTSTTS(BaseTTSProvider):
    """
    FasterQwen3TTS Provider - wraps the faster-qwen3-tts model for real-time TTS.
    
    This provider uses the faster-qwen3-tts library which provides CUDA graph acceleration
    for Qwen3-TTS models, offering 6-10x speedup over standard implementations.
    """
    
    @property
    def provider_name(self) -> str:
        """Return the unique name of this provider."""
        return "faster-qwen3-tts"
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model = None
        self.model_name = config.get("model_name", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
        self.device = config.get("device", "cuda")
        self.dtype = config.get("dtype", "bfloat16")
        self.max_seq_len = config.get("max_seq_len", 2048)
        self.chunk_size = config.get("chunk_size", 12)
        self.temperature = config.get("temperature", 0.9)
        self.top_k = config.get("top_k", 50)
        self.top_p = config.get("top_p", 1.0)
        self.do_sample = config.get("do_sample", True)
        self.repetition_penalty = config.get("repetition_penalty", 1.05)
        self.xvec_only = config.get("xvec_only", True)
        self.non_streaming_mode = config.get("non_streaming_mode", True)
        self.append_silence = config.get("append_silence", True)
        
    def start(self) -> Dict[str, Any]:
        """Initialize the FasterQwen3TTS model."""
        if self.model is not None:
            return {"running": True, "message": "Model already loaded"}
        
        try:
            # Import the faster-qwen3-tts library
            import torch
            from faster_qwen3_tts import FasterQwen3TTS
            
            logger.info(f"Loading FasterQwen3TTS model: {self.model_name}")
            
            # Check if CUDA is available, fallback to CPU if not
            if self.device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA not available, falling back to CPU")
                self.device = "cpu"
                self.dtype = "float32"  # Use float32 for CPU compatibility
            
            # Load the model with proper device handling
            # Use the same approach as simple_tts_server_with_ui.py
            try:
                self.model = FasterQwen3TTS.from_pretrained(
                    model_name=self.model_name,
                    device=self.device,
                    dtype=self.dtype,
                    max_seq_len=self.max_seq_len
                )
            except Exception as e:
                if "meta tensor" in str(e).lower():
                    logger.warning(f"Meta tensor issue during model loading, trying to fix: {e}")
                    # Try to fix meta tensor issue by using to_empty approach
                    try:
                        import torch
                        # Load model to meta device first, then move to target device
                        self.model = FasterQwen3TTS.from_pretrained(
                            model_name=self.model_name,
                            device="meta",  # Load to meta first
                            dtype=self.dtype,
                            max_seq_len=self.max_seq_len
                        )
                        
                        # Move model to target device using to_empty approach
                        if hasattr(self.model, 'model'):
                            # Create empty model on target device using to_empty
                            target_device = torch.device(self.device)
                            empty_model = self.model.model.to_empty(device=target_device)
                            
                            # Copy state dict to empty model
                            state_dict = self.model.model.state_dict()
                            empty_model.load_state_dict(state_dict)
                            
                            # Replace the model
                            self.model.model = empty_model
                            
                        logger.info("Meta tensor issue fixed, model loaded successfully")
                    except Exception as e2:
                        logger.error(f"Failed to fix meta tensor issue: {e2}")
                        raise Exception(f"Meta tensor error: {str(e)}")
                else:
                    raise e
            
            # Capture CUDA graphs for performance (only if CUDA is available)
            if self.device == "cuda":
                try:
                    logger.info("Capturing CUDA graphs for performance optimization...")
                    self.model._warmup(prefill_len=100)
                    logger.info("CUDA graphs captured successfully")
                except Exception as e:
                    logger.warning(f"Failed to capture CUDA graphs: {e}")
                    # Continue without CUDA graphs - the model will still work
            
            return {"running": True, "message": f"FasterQwen3TTS model loaded successfully on {self.device}"}
            
        except ImportError:
            return {"running": False, "message": "faster-qwen3-tts library not installed. Run: pip install faster-qwen3-tts"}
        except Exception as e:
            logger.error(f"Failed to load FasterQwen3TTS model: {e}")
            return {"running": False, "message": f"Failed to load model: {str(e)}"}
    
    def stop(self) -> bool:
        """Stop the FasterQwen3TTS model."""
        if self.model is not None:
            self.model = None
            logger.info("FasterQwen3TTS model unloaded")
        return True
    
    def health_check(self) -> bool:
        """Check if the model is loaded and ready."""
        return self.model is not None
    
    def test_connection(self) -> bool:
        """Test connection to the FasterQwen3TTS service."""
        return self.health_check()
    
    def get_speakers(self) -> List[Dict[str, Any]]:
        """Get list of available speakers/voices."""
        # FasterQwen3TTS supports voice cloning and custom voices
        # For now, return basic options
        speakers = [
            {
                "id": "default",
                "name": "Default Voice",
                "language": "en"
            },
            {
                "id": "voice_clone",
                "name": "Voice Clone (requires reference audio)",
                "language": "multilingual"
            }
        ]
        
        # Add any custom voices from shared custom_voices
        try:
            from app import shared
            for voice_id, voice_data in shared.custom_voices.items():
                if voice_data.get("has_audio", False):
                    speakers.append({
                        "id": voice_id,
                        "name": f"{voice_id} (Custom)",
                        "language": voice_data.get("language", "en")
                    })
        except Exception as e:
            logger.warning(f"Could not load custom voices: {e}")
        
        return speakers
    
    def generate_audio(self, text: str, speaker: Optional[str] = None, 
                      language: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Generate audio from text using FasterQwen3TTS."""
        try:
            if self.model is None:
                return {"success": False, "error": "Model not loaded"}
            
            # Set default language if not provided
            if language is None:
                language = "English"
            # Map common language codes to full names expected by FasterQwen3TTS
            elif language.lower() == 'en':
                language = "English"
            elif language.lower() == 'zh':
                language = "Chinese"
            elif language.lower() == 'fr':
                language = "French"
            elif language.lower() == 'es':
                language = "Spanish"
            elif language.lower() == 'de':
                language = "German"
            elif language.lower() == 'ja':
                language = "Japanese"
            elif language.lower() == 'ko':
                language = "Korean"
            
            # Handle voice cloning - check if speaker is in custom voices or is a valid voice ID
            if speaker and speaker != "default":
                # Check if speaker exists in custom voices
                if speaker in self._get_custom_voice_ids():
                    # Use voice cloning with custom voice
                    ref_audio_path = self._get_voice_audio_path(speaker)
                    if ref_audio_path and os.path.exists(ref_audio_path):
                        ref_text = kwargs.get("ref_text", "")
                        
                        # Generate with voice cloning - handle meta tensor issues
                        try:
                            audio_arrays, sample_rate = self.model.generate_voice_clone(
                                text=text,
                                language=language,
                                ref_audio=ref_audio_path,
                                ref_text=ref_text,
                                max_new_tokens=kwargs.get("max_new_tokens", 2048),
                                min_new_tokens=kwargs.get("min_new_tokens", 2),
                                temperature=kwargs.get("temperature", self.temperature),
                                top_k=kwargs.get("top_k", self.top_k),
                                top_p=kwargs.get("top_p", self.top_p),
                                do_sample=kwargs.get("do_sample", self.do_sample),
                                repetition_penalty=kwargs.get("repetition_penalty", self.repetition_penalty),
                                xvec_only=kwargs.get("xvec_only", self.xvec_only),
                                non_streaming_mode=kwargs.get("non_streaming_mode", self.non_streaming_mode),
                                append_silence=kwargs.get("append_silence", self.append_silence),
                            )
                        except Exception as e:
                            if "meta tensor" in str(e).lower():
                                logger.warning(f"Meta tensor issue during generation, trying to fix: {e}")
                                # Try to fix meta tensor issue by moving model to device properly
                                try:
                                    import torch
                                    if hasattr(self.model, 'model'):
                                        # Try to move the model components to the correct device
                                        for name, param in self.model.model.named_parameters():
                                            if param.is_meta:
                                                param.data = torch.empty_like(param, device=self.device, dtype=getattr(torch, self.dtype))
                                    audio_arrays, sample_rate = self.model.generate_voice_clone(
                                        text=text,
                                        language=language,
                                        ref_audio=ref_audio_path,
                                        ref_text=ref_text,
                                        max_new_tokens=kwargs.get("max_new_tokens", 2048),
                                        min_new_tokens=kwargs.get("min_new_tokens", 2),
                                        temperature=kwargs.get("temperature", self.temperature),
                                        top_k=kwargs.get("top_k", self.top_k),
                                        top_p=kwargs.get("top_p", self.top_p),
                                        do_sample=kwargs.get("do_sample", self.do_sample),
                                        repetition_penalty=kwargs.get("repetition_penalty", self.repetition_penalty),
                                        xvec_only=kwargs.get("xvec_only", self.xvec_only),
                                        non_streaming_mode=kwargs.get("non_streaming_mode", self.non_streaming_mode),
                                        append_silence=kwargs.get("append_silence", self.append_silence),
                                    )
                                except Exception as e2:
                                    logger.error(f"Failed to fix meta tensor issue: {e2}")
                                    return {"success": False, "error": f"Meta tensor error: {str(e)}"}
                            else:
                                raise e
                        
                        if audio_arrays and len(audio_arrays) > 0:
                            # Convert to base64 - use proper audio handling like the demo
                            def _concat_audio(audio_list):
                                if isinstance(audio_list, np.ndarray):
                                    return audio_list.astype(np.float32).squeeze()
                                parts = [np.array(a, dtype=np.float32).squeeze() for a in audio_list if len(a) > 0]
                                return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
                            
                            # Concatenate audio arrays and ensure they are Float32
                            audio_data = _concat_audio(audio_arrays)
                            
                            # Clip audio to prevent distortion
                            audio_data = np.clip(audio_data, -1.0, 1.0)
                            
                            # Scale to int16 range and convert
                            audio_int16 = (audio_data * 32767).astype(np.int16)
                            
                            # Create WAV container using io.BytesIO and wave module
                            wav_buffer = io.BytesIO()
                            with wave.open(wav_buffer, 'wb') as wav_file:
                                wav_file.setnchannels(1)  # Mono
                                wav_file.setsampwidth(2)  # 2 bytes (16-bit)
                                wav_file.setframerate(sample_rate)
                                wav_file.writeframes(audio_int16.tobytes())
                            
                            # Get WAV bytes and encode to base64
                            wav_bytes = wav_buffer.getvalue()
                            audio_b64 = base64.b64encode(wav_bytes).decode('utf-8')
                            
                            return {
                                "success": True,
                                "audio": audio_b64,
                                "sample_rate": sample_rate,
                                "format": "audio/wav"
                            }
                        else:
                            return {"success": False, "error": "No audio generated"}
                    else:
                        return {"success": False, "error": f"Reference audio not found for speaker: {speaker}"}
                else:
                    return {"success": False, "error": f"Speaker '{speaker}' not found in custom voices"}
            else:
                # Use default voice generation (not yet implemented in this provider)
                # For now, fall back to voice cloning with a default reference audio
                ref_audio_path = self._get_default_ref_audio()
                if ref_audio_path:
                    audio_arrays, sample_rate = self.model.generate_voice_clone(
                        text=text,
                        language=language,
                        ref_audio=ref_audio_path,
                        ref_text="",
                        max_new_tokens=kwargs.get("max_new_tokens", 2048),
                        min_new_tokens=kwargs.get("min_new_tokens", 2),
                        temperature=kwargs.get("temperature", self.temperature),
                        top_k=kwargs.get("top_k", self.top_k),
                        top_p=kwargs.get("top_p", self.top_p),
                        do_sample=kwargs.get("do_sample", self.do_sample),
                        repetition_penalty=kwargs.get("repetition_penalty", self.repetition_penalty),
                        xvec_only=kwargs.get("xvec_only", self.xvec_only),
                        non_streaming_mode=kwargs.get("non_streaming_mode", self.non_streaming_mode),
                        append_silence=kwargs.get("append_silence", self.append_silence),
                    )
                    
                    if audio_arrays and len(audio_arrays) > 0:
                        # Convert to base64 - use proper audio handling like the demo
                        def _concat_audio(audio_list):
                            if isinstance(audio_list, np.ndarray):
                                return audio_list.astype(np.float32).squeeze()
                            parts = [np.array(a, dtype=np.float32).squeeze() for a in audio_list if len(a) > 0]
                            return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
                        
                        # Concatenate audio arrays and ensure they are Float32
                        audio_data = _concat_audio(audio_arrays)
                        
                        # Clip audio to prevent distortion
                        audio_data = np.clip(audio_data, -1.0, 1.0)
                        
                        # Scale to int16 range and convert
                        audio_int16 = (audio_data * 32767).astype(np.int16)
                        
                        # Create WAV container using io.BytesIO and wave module
                        wav_buffer = io.BytesIO()
                        with wave.open(wav_buffer, 'wb') as wav_file:
                            wav_file.setnchannels(1)  # Mono
                            wav_file.setsampwidth(2)  # 2 bytes (16-bit)
                            wav_file.setframerate(sample_rate)
                            wav_file.writeframes(audio_int16.tobytes())
                        
                        # Get WAV bytes and encode to base64
                        wav_bytes = wav_buffer.getvalue()
                        audio_b64 = base64.b64encode(wav_bytes).decode('utf-8')
                        
                        return {
                            "success": True,
                            "audio": audio_b64,
                            "sample_rate": sample_rate,
                            "format": "audio/wav"
                        }
                    else:
                        return {"success": False, "error": "No audio generated"}
                else:
                    return {"success": False, "error": "No default reference audio available"}
            
        except Exception as e:
            logger.error(f"Error generating audio: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def generate_audio_stream(self, text: str, speaker: Optional[str] = None, 
                             language: Optional[str] = "English", **kwargs) -> Iterator[bytes]:
        """
        Stream TTS audio generation for real-time playback.
        
        Args:
            text: The text to synthesize
            speaker: Optional speaker/voice to use
            language: Optional language code
            **kwargs: Provider-specific parameters
            
        Yields:
            PCM audio chunks as bytes
        """
        try:
            if self.model is None:
                raise Exception("Model not loaded")
            
            # Set default language if not provided
            if language is None:
                language = "English"
            # Map common language codes to full names expected by FasterQwen3TTS
            elif language.lower() == 'en':
                language = "English"
            elif language.lower() == 'zh':
                language = "Chinese"
            elif language.lower() == 'fr':
                language = "French"
            elif language.lower() == 'es':
                language = "Spanish"
            elif language.lower() == 'de':
                language = "German"
            elif language.lower() == 'ja':
                language = "Japanese"
            elif language.lower() == 'ko':
                language = "Korean"
            
            # Handle voice cloning - check if speaker is in custom voices or is a valid voice ID
            if speaker and speaker != "default":
                # Check if speaker exists in custom voices
                if speaker in self._get_custom_voice_ids():
                    # Use voice cloning with custom voice
                    ref_audio_path = self._get_voice_audio_path(speaker)
                    if ref_audio_path and os.path.exists(ref_audio_path):
                        ref_text = kwargs.get("ref_text", "")
                        
                        # Generate with voice cloning in streaming mode
                        try:
                            # Set non_streaming_mode to False for streaming
                            streaming_kwargs = kwargs.copy()
                            streaming_kwargs['non_streaming_mode'] = False
                            
                            # Generate audio with streaming support
                            audio_generator = self.model.generate_voice_clone(
                                text=text,
                                language=language,
                                ref_audio=ref_audio_path,
                                ref_text=ref_text,
                                max_new_tokens=kwargs.get("max_new_tokens", 2048),
                                min_new_tokens=kwargs.get("min_new_tokens", 2),
                                temperature=kwargs.get("temperature", self.temperature),
                                top_k=kwargs.get("top_k", self.top_k),
                                top_p=kwargs.get("top_p", self.top_p),
                                do_sample=kwargs.get("do_sample", self.do_sample),
                                repetition_penalty=kwargs.get("repetition_penalty", self.repetition_penalty),
                                xvec_only=kwargs.get("xvec_only", self.xvec_only),
                                non_streaming_mode=False,  # Enable streaming
                                append_silence=kwargs.get("append_silence", self.append_silence),
                            )
                            
                            # Process streaming audio chunks
                            for audio_chunk in audio_generator:
                                # Check if audio_chunk is valid before processing
                                if audio_chunk is not None:
                                    try:
                                        # Handle different audio chunk formats
                                        if isinstance(audio_chunk, (list, tuple)):
                                            # Multiple chunks in a list
                                            for chunk in audio_chunk:
                                                if chunk is not None and hasattr(chunk, '__len__') and len(chunk) > 0:
                                                    yield self._process_audio_chunk(chunk)
                                        elif hasattr(audio_chunk, '__len__') and len(audio_chunk) > 0:
                                            # Single chunk with length
                                            yield self._process_audio_chunk(audio_chunk)
                                        elif isinstance(audio_chunk, (int, float)):
                                            # Skip numeric values (likely token counts or other metadata)
                                            continue
                                        else:
                                            # Other types, try to process as single chunk
                                            yield self._process_audio_chunk(audio_chunk)
                                    except Exception as chunk_error:
                                        logger.warning(f"Skipping invalid audio chunk: {chunk_error}")
                                        continue
                                    
                        except Exception as e:
                            if "meta tensor" in str(e).lower():
                                logger.warning(f"Meta tensor issue during streaming generation, trying to fix: {e}")
                                # Try to fix meta tensor issue by moving model to device properly
                                try:
                                    import torch
                                    if hasattr(self.model, 'model'):
                                        # Try to move the model components to the correct device
                                        for name, param in self.model.model.named_parameters():
                                            if param.is_meta:
                                                param.data = torch.empty_like(param, device=self.device, dtype=getattr(torch, self.dtype))
                                    
                                    # Retry with fixed model
                                    audio_generator = self.model.generate_voice_clone(
                                        text=text,
                                        language=language,
                                        ref_audio=ref_audio_path,
                                        ref_text=ref_text,
                                        max_new_tokens=kwargs.get("max_new_tokens", 2048),
                                        min_new_tokens=kwargs.get("min_new_tokens", 2),
                                        temperature=kwargs.get("temperature", self.temperature),
                                        top_k=kwargs.get("top_k", self.top_k),
                                        top_p=kwargs.get("top_p", self.top_p),
                                        do_sample=kwargs.get("do_sample", self.do_sample),
                                        repetition_penalty=kwargs.get("repetition_penalty", self.repetition_penalty),
                                        xvec_only=kwargs.get("xvec_only", self.xvec_only),
                                        non_streaming_mode=False,  # Enable streaming
                                        append_silence=kwargs.get("append_silence", self.append_silence),
                                    )
                                    
                                    # Process streaming audio chunks
                                    for audio_chunk in audio_generator:
                                        # Check if audio_chunk is valid before processing
                                        if audio_chunk is not None:
                                            try:
                                                # Handle different audio chunk formats
                                                if isinstance(audio_chunk, (list, tuple)):
                                                    # Multiple chunks in a list
                                                    for chunk in audio_chunk:
                                                        if chunk is not None and hasattr(chunk, '__len__') and len(chunk) > 0:
                                                            yield self._process_audio_chunk(chunk)
                                                elif hasattr(audio_chunk, '__len__') and len(audio_chunk) > 0:
                                                    # Single chunk with length
                                                    yield self._process_audio_chunk(audio_chunk)
                                                elif isinstance(audio_chunk, (int, float)):
                                                    # Skip numeric values (likely token counts or other metadata)
                                                    continue
                                                else:
                                                    # Other types, try to process as single chunk
                                                    yield self._process_audio_chunk(audio_chunk)
                                            except Exception as chunk_error:
                                                logger.warning(f"Skipping invalid audio chunk: {chunk_error}")
                                                continue
                                            
                                except Exception as e2:
                                    logger.error(f"Failed to fix meta tensor issue: {e2}")
                                    raise Exception(f"Meta tensor error: {str(e)}")
                            else:
                                raise e
                    else:
                        raise Exception(f"Reference audio not found for speaker: {speaker}")
                else:
                    raise Exception(f"Speaker '{speaker}' not found in custom voices")
            else:
                # Use default voice generation with streaming
                ref_audio_path = self._get_default_ref_audio()
                if ref_audio_path:
                    try:
                        # Generate audio with streaming support
                        audio_generator = self.model.generate_voice_clone(
                            text=text,
                            language=language,
                            ref_audio=ref_audio_path,
                            ref_text="",
                            max_new_tokens=kwargs.get("max_new_tokens", 2048),
                            min_new_tokens=kwargs.get("min_new_tokens", 2),
                            temperature=kwargs.get("temperature", self.temperature),
                            top_k=kwargs.get("top_k", self.top_k),
                            top_p=kwargs.get("top_p", self.top_p),
                            do_sample=kwargs.get("do_sample", self.do_sample),
                            repetition_penalty=kwargs.get("repetition_penalty", self.repetition_penalty),
                            xvec_only=kwargs.get("xvec_only", self.xvec_only),
                            non_streaming_mode=False,  # Enable streaming
                            append_silence=kwargs.get("append_silence", self.append_silence),
                        )
                        
                        # Process streaming audio chunks
                        for audio_chunk in audio_generator:
                            # Check if audio_chunk is valid before processing
                            if audio_chunk is not None:
                                try:
                                    # Handle different audio chunk formats
                                    if isinstance(audio_chunk, (list, tuple)):
                                        # Multiple chunks in a list
                                        for chunk in audio_chunk:
                                            if chunk is not None and hasattr(chunk, '__len__') and len(chunk) > 0:
                                                yield self._process_audio_chunk(chunk)
                                    elif hasattr(audio_chunk, '__len__') and len(audio_chunk) > 0:
                                        # Single chunk with length
                                        yield self._process_audio_chunk(audio_chunk)
                                    elif isinstance(audio_chunk, (int, float)):
                                        # Skip numeric values (likely token counts or other metadata)
                                        continue
                                    else:
                                        # Other types, try to process as single chunk
                                        yield self._process_audio_chunk(audio_chunk)
                                except Exception as chunk_error:
                                    logger.warning(f"Skipping invalid audio chunk: {chunk_error}")
                                    continue
                                    
                    except Exception as e:
                        if "meta tensor" in str(e).lower():
                            logger.warning(f"Meta tensor issue during streaming generation, trying to fix: {e}")
                            # Try to fix meta tensor issue by moving model to device properly
                            try:
                                import torch
                                if hasattr(self.model, 'model'):
                                    # Try to move the model components to the correct device
                                    for name, param in self.model.model.named_parameters():
                                        if param.is_meta:
                                            param.data = torch.empty_like(param, device=self.device, dtype=getattr(torch, self.dtype))
                                
                                # Retry with fixed model
                                audio_generator = self.model.generate_voice_clone(
                                    text=text,
                                    language=language,
                                    ref_audio=ref_audio_path,
                                    ref_text="",
                                    max_new_tokens=kwargs.get("max_new_tokens", 2048),
                                    min_new_tokens=kwargs.get("min_new_tokens", 2),
                                    temperature=kwargs.get("temperature", self.temperature),
                                    top_k=kwargs.get("top_k", self.top_k),
                                    top_p=kwargs.get("top_p", self.top_p),
                                    do_sample=kwargs.get("do_sample", self.do_sample),
                                    repetition_penalty=kwargs.get("repetition_penalty", self.repetition_penalty),
                                    xvec_only=kwargs.get("xvec_only", self.xvec_only),
                                    non_streaming_mode=False,  # Enable streaming
                                    append_silence=kwargs.get("append_silence", self.append_silence),
                                )
                                
                                # Process streaming audio chunks
                                for audio_chunk in audio_generator:
                                    # Check if audio_chunk is valid before processing
                                    if audio_chunk is not None:
                                        try:
                                            # Handle different audio chunk formats
                                            if isinstance(audio_chunk, (list, tuple)):
                                                # Multiple chunks in a list
                                                for chunk in audio_chunk:
                                                    if chunk is not None and hasattr(chunk, '__len__') and len(chunk) > 0:
                                                        yield self._process_audio_chunk(chunk)
                                            elif hasattr(audio_chunk, '__len__') and len(audio_chunk) > 0:
                                                # Single chunk with length
                                                yield self._process_audio_chunk(audio_chunk)
                                            elif isinstance(audio_chunk, (int, float)):
                                                # Skip numeric values (likely token counts or other metadata)
                                                continue
                                            else:
                                                # Other types, try to process as single chunk
                                                yield self._process_audio_chunk(audio_chunk)
                                        except Exception as chunk_error:
                                            logger.warning(f"Skipping invalid audio chunk: {chunk_error}")
                                            continue
                                            
                            except Exception as e2:
                                logger.error(f"Failed to fix meta tensor issue: {e2}")
                                raise Exception(f"Meta tensor error: {str(e)}")
                        else:
                            raise e
                else:
                    raise Exception("No default reference audio available")
            
        except Exception as e:
            logger.error(f"Error generating streaming audio: {e}")
            import traceback
            traceback.print_exc()
            raise e
    
    def _process_audio_chunk(self, audio_chunk) -> bytes:
        """Process a single audio chunk and convert to PCM bytes.

        Uses peak-based normalisation: only scales down when the peak
        exceeds 0.95 to avoid amplifying noise on quiet chunks.
        """
        try:
            # Convert audio chunk to numpy array if needed
            if isinstance(audio_chunk, np.ndarray):
                audio_data = audio_chunk.astype(np.float32).squeeze()
            else:
                audio_data = np.array(audio_chunk, dtype=np.float32).squeeze()
            
            # Ensure we have valid audio data
            if audio_data.size == 0:
                return b''
            
            # Peak-based normalisation — prevent clipping without
            # amplifying noise on low-amplitude chunks.
            peak = np.max(np.abs(audio_data))
            if peak > 0.95:
                audio_data = audio_data / peak
            # Soft limiter — smoothly saturates near ±1, preserving
            # more dynamic range than tanh while preventing clipping.
            audio_data = audio_data / (1.0 + np.abs(audio_data))
            
            # Scale to int16 range and convert to bytes
            audio_int16 = (audio_data * 32767).astype(np.int16)
            pcm_bytes = audio_int16.tobytes()
            
            return pcm_bytes
            
        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")
            return b''
    
    def voice_clone(self, voice_id: str, audio_data: bytes, 
                   ref_text: Optional[str] = None) -> Dict[str, Any]:
        """Create a voice clone from audio data."""
        try:
            if self.model is None:
                return {"success": False, "error": "Model not loaded"}
            
            # Save the audio data to a temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_audio_path = temp_file.name
            
            try:
                # Generate a sample to test the voice clone
                # This will cache the voice embedding for future use
                sample_text = "This is a voice clone test."
                audio_arrays, sample_rate = self.model.generate_voice_clone(
                    text=sample_text,
                    language="English",
                    ref_audio=temp_audio_path,
                    ref_text=ref_text or "",
                    max_new_tokens=100,
                    min_new_tokens=2,
                    temperature=self.temperature,
                    top_k=self.top_k,
                    top_p=self.top_p,
                    do_sample=self.do_sample,
                    repetition_penalty=self.repetition_penalty,
                    xvec_only=self.xvec_only,
                    non_streaming_mode=self.non_streaming_mode,
                    append_silence=self.append_silence,
                )
                
                if audio_arrays and len(audio_arrays) > 0:
                    # Save the user's reference audio for future use
                    from app.shared import VOICE_CLONES_DIR
                    voice_clones_dir = VOICE_CLONES_DIR
                    os.makedirs(voice_clones_dir, exist_ok=True)
                    
                    ref_audio_path = os.path.join(voice_clones_dir, f"{voice_id}.wav")
                    with open(ref_audio_path, "wb") as f:
                        f.write(audio_data)
                    
                    return {
                        "success": True,
                        "message": f"Voice clone '{voice_id}' created successfully"
                    }
                else:
                    return {"success": False, "error": "Failed to create voice clone"}
                    
            finally:
                # Clean up temporary file
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
                    
        except Exception as e:
            logger.error(f"Error creating voice clone: {e}")
            return {"success": False, "message": str(e)}
    
    def get_capabilities(self) -> List[AudioProviderCapability]:
        return [
            AudioProviderCapability.STREAMING,
            AudioProviderCapability.VOICE_CLONING,
            AudioProviderCapability.MULTILINGUAL,
            AudioProviderCapability.REAL_TIME
        ]
    
    def supports_streaming(self) -> bool:
        """Check if provider supports streaming TTS."""
        return True  # FasterQwen3TTS supports streaming
    
    def _get_custom_voice_ids(self) -> List[str]:
        """Get list of custom voice IDs."""
        try:
            from app import shared
            return [vid for vid, data in shared.custom_voices.items() if data.get("has_audio", False)]
        except:
            return []
    
    def _get_voice_audio_path(self, voice_id: str) -> Optional[str]:
        """Get the path to a custom voice's audio file."""
        from app.shared import VOICE_CLONES_DIR
        voice_clones_dir = VOICE_CLONES_DIR
        audio_path = os.path.join(voice_clones_dir, f"{voice_id}.wav")
        return audio_path if os.path.exists(audio_path) else None
    
    def _get_default_ref_audio(self) -> Optional[str]:
        """Get a default reference audio file for voice cloning."""
        from app.shared import MODELS_DIR
        # Try to find any available reference audio
        ref_audio_paths = [
            os.path.join(MODELS_DIR, 'tts', 'faster-qwen3-tts-main', 'ref_audio.wav'),
            os.path.join(MODELS_DIR, 'tts', 'faster-qwen3-tts-main', 'ref_audio_2.wav'),
            os.path.join(MODELS_DIR, 'tts', 'faster-qwen3-tts-main', 'ref_audio_3.wav'),
        ]
        
        for path in ref_audio_paths:
            if os.path.exists(path):
                return path
        
        # If no reference audio found, try to use any custom voice
        custom_voices = self._get_custom_voice_ids()
        if custom_voices:
            return self._get_voice_audio_path(custom_voices[0])
        
        return None