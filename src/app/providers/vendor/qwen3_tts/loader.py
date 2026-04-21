"""
Vendored Qwen3-TTS model loader with caching.

This is the only module that imports directly from the vendored TTS package.
All other code should use this loader interface.
"""

import logging
import threading
from typing import Any, Dict, Optional

from .bootstrap import ensure_vendored_qwen3_tts_available

logger = logging.getLogger(__name__)

# Global model cache
_model_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()


def _classify_qwen3_model_load_error(exc: Exception) -> str:
    message = str(exc or "").strip()
    if "'NoneType' object has no attribute 'get'" in message:
        return (
            "safetensors_metadata_missing_or_incompatible:"
            "transformers attempted metadata.get('format') but shard metadata was None"
        )
    return message or exc.__class__.__name__


def load_tts_model(model_name: str, device: str, **kwargs) -> Any:
    """
    Load and return vendored Qwen3-TTS model runtime instance.
    
    This function always loads a fresh model instance.
    For cached access use get_or_create_tts_model().
    
    Args:
        model_name: HuggingFace model name or local path
        device: Target device ('cuda', 'cpu', 'mps')
        **kwargs: Additional model loading parameters
    
    Returns:
        Initialized FasterQwen3TTS model instance
    
    Raises:
        RuntimeError: If bootstrap or model loading fails
    """
    ensure_vendored_qwen3_tts_available()
    
    # Import only after bootstrap validation is complete
    from app.providers.vendor.faster_qwen3_tts.model import FasterQwen3TTS
    
    logger.info(f"Loading vendored Qwen3-TTS model: {model_name} on {device}")
    
    try:
        model = FasterQwen3TTS.from_pretrained(
            model_name=model_name,
            device=device,
            **kwargs
        )
        
        logger.info(f"Successfully loaded vendored Qwen3-TTS model: {model_name}")
        return model
        
    except Exception as e:
        classified = _classify_qwen3_model_load_error(e)
        logger.error(
            "Failed to load vendored Qwen3-TTS model: %s (raw=%r)",
            classified,
            e,
            exc_info=True,
        )
        raise RuntimeError(f"Model loading failed: {classified}") from e


def get_or_create_tts_model(model_name: str, device: str, **kwargs) -> Any:
    """
    Return cached model instance keyed by model name + device.
    
    Thread-safe singleton access pattern.
    """
    cache_key = f"{model_name}:{device}"
    
    # Fast path: already cached
    if cache_key in _model_cache:
        return _model_cache[cache_key]
    
    # Thread-safe initialization
    with _cache_lock:
        # Double-check after acquiring lock
        if cache_key in _model_cache:
            return _model_cache[cache_key]
        
        model = load_tts_model(model_name, device, **kwargs)
        _model_cache[cache_key] = model
        
        return model


def reset_tts_model_cache() -> None:
    """
    Clear cached vendored TTS model state and free memory.
    
    This will unload all models from GPU/CPU memory.
    Subsequent calls to get_or_create_tts_model() will reload fresh instances.
    """
    global _model_cache
    
    with _cache_lock:
        for model in _model_cache.values():
            if hasattr(model, 'unload'):
                try:
                    model.unload()
                except Exception:
                    pass
        
        _model_cache.clear()
    
    # Force garbage collection
    import gc
    gc.collect()
    
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    
    logger.info("Vendored Qwen3-TTS model cache cleared")