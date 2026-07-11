from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch

from app.providers.vendor.faster_qwen3_tts import streaming
from app.providers.vendor.faster_qwen3_tts.termination import (
    StreamingEosPolicy,
    classify_after_sample,
    eos_logit_bias,
)


class _Predictor:
    def __init__(self, vocab_size: int, hidden_size: int) -> None:
        self._embeddings = [torch.nn.Embedding(vocab_size, hidden_size)]

    def get_input_embeddings(self):
        return self._embeddings


class _ZeroHead(torch.nn.Module):
    def __init__(self, hidden_size: int, vocab_size: int) -> None:
        super().__init__()
        self.hidden_size = hidden_size
        self.vocab_size = vocab_size

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        return torch.zeros(
            *hidden_states.shape[:-1],
            self.vocab_size,
            dtype=hidden_states.dtype,
            device=hidden_states.device,
        )


class _FastTalker:
    def __init__(self, vocab_size: int = 32, hidden_size: int = 4) -> None:
        self.code_predictor = _Predictor(vocab_size, hidden_size)
        self._embedding = torch.nn.Embedding(vocab_size, hidden_size)
        self.codec_head = _ZeroHead(hidden_size, vocab_size)
        self.rope_deltas = None
        self.hidden_size = hidden_size
        self.vocab_size = vocab_size

    def get_input_embeddings(self):
        return self._embedding

    def forward(self, **_kwargs):
        return SimpleNamespace(
            past_key_values=(),
            past_hidden=torch.zeros(1, 1, self.hidden_size),
            generation_step=0,
            logits=torch.zeros(1, 1, self.vocab_size),
        )


class _PredictorGraph:
    def run(self, _inputs: torch.Tensor) -> torch.Tensor:
        return torch.tensor([1], dtype=torch.long)


class _TalkerGraph:
    max_seq_len = 128

    def prefill_kv(self, _past_key_values) -> int:
        return 1

    def set_generation_state(self, _attention_mask, _rope_deltas) -> None:
        return None

    def run(self, _inputs: torch.Tensor, *, position: int) -> torch.Tensor:
        assert position >= 1
        return torch.zeros(1, 1, 4)


class _ParityTalker:
    def __init__(self, vocab_size: int = 32, hidden_size: int = 4) -> None:
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size

    def forward(self, **kwargs):
        generation_step = kwargs.get("generation_step")
        if generation_step is None:
            return SimpleNamespace(
                past_key_values=(),
                past_hidden=torch.zeros(1, 1, self.hidden_size),
                generation_step=0,
                logits=torch.zeros(1, 1, self.vocab_size),
            )
        return SimpleNamespace(
            hidden_states=(None, torch.tensor([[1, 1]], dtype=torch.long)),
            past_key_values=(),
            past_hidden=torch.zeros(1, 1, self.hidden_size),
            generation_step=int(generation_step) + 1,
            logits=torch.zeros(1, 1, self.vocab_size),
        )


def _inputs(text_context_steps: int = 1):
    return {
        "talker_input_embeds": torch.zeros(1, 1, 4),
        "attention_mask": torch.ones(1, 1, dtype=torch.long),
        "trailing_text_hiddens": torch.zeros(1, text_context_steps, 4),
        "tts_pad_embed": torch.zeros(1, 1, 4),
        "config": SimpleNamespace(
            codec_eos_token_id=31,
            vocab_size=32,
            num_code_groups=2,
        ),
    }


def _constant_sampler(token_id: int):
    def sample(_logits, **_kwargs):
        return torch.tensor([token_id], dtype=torch.long)

    return sample


def _sequence_sampler(*token_ids: int):
    values = iter(token_ids)

    def sample(_logits, **_kwargs):
        return torch.tensor([next(values)], dtype=torch.long)

    return sample


