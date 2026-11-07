"""Whether a speaker has finished their turn, judged from the sound of their voice (Pipecat Smart Turn v3.2).

Parakeet's end-of-utterance signal fires at nearly every pause, including the 430-480 ms ones people make inside a
sentence, so a turn used to wait 500 ms of silence whatever was said. Smart Turn listens to the last 8 s, intonation
included, and gives the probability that the speaker is done; the live client ends a turn sooner when it is sure.
On a 4090 host it takes about 12 ms of CPU.

Optional: without onnxruntime or the model file, ``turn_complete_probability`` returns None and turns wait as before.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.config.env import env_str

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
WINDOW_SAMPLES = 8 * SAMPLE_RATE
MODEL_REPO = "pipecat-ai/smart-turn-v3"
MODEL_REVISION = "f766f81d3cfdf7737ac64aad813d91bbfd56bf93"
MODEL_FILE = "smart-turn-v3.2-cpu.onnx"


class _SmartTurn:
    """One ONNX session and feature extractor for the process, loaded on first use or at service start."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._session: Any = None
        self._extractor: Any = None

    def load(self) -> bool:
        with self._lock:
            if self._loaded:
                return self._session is not None
            self._loaded = True
            try:
                import onnxruntime as ort
                from transformers import WhisperFeatureExtractor

                path = env_str("OMNIX_SMART_TURN_MODEL", "").strip() or _cached_model_file()
                options = ort.SessionOptions()
                options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                options.inter_op_num_threads = 1
                options.intra_op_num_threads = 1
                options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                self._session = ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])
                self._extractor = WhisperFeatureExtractor(chunk_length=8)
                logger.info("[STT] Smart Turn ready: %s", path)
            except Exception as exc:  # noqa: BLE001 - optional: turns keep the fixed wait
                self._session = None
                logger.warning("[STT] Smart Turn unavailable, turns keep the fixed wait: %s: %s", type(exc).__name__, exc)
            return self._session is not None

    def probability(self, pcm16le: bytes) -> float | None:
        if not self.load():
            return None
        import numpy as np

        audio = np.frombuffer(pcm16le[-WINDOW_SAMPLES * 2:], dtype="<i2").astype(np.float32) / 32768.0
        if audio.size == 0:
            return None
        if audio.size < WINDOW_SAMPLES:  # as Smart Turn was trained: silence before, never after
            audio = np.pad(audio, (WINDOW_SAMPLES - audio.size, 0))
        features = self._extractor(
            audio, sampling_rate=SAMPLE_RATE, return_tensors="np", padding="max_length",
            max_length=WINDOW_SAMPLES, truncation=True, do_normalize=True,
        ).input_features.astype(np.float32)
        return float(self._session.run(None, {"input_features": features})[0][0].item())


def _cached_model_file() -> str:
    """The pinned file from the Hugging Face cache, where the model catalog installs it. Never fetched from here."""
    from huggingface_hub import hf_hub_download

    return str(hf_hub_download(MODEL_REPO, MODEL_FILE, revision=MODEL_REVISION, local_files_only=True))


_MODEL = _SmartTurn()


def load_smart_turn() -> bool:
    """Load at service start, so the first turn does not pay for it."""
    return _MODEL.load()


def turn_complete_probability(pcm16le: bytes) -> float | None:
    """The probability, 0 to 1, that the speaker of this 16 kHz mono PCM is done; None when Smart Turn is unavailable."""
    try:
        return _MODEL.probability(pcm16le)
    except Exception as exc:  # noqa: BLE001 - a failed judgement leaves the turn to the fixed wait
        logger.warning("[STT] Smart Turn judgement failed: %s: %s", type(exc).__name__, exc)
        return None


__all__ = ["load_smart_turn", "turn_complete_probability"]
