"""
Faster Qwen3 TTS Provider Plugin

Implements the BaseTTSProvider interface for the faster-qwen3-tts library
with CUDA graph acceleration for real-time voice cloning.
"""

import os
import sys
import logging
import threading
import time
from pathlib import Path
from io import BytesIO
from typing import List, Optional, Dict, Any, Iterator, Union
from dataclasses import dataclass, field
import numpy as np

from .audio_base import BaseTTSProvider, AudioProviderConfig, TTSAudioResponse, AudioProviderCapability
from ..shared import MODELS_DIR, VOICE_CLONES_DIR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audio hardening helpers  (Issue 3 – prevent stream corruption)
# ---------------------------------------------------------------------------

def _is_valid_audio(audio: np.ndarray) -> bool:
    """Return *True* if *audio* is a usable waveform array."""
    if audio is None or len(audio) == 0:
        return False
    if np.isnan(audio).any():
        return False
    # Silence bug – all-zero / near-zero output
    if np.max(np.abs(audio)) < 1e-5:
        return False
    # Explosion bug – values far outside normal range
    if np.max(np.abs(audio)) > 5:
        return False
    return True


def soft_clip(x: np.ndarray) -> np.ndarray:
    """Gentle soft limiter: ``x / (1 + |x|)``.

    Smoothly saturates near ±1 while preserving more dynamic range than
    ``np.tanh``.  Unlike hard clipping (``np.clip``) it never introduces
    discontinuities.
    """
    return x / (1.0 + np.abs(x))


def find_best_offset(prev: np.ndarray, curr: np.ndarray,
                     max_shift: int = 128) -> int:
    """Find the sample offset in *curr* that best aligns with *prev*.

    TTS chunks often start at arbitrary waveform phase, causing micro
    discontinuities even with a raised-cosine crossfade.  This helper
    slides *curr* by up to *max_shift* samples and returns the offset
    that minimises the mean-squared difference against the tail of
    *prev*, producing a smoother splice.
    """
    if prev is None or curr is None or len(prev) == 0 or len(curr) == 0:
        return 0

    best_offset = 0
    best_score = float('inf')

    for shift in range(max_shift):
        overlap = min(len(prev), len(curr) - shift)
        if overlap <= 0:
            continue

        diff = prev[-overlap:] - curr[shift:shift + overlap]
        score = np.mean(diff ** 2)

        if score < best_score:
            best_score = score
            best_offset = shift

    return best_offset


def _normalize_audio(audio: np.ndarray) -> bytes:
    """Normalise a float waveform to 16-bit PCM bytes.

    Uses peak-based normalisation to avoid amplifying noise when the
    signal is already within range.  Only scales down when the peak
    exceeds 0.95 (close to clipping).  Final limiting uses
    :func:`soft_clip` for a smooth curve instead of hard clipping.
    """
    audio = audio.astype(np.float32)
    peak = np.max(np.abs(audio)) if len(audio) > 0 else 0.0
    if peak > 0.95:
        audio = audio / peak
    # Soft limiter — smoothly saturates near ±1, preserving more
    # dynamic range than tanh while still preventing hard clipping.
    audio = soft_clip(audio)
    audio_int16 = (audio * 32767).astype(np.int16)
    return audio_int16.tobytes()


def _align_bytes(audio_bytes: bytes) -> bytes:
    """Ensure *audio_bytes* length is a multiple of 2 (16-bit frame boundary)."""
    remainder = len(audio_bytes) % 2
    if remainder != 0:
        audio_bytes = audio_bytes[:-remainder]
    return audio_bytes


