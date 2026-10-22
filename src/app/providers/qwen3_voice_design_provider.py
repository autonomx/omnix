"""Qwen3-TTS VoiceDesign: a voice made from a written description (Voice Studio Phase 3).

The 1.7B VoiceDesign checkpoint speaks text in a voice described by
``instruct`` ("a calm woman in her sixties, slight Irish accent, close mic").
It is a voice tool, not an engine people select: the swap controller loads it
in place of the selected engine for a design session (Phase 1 section 6), and
the engine picker never lists it. It shares the Qwen model loader, so loading
it unloads the base model and the other way round: one model on the GPU.

``seed`` makes a candidate repeatable on one machine; GPU kernels are not
bit-exact across runs, so the same prompt and seed sound alike, not identical.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .faster_qwen3_tts_provider import FasterQwen3TTSProvider
from .tts_priority import generation_slot

logger = logging.getLogger(__name__)

VOICE_DESIGN_MODEL_DIR = "Qwen3-TTS-12Hz-1.7B-VoiceDesign"
MAX_INSTRUCT_CHARS = 600
# Sampling the checkpoint's model card recommends for design.
DESIGN_DEFAULTS: dict[str, Any] = {"temperature": 0.9, "top_k": 50, "top_p": 1.0, "repetition_penalty": 1.05}


class VoiceDesignUnavailable(RuntimeError):
    """The VoiceDesign checkpoint is not installed, or the request cannot be designed."""


def voice_design_model_dir() -> Path:
    from app.runtime.paths import resources_models_root

    return resources_models_root() / "tts" / VOICE_DESIGN_MODEL_DIR


def seeded(seed: int | None) -> None:
    """Seed every generator the sampler draws from."""
    if seed is None:
        return
    import random

    import torch

    random.seed(int(seed))
    np.random.seed(int(seed) % (2 ** 32))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))


class Qwen3VoiceDesignProvider(FasterQwen3TTSProvider):
    provider_name = "qwen3-tts-voicedesign"
    provider_display_name = "Qwen3 VoiceDesign"
    provider_description = "Creates a voice from a written description (Voice Studio's Design tool)"
    generation_strategy_revision = "qwen3-voicedesign-v1"
    default_capabilities: list[Any] = []

    @staticmethod
    def local_model_artifacts():
        from .tts_artifacts import LocalArtifactsUnavailable, LocalModelArtifacts

        directory = voice_design_model_dir()
        if not directory.is_dir() or not list(directory.glob("*.safetensors")):
            raise LocalArtifactsUnavailable("install Qwen3-TTS 1.7B VoiceDesign from Voice Studio's Models tool")
        return LocalModelArtifacts(model_id="Qwen3-TTS-VoiceDesign", directory=directory)

    def _validate_config(self) -> None:
        # Not the base resolution: OMNIX_TTS_MODEL_DIR names the selected engine's checkpoint.
        self._model_config["model_name"] = str(self._model_config.get("model_dir") or voice_design_model_dir())
        self.device = self._model_config.get("device", "cuda")
        self.dtype = self._model_config.get("dtype", "bfloat16")
        self.max_seq_len = self._model_config.get("max_seq_len", 2048)
        self._model_config.update(device=self.device, dtype=self.dtype, max_seq_len=self.max_seq_len)

    def get_speakers(self) -> list[dict[str, Any]]:
        return []

    def supports_streaming(self) -> bool:
        return False

    def supports_voice_cloning(self) -> bool:
        return False

    def generate_audio(self, text: str, speaker: Optional[str] = None, language: Optional[str] = None,
                       **kwargs: Any) -> dict[str, Any]:
        """Speak ``text`` in the voice ``instruct`` describes; ``speaker`` is ignored."""
        del speaker
        instruct = str(kwargs.get("instruct") or "").strip()
        if not instruct:
            return {"success": False, "error": "voice design needs a description (instruct)"}
        if len(instruct) > MAX_INSTRUCT_CHARS:
            return {"success": False, "error": f"the description is over {MAX_INSTRUCT_CHARS} characters"}
        if not str(text or "").strip():
            return {"success": False, "error": "nothing to say"}
        sampling = {key: kwargs.get(key, value) for key, value in DESIGN_DEFAULTS.items()}
        seed = kwargs.get("seed")
        try:
            with generation_slot():
                model = self._get_model()
                started = time.perf_counter()
                seeded(None if seed is None else int(seed))
                audio_list, sample_rate = model.generate_voice_design(
                    text=str(text), instruct=instruct, language=self._map_language(language),
                    max_new_tokens=int(kwargs.get("max_new_tokens") or 2048), **sampling,
                )
        except Exception as exc:
            logger.warning("Voice design failed: %s", exc)
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
        audio = np.concatenate([np.asarray(part, dtype=np.float32).reshape(-1) for part in audio_list])
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak > 0.99:
            audio = audio * (0.99 / peak)
        duration = len(audio) / float(sample_rate)
        return self._build_audio_response(
            wav_bytes=self._numpy_to_wav_bytes(audio, int(sample_rate)),
            sample_rate=int(sample_rate),
            duration=duration,
            extra_fields={"seed": seed, "instruct": instruct, "model_revision": design_model_revision(),
                          "generation_seconds": round(time.perf_counter() - started, 3), "is_fallback": False},
        )

    def generate_audio_stream(self, *args: Any, **kwargs: Any):
        raise VoiceDesignUnavailable("voice design renders whole clips; it does not stream")

    def voice_clone(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"success": False, "error": "voice design does not clone; save a designed voice instead"}


def design_model_revision() -> str:
    """The installed checkpoint's pinned commit (from the Models install marker), or ''."""
    import json

    marker = voice_design_model_dir() / ".omnix-model.json"
    try:
        return str(json.loads(marker.read_text(encoding="utf-8")).get("commit") or "")
    except (OSError, ValueError):
        return ""


__all__ = ["DESIGN_DEFAULTS", "Qwen3VoiceDesignProvider", "VoiceDesignUnavailable", "design_model_revision",
           "seeded", "voice_design_model_dir"]
