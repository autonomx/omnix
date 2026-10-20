"""Mixing speaker embeddings: a voice between library voices (Voice Studio Phase 3 §5).

Works on anything with ``*`` and ``+`` (torch tensors, numpy arrays), so it needs no model to test.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def mix_speaker_embeddings(embeddings: Sequence[Any], weights: Sequence[float]) -> Any:
    """The weighted mean of speaker embeddings (weights need not sum to one; negatives are refused)."""
    if not embeddings or len(embeddings) != len(weights):
        raise ValueError("a blend needs one weight per voice")
    if any(weight < 0 for weight in weights) or sum(weights) <= 0:
        raise ValueError("blend weights are positive")
    total = float(sum(weights))
    mixed = embeddings[0] * (float(weights[0]) / total)
    for embedding, weight in zip(embeddings[1:], weights[1:]):
        mixed = mixed + embedding * (float(weight) / total)
    return mixed


__all__ = ["mix_speaker_embeddings"]
