"""Deterministic end-of-sequence policy for streaming codec generation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TerminationReason = Literal[
    "natural_eos",
    "forced_eos",
    "token_limit",
    "sequence_limit",
    "model_stopped",
]


@dataclass(frozen=True)
class StreamingEosPolicy:
    """Control how streaming generation transitions from natural to forced EOS."""

    bias_start_steps: int = 2
    force_after_steps: int = 8
    bias_per_step: float = 2.0

    def __post_init__(self) -> None:
        if self.bias_start_steps < 0:
            raise ValueError("bias_start_steps must be non-negative")
        if self.force_after_steps <= 0:
            raise ValueError("force_after_steps must be positive")
        if self.force_after_steps < self.bias_start_steps:
            raise ValueError("force_after_steps must be >= bias_start_steps")
        if self.bias_per_step < 0:
            raise ValueError("bias_per_step must be non-negative")


def post_text_steps(generation_step: int, text_context_steps: int) -> int:
    """Return how many codec steps have advanced beyond text alignment context."""

    return max(0, int(generation_step) - max(0, int(text_context_steps)))


def eos_logit_bias(
    generation_step: int,
    text_context_steps: int,
    policy: StreamingEosPolicy,
) -> float:
    """Return the progressive EOS logit bias for the current generation step."""

    extra_steps = post_text_steps(generation_step, text_context_steps)
    if extra_steps < policy.bias_start_steps:
        return 0.0
    return (extra_steps - policy.bias_start_steps + 1) * policy.bias_per_step


def classify_after_sample(
    *,
    sampled_token_id: int,
    eos_token_id: int,
    generation_step: int,
    text_context_steps: int,
    policy: StreamingEosPolicy,
) -> TerminationReason | None:
    """Classify termination after sampling the next codec token."""

    if int(sampled_token_id) == int(eos_token_id):
        return "natural_eos"
    if post_text_steps(generation_step, text_context_steps) >= policy.force_after_steps:
        return "forced_eos"
    return None


def termination_metadata(
    *,
    reason: TerminationReason,
    generated_steps: int,
    generation_step: int,
    text_context_steps: int,
    eos_bias_applied: float,
    policy: StreamingEosPolicy,
) -> dict[str, object]:
    """Build consistent final-chunk diagnostics for both decoder paths."""

    return {
        "termination_reason": reason,
        "generated_steps": max(0, int(generated_steps)),
        "generation_step": max(0, int(generation_step)),
        "text_context_steps": max(0, int(text_context_steps)),
        "post_text_steps": post_text_steps(generation_step, text_context_steps),
        "eos_bias_applied": float(eos_bias_applied),
        "eos_bias_start_steps": policy.bias_start_steps,
        "eos_force_after_steps": policy.force_after_steps,
    }