def crossfade_audio(prev: np.ndarray, curr: np.ndarray,
                    fade_samples: int = 512) -> np.ndarray:
    """Crossfade *prev* into *curr* over *fade_samples* using a raised-cosine curve.

    If either array is too short for a full crossfade the arrays are simply
    concatenated so no samples are lost.
    """
    if prev is None or len(prev) < fade_samples or len(curr) < fade_samples:
        if prev is not None:
            return np.concatenate([prev, curr]) if curr is not None else prev.copy()
        return curr if curr is not None else np.array([], dtype=np.float32)

    t = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
    fade_in = 0.5 * (1.0 - np.cos(np.pi * t))   # raised-cosine
    fade_out = 1.0 - fade_in

    prev_tail = prev[-fade_samples:] * fade_out
    curr_head = curr[:fade_samples] * fade_in

    blended = prev_tail + curr_head

    return np.concatenate([
        prev[:-fade_samples],
        blended,
        curr[fade_samples:],
    ])


def apply_fade(audio: np.ndarray, fade_samples: int = 256) -> np.ndarray:
    """Apply a micro fade-in / fade-out to *audio* to eliminate edge clicks.

    Uses a raised-cosine ramp for perceptually smooth transitions.
    Returns a *copy* so the caller's original array is not mutated.
    """
    if audio is None or len(audio) < 2 * fade_samples:
        return audio.copy() if audio is not None else np.array([], dtype=np.float32)

    audio = audio.copy()
    n = min(fade_samples, len(audio) // 2)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    ramp = 0.5 * (1.0 - np.cos(np.pi * t))   # raised-cosine ramp
    audio[:n] *= ramp
    audio[-n:] *= ramp[::-1]
    return audio


def silence_pad(audio: np.ndarray, sample_rate: int,
                duration_sec: float = 0.05) -> np.ndarray:
    """Append a short silence to *audio* to guard against abrupt transitions."""
    silence = np.zeros(int(duration_sec * sample_rate), dtype=np.float32)
    return np.concatenate([audio, silence])


@dataclass
class ModelLoader:
    """Helper class to manage model loading state."""
    model: Any = None
    device: str = "cuda"
    initialized: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


# Global model loader singleton
_model_loader = ModelLoader()


class FasterQwen3TTSProvider(BaseTTSProvider):
    """
    TTS provider using FasterQwen3TTS with CUDA graphs for real-time performance.
    
    Supports voice cloning with reference audio and multilingual synthesis.
    """
    
    provider_name = "faster-qwen3-tts"
    provider_display_name = "Faster Qwen3 TTS"
    provider_description = "Real-time voice cloning TTS with CUDA graph acceleration (6-10x speedup)"
    
    default_capabilities = [
        AudioProviderCapability.STREAMING,
        AudioProviderCapability.VOICE_CLONING,
        AudioProviderCapability.MULTILINGUAL,
        AudioProviderCapability.REAL_TIME,
    ]
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the FasterQwen3TTS provider.
        
        Args:
            config: Provider configuration dict. For faster-qwen3-tts, this contains
                   the full settings from settings.json['faster-qwen3-tts'] with keys:
                   model_name, device, dtype, max_seq_len, chunk_size, temperature, top_k, etc.
        """
        super().__init__(config)
        # The config directly contains the model settings (not wrapped in extra_params)
        self._model_config = self.config.copy()
        self._sample_rate = 12000  # Qwen3-TTS uses 12kHz
        self._model_instance = None
        # Validate configuration and set defaults immediately
        self._validate_config()
        
    def _validate_config(self):
        """Validate and set defaults for provider configuration."""
        # Set default model name if not provided
        if not self._model_config.get('model_name'):
            self._model_config['model_name'] = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
        
        # Set device
        self.device = self._model_config.get('device', 'cuda')
        self.dtype = self._model_config.get('dtype', 'bfloat16')
        self.max_seq_len = self._model_config.get('max_seq_len', 2048)
        
        logger.info(f"FasterQwen3TTS configured: model={self._model_config['model_name']}, device={self.device}")
    
    def _get_model(self):
        """
        Get or initialize the FasterQwen3TTS model instance.
        Uses singleton pattern with thread-safe lazy initialization.
        """
        global _model_loader
        
        # Fast path: already initialized
        if _model_loader.model is not None and _model_loader.initialized:
            return _model_loader.model
        
        # Thread-safe initialization
        with _model_loader.lock:
            # Double-check pattern
            if _model_loader.model is not None and _model_loader.initialized:
                return _model_loader.model
            
            try:
                logger.info("Loading FasterQwen3TTS model...")
                
                # Add the faster-qwen3-tts directory to Python path if not already
                tts_lib_path = Path(__file__).parent.parent.parent.parent / 'resources' / 'models' / 'tts' / 'faster-qwen3-tts-main'
                if tts_lib_path.exists() and str(tts_lib_path) not in sys.path:
                    sys.path.insert(0, str(tts_lib_path))
                
                # Import the FasterQwen3TTS class
                from faster_qwen3_tts.model import FasterQwen3TTS
                
                # Load the model
                model_name = self._model_config['model_name']
                model = FasterQwen3TTS.from_pretrained(
                    model_name=model_name,
                    device=self.device,
                    dtype=self.dtype,
                    max_seq_len=self.max_seq_len
                )
                
                _model_loader.model = model
                _model_loader.initialized = True
                logger.info("FasterQwen3TTS model loaded successfully")
                
                return model
                
            except ImportError as e:
                logger.error(f"Failed to import faster_qwen3_tts: {e}")
                raise
            except Exception as e:
                logger.error(f"Failed to load FasterQwen3TTS model: {e}")
                raise
    
    def _convert_audio_to_float32(self, audio_data: Union[bytes, np.ndarray], sample_rate: int = 24000) -> np.ndarray:
        """
        Convert audio data to float32 numpy array.
        
        Args:
            audio_data: Audio as bytes (WAV) or numpy array
            sample_rate: Expected sample rate
            
        Returns:
            Float32 mono audio array normalized to [-1, 1]
        """
        import numpy as np
        import soundfile as io
        from io import BytesIO
        
        if isinstance(audio_data, bytes):
            # Decode WAV bytes
            with BytesIO(audio_data) as bio:
                audio, sr = io.read(bio, dtype='float32', always_2d=False)
            if sr != sample_rate:
                # Simple resampling would be needed - for now require correct sample rate
                logger.warning(f"Sample rate mismatch: got {sr}, expected {sample_rate}")
        else:
            audio = audio_data
        
        # Ensure mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        
        # Normalize to [-1, 1] if needed
        max_val = np.max(np.abs(audio))
        if max_val > 1.0:
            audio = audio / max_val
            
        return audio.astype(np.float32)
    
    def _numpy_to_wav_bytes(self, audio: np.ndarray, sample_rate: int = 12000) -> bytes:
        """
        Convert float32 numpy array to WAV bytes.
        
        Args:
            audio: Float32 audio array
            sample_rate: Sample rate
            
        Returns:
            WAV file as bytes
        """
        import soundfile as io
        from io import BytesIO
        
        with BytesIO() as bio:
            io.write(bio, audio, sample_rate, format='WAV', subtype='PCM_16')
            return bio.getvalue()
    
    def get_speakers(self) -> List[Dict[str, Any]]:
        """
        Get list of available speakers/voices.
        
        For faster-qwen3-tts, speakers are derived from voice clones.
        
        Returns:
            List of speaker dictionaries with 'id', 'name', 'language' keys
        """
        speakers = []
        
        # Add default speaker
        speakers.append({
            "id": "default",
            "name": "Default",
            "language": "en",
            "description": "Default voice"
        })
        
        # Add custom voice clones
        voice_clones_dir = Path(VOICE_CLONES_DIR)
        if voice_clones_dir.exists():
            for wav_file in voice_clones_dir.glob('*.wav'):
                voice_id = wav_file.stem
                speakers.append({
                    "id": voice_id,
                    "name": voice_id,
                    "language": "en",  # Could be detected from metadata or config
                    "path": str(wav_file),
                    "description": f"Custom voice: {voice_id}"
                })
        
        return speakers
    
    def _map_language(self, language: Optional[str]) -> str:
        """Map language codes to model-supported language names."""
        if not language:
            return "English"
        
        # Language code to name mapping
        language_map = {
            'en': 'English',
            'zh': 'Chinese',
            'ja': 'Japanese',
            'fr': 'French',
            'de': 'German',
            'es': 'Spanish',
            'it': 'Italian',
            'ru': 'Russian',
            'ko': 'Korean',
            'pt': 'Portuguese',
        }
        
        # Return mapped language or original if not found
        return language_map.get(language.lower(), language)
    
    def generate_audio(
        self,
        text: str,
        speaker: Optional[str] = None,
        language: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate audio from text using voice cloning.
        
        Args:
            text: Text to synthesize
            speaker: Speaker ID (refers to voice clone audio file)
            language: Language code (e.g., 'en', 'zh', 'ja')
            **kwargs: Additional parameters
                - ref_text: Transcription of reference audio
                - temperature: Sampling temperature (0.5-1.0)
                - top_k: Top-k sampling parameter
                - repetition_penalty: Repetition penalty factor
                - xvec_only: Use only speaker embedding (True) or full ICL (False)
                
        Returns:
            Dict with 'success', 'audio' (base64 WAV), 'sample_rate', 'duration'
        """
        try:
            # Get reference audio path
            ref_audio_path = None
            if speaker:
                voice_clones_dir = Path(VOICE_CLONES_DIR)
                ref_path = voice_clones_dir / f"{speaker}.wav"
                if ref_path.exists():
                    ref_audio_path = str(ref_path)
            
            # Fallback to default reference audio
            if not ref_audio_path:
                default_ref = voice_clones_dir / "default_ref.wav"
                if default_ref.exists():
                    ref_audio_path = str(default_ref)
            
            if not ref_audio_path:
                # Try to find any wav file in voice_clones as fallback
                if voice_clones_dir.exists():
                    wav_files = list(voice_clones_dir.glob('*.wav'))
                    if wav_files:
                        ref_audio_path = str(wav_files[0])
            
            if not ref_audio_path:
                return {
                    "success": False,
                    "error": "No reference audio available for voice cloning. Please upload a voice sample first."
                }
            
            # Load the model
            model = self._get_model()
            
            # Prepare generation parameters
            gen_kwargs = {
                'text': text,
                'language': self._map_language(language),
                'ref_audio': ref_audio_path,
                'ref_text': kwargs.get('ref_text', ''),
                'max_new_tokens': kwargs.get('max_new_tokens', self.max_seq_len),
                'min_new_tokens': kwargs.get('min_new_tokens', 2),
                'temperature': kwargs.get('temperature', self._model_config.get('temperature', 0.9)),
                'top_k': kwargs.get('top_k', self._model_config.get('top_k', 50)),
                'top_p': kwargs.get('top_p', self._model_config.get('top_p', 1.0)),
                'do_sample': kwargs.get('do_sample', self._model_config.get('do_sample', True)),
                'repetition_penalty': kwargs.get('repetition_penalty', self._model_config.get('repetition_penalty', 1.05)),
                'xvec_only': kwargs.get('xvec_only', self._model_config.get('xvec_only', True)),
                'non_streaming_mode': kwargs.get('non_streaming_mode', self._model_config.get('non_streaming_mode', True)),
                'append_silence': kwargs.get('append_silence', self._model_config.get('append_silence', True)),
            }
            
            # Generate audio (non-streaming)
            audio_list, sample_rate = model.generate_voice_clone(**gen_kwargs)
            
            if not audio_list or len(audio_list) == 0:
                return {
                    "success": False,
                    "error": "No audio generated"
                }
            
            # Validate the raw waveform before encoding
            audio_np = audio_list[0]  # First (and only) audio array
            if not _is_valid_audio(audio_np):
                logger.warning("[TTS] Invalid audio detected – retrying once")
                audio_list, sample_rate = model.generate_voice_clone(**gen_kwargs)
                if not audio_list or not _is_valid_audio(audio_list[0]):
                    return {
                        "success": False,
                        "error": "Generated audio failed validation (corrupt or silent)"
                    }
                audio_np = audio_list[0]

            # Convert to WAV bytes
            wav_bytes = self._numpy_to_wav_bytes(audio_np, sample_rate)
            
            # Calculate duration
            duration = len(audio_np) / sample_rate
            logger.info("[TTS] generated chunk size=%d bytes, duration=%.2fs", len(wav_bytes), duration)
            
            # Encode as base64
            import base64
            audio_b64 = base64.b64encode(wav_bytes).decode('utf-8')
            
            return {
                "success": True,
                "audio": audio_b64,
                "sample_rate": sample_rate,
                "duration": duration,
                "format": "audio/wav",
                "raw_response": None
            }
            
        except Exception as e:
            logger.error(f"Error in generate_audio: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_audio_stream(
        self,
        text: str,
        speaker: Optional[str] = None,
        language: Optional[str] = None,
        **kwargs
    ) -> Iterator[tuple[np.ndarray, int, dict]]:
        """
        Stream audio generation for real-time playback.
        
        Args:
            text: Text to synthesize
            speaker: Speaker ID (refers to voice clone audio file)
            language: Language code
            **kwargs: Same as generate_audio() plus:
                - chunk_size: Number of codec steps per chunk (default 12)
                
        Yields:
            Tuples of (audio_chunk_numpy, sample_rate, timing_dict)
        """
        try:
            # Get reference audio path
            ref_audio_path = None
            voice_clones_dir = Path(VOICE_CLONES_DIR)
            if speaker:
                ref_path = voice_clones_dir / f"{speaker}.wav"
                if ref_path.exists():
                    ref_audio_path = str(ref_path)
            
            if not ref_audio_path:
                default_ref = voice_clones_dir / "default_ref.wav"
                if default_ref.exists():
                    ref_audio_path = str(default_ref)
            
            if not ref_audio_path:
                # Try to find any wav file in voice_clones as fallback
                if voice_clones_dir.exists():
                    wav_files = list(voice_clones_dir.glob('*.wav'))
                    if wav_files:
                        ref_audio_path = str(wav_files[0])
            
            if not ref_audio_path:
                raise Exception("No reference audio available for voice cloning")
            
            # Load the model
            model = self._get_model()
            
            # Prepare generation parameters
            gen_kwargs = {
                'text': text,
                'language': self._map_language(language),
                'ref_audio': ref_audio_path,
                'ref_text': kwargs.get('ref_text', ''),
                'max_new_tokens': kwargs.get('max_new_tokens', self.max_seq_len),
                'min_new_tokens': kwargs.get('min_new_tokens', 2),
                'temperature': kwargs.get('temperature', self._model_config.get('temperature', 0.9)),
                'top_k': kwargs.get('top_k', self._model_config.get('top_k', 50)),
                'top_p': kwargs.get('top_p', self._model_config.get('top_p', 1.0)),
                'do_sample': kwargs.get('do_sample', self._model_config.get('do_sample', True)),
                'repetition_penalty': kwargs.get('repetition_penalty', self._model_config.get('repetition_penalty', 1.05)),
                'chunk_size': kwargs.get('chunk_size', self._model_config.get('chunk_size', 12)),
                'xvec_only': kwargs.get('xvec_only', self._model_config.get('xvec_only', True)),
                'non_streaming_mode': kwargs.get('non_streaming_mode', self._model_config.get('non_streaming_mode', True)),
                'append_silence': kwargs.get('append_silence', self._model_config.get('append_silence', True)),
            }
            
            # Stream generation – validate each chunk before yielding
            chunk_idx = 0
            for audio_chunk, sr, timing in model.generate_voice_clone_streaming(**gen_kwargs):
                if not _is_valid_audio(audio_chunk):
                    logger.warning("[TTS] Skipping corrupt streaming chunk %d", chunk_idx)
                    chunk_idx += 1
                    continue
                logger.info("[TTS] streaming chunk=%d size=%d samples", chunk_idx, len(audio_chunk))
                yield audio_chunk, sr, timing
                chunk_idx += 1
                
        except Exception as e:
            logger.error(f"Error in generate_audio_stream: {e}", exc_info=True)
            raise
    
    def voice_clone(
        self,
        voice_id: str,
        audio_data: bytes,
        ref_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a voice clone from audio data.
        
        For faster-qwen3-tts, voice cloning is done by saving the reference audio
        to the voice_clones directory. The actual cloning happens during generation.
        
        Args:
            voice_id: Unique identifier for the voice clone
            audio_data: Reference audio data (WAV format)
            ref_text: Optional transcription of the reference audio
            
        Returns:
            Dict with 'success', 'message', 'voice_id'
        """
        try:
            # Validate voice_id (alphanumeric + underscores)
            import re
            if not re.match(r'^[a-zA-Z0-9_\-]+$', voice_id):
                return {
                    "success": False,
                    "error": "Invalid voice ID. Use only letters, numbers, hyphens, and underscores."
                }
            
            # Ensure voice_clones directory exists
            voice_clones_dir = Path(VOICE_CLONES_DIR)
            voice_clones_dir.mkdir(parents=True, exist_ok=True)
            
            # Save the audio file
            output_path = voice_clones_dir / f"{voice_id}.wav"
            
            # Validate WAV format
            import wave
            with wave.open(BytesIO(audio_data), 'rb') as wav_file:
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                frames = wav_file.getnframes()
                
                # Check if it's a valid WAV
                if channels not in [1, 2]:
                    return {
                        "success": False,
                        "error": f"Invalid WAV: must be mono or stereo, got {channels} channels"
                    }
            
            # Write the file
            output_path.write_bytes(audio_data)
            
            logger.info(f"Voice clone created: {voice_id} ({framerate} Hz, {frames} frames)")
            
            return {
                "success": True,
                "message": f"Voice clone '{voice_id}' created successfully",
                "voice_id": voice_id
            }
            
        except Exception as e:
            logger.error(f"Error in voice_clone: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def health_check(self) -> bool:
        """
        Check if the service is healthy.
        
        Returns:
            True if model is loaded and responsive, False otherwise
        """
        try:
            # Try to get the model (does not initialize if not ready)
            if _model_loader.model is not None and _model_loader.initialized:
                return True
            
            # Quick test: can we import the library?
            tts_lib_path = Path(__file__).parent.parent.parent / 'models' / 'tts' / 'faster-qwen3-tts-main'
            if not tts_lib_path.exists():
                logger.warning("faster-qwen3-tts library not found")
                return False
            
            # Check if CUDA is available if using CUDA
            if self.device == 'cuda':
                import torch
                if not torch.cuda.is_available():
                    logger.warning("CUDA requested but not available")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def test_connection(self) -> bool:
        """
        Test connection (alias for health_check).
        
        Returns:
            True if provider is ready, False otherwise
        """
        return self.health_check()
    
    def get_capabilities(self) -> List[AudioProviderCapability]:
        """
        Get list of capabilities supported by this provider.
        
        Returns:
            List of AudioProviderCapability enums
        """
        return self.default_capabilities.copy()
    
    def supports_streaming(self) -> bool:
        """Check if provider supports streaming TTS."""
        return True
    
    def supports_voice_cloning(self) -> bool:
        """Check if provider supports voice cloning."""
        return True
    
    def start(self) -> Dict[str, Any]:
        """
        Start the provider (initialize model).
        
        Returns:
            Dict with 'running' status and 'message'
        """
        try:
            self._validate_config()
            model = self._get_model()
            return {
                "running": True,
                "message": f"FasterQwen3TTS initialized with {self._model_config['model_name']}"
            }
        except Exception as e:
            logger.error(f"Failed to start provider: {e}")
            return {
                "running": False,
                "message": f"Failed to start: {str(e)}"
            }
    
    def stop(self) -> bool:
        """
        Stop the provider (unload model).
        
        Returns:
            True if stopped successfully
        """
        global _model_loader
        
        try:
            with _model_loader.lock:
                if _model_loader.model is not None:
                    # Clear the model to free memory
                    _model_loader.model = None
                    _model_loader.initialized = False
                    
                    # Force garbage collection
                    import gc
                    import torch
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    
                    logger.info("FasterQwen3TTS model unloaded")
                    
                return True
        except Exception as e:
            logger.error(f"Error stopping provider: {e}")
            return False