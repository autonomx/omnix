"""Shared TTS stream compatibility module."""
from __future__ import annotations

from . import tts_stream_contract as _contract

DEFAULT_SAMPLE_RATE = _contract.DEFAULT_SAMPLE_RATE
TtsStreamRequest = _contract.TtsStreamRequest
estimate_chat_stream_max_new_tokens = _contract.estimate_chat_stream_max_new_tokens
_audio_chunk_to_pcm16_bytes = _contract.audio_chunk_to_pcm16_bytes
_stream_pcm16_blocks = _contract.stream_pcm16_blocks
