from __future__ import annotations

import numpy as np


def apply_fade(audio: np.ndarray, fade_samples: int = 128) -> np.ndarray:
    if audio is None or len(audio) == 0 or fade_samples <= 0:
        return audio
    n = min(len(audio), fade_samples)
    out = np.asarray(audio, dtype=np.float32).copy()
    fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
    fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
    out[:n] *= fade_in
    out[-n:] *= fade_out
    return out


def soft_clip(audio: np.ndarray) -> np.ndarray:
    if audio is None or len(audio) == 0:
        return audio
    out = np.tanh(np.asarray(audio, dtype=np.float32))
    return out.astype(np.float32, copy=False)


def find_best_offset(prev_audio: np.ndarray, curr_audio: np.ndarray, max_offset: int = 256) -> int:
    if prev_audio is None or curr_audio is None:
        return 0
    if len(prev_audio) == 0 or len(curr_audio) == 0:
        return 0

    tail = np.asarray(prev_audio[-max_offset:], dtype=np.float32)
    best_offset = 0
    best_score = None
    upper = min(max_offset, len(curr_audio))
    for offset in range(upper):
        overlap = min(len(tail), len(curr_audio) - offset)
        if overlap <= 16:
            break
        a = tail[-overlap:]
        b = curr_audio[offset:offset + overlap]
        score = float(np.mean((a - b) ** 2))
        if best_score is None or score < best_score:
            best_score = score
            best_offset = offset
    return best_offset