def test_eos_policy_biases_then_forces_after_text_context() -> None:
    policy = StreamingEosPolicy(
        bias_start_steps=2,
        force_after_steps=4,
        bias_per_step=1.5,
    )

    assert eos_logit_bias(2, 1, policy) == 0.0
    assert eos_logit_bias(3, 1, policy) == 1.5
    assert eos_logit_bias(4, 1, policy) == 3.0
    assert classify_after_sample(
        sampled_token_id=7,
        eos_token_id=31,
        generation_step=5,
        text_context_steps=1,
        policy=policy,
    ) == "forced_eos"


def test_natural_eos_wins_at_the_forced_boundary() -> None:
    policy = StreamingEosPolicy(force_after_steps=4)

    assert classify_after_sample(
        sampled_token_id=31,
        eos_token_id=31,
        generation_step=5,
        text_context_steps=1,
        policy=policy,
    ) == "natural_eos"


def test_fast_stream_marks_natural_eos_on_exact_chunk_boundary(monkeypatch) -> None:
    monkeypatch.setattr(streaming.torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(streaming, "sample_logits", _sequence_sampler(1, 31))

    chunks = list(
        streaming.fast_generate_streaming(
            talker=_FastTalker(),
            predictor_graph=_PredictorGraph(),
            talker_graph=_TalkerGraph(),
            max_new_tokens=20,
            min_new_tokens=0,
            chunk_size=1,
            **_inputs(),
        )
    )

    assert len(chunks) == 1
    codec_chunk, timing = chunks[0]
    assert codec_chunk.shape == (1, 2)
    assert timing["is_final"] is True
    assert timing["termination_reason"] == "natural_eos"
    assert timing["generated_steps"] == 1


def test_fast_stream_forces_eos_after_bounded_post_text_grace(monkeypatch) -> None:
    monkeypatch.setattr(streaming.torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(streaming, "sample_logits", _constant_sampler(1))

    chunks = list(
        streaming.fast_generate_streaming(
            talker=_FastTalker(),
            predictor_graph=_PredictorGraph(),
            talker_graph=_TalkerGraph(),
            max_new_tokens=20,
            min_new_tokens=0,
            chunk_size=2,
            eos_bias_start_steps=2,
            eos_force_after_steps=4,
            eos_bias_per_step=2.0,
            **_inputs(text_context_steps=1),
        )
    )

    assert [chunk.shape[0] for chunk, _timing in chunks] == [2, 2, 1]
    final_timing = chunks[-1][1]
    assert final_timing["is_final"] is True
    assert final_timing["termination_reason"] == "forced_eos"
    assert final_timing["generated_steps"] == 5
    assert final_timing["post_text_steps"] == 4
    assert final_timing["eos_bias_applied"] == pytest.approx(4.0)


def test_fast_stream_marks_token_limit_on_exact_chunk_boundary(monkeypatch) -> None:
    monkeypatch.setattr(streaming.torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(streaming, "sample_logits", _constant_sampler(1))

    chunks = list(
        streaming.fast_generate_streaming(
            talker=_FastTalker(),
            predictor_graph=_PredictorGraph(),
            talker_graph=_TalkerGraph(),
            max_new_tokens=2,
            min_new_tokens=0,
            chunk_size=2,
            eos_force_after_steps=8,
            **_inputs(text_context_steps=100),
        )
    )

    assert len(chunks) == 1
    assert chunks[0][1]["is_final"] is True
    assert chunks[0][1]["termination_reason"] == "token_limit"


def test_parity_stream_uses_the_same_forced_eos_policy(monkeypatch) -> None:
    monkeypatch.setattr(streaming.torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(streaming, "sample_logits", _constant_sampler(1))

    chunks = list(
        streaming.parity_generate_streaming(
            talker=_ParityTalker(),
            max_new_tokens=20,
            min_new_tokens=0,
            chunk_size=2,
            eos_bias_start_steps=2,
            eos_force_after_steps=4,
            eos_bias_per_step=2.0,
            **_inputs(text_context_steps=1),
        )
    )

    final_timing = chunks[-1][1]
    assert final_timing["is_final"] is True
    assert final_timing["termination_reason"] == "forced_eos"
    assert final_timing["post_text_steps"] == 4
