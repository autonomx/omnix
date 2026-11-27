"""Speak tagged lines with a cast (Storyteller roadmap ST-4.1, from the RPG's EV-13 transport).

One service for every app whose text has speakers: a plan says which voice speaks each block, sentence by
sentence (``split_sentences``, 240 characters), and each sentence is then asked for on its own and streamed as
PCM16 while it is synthesized. A sentence is kept only when it is whole and ended on its own (one that ran into
its token budget is a model failure), in the app's own cache (``SpeechCache``), and plays from there afterwards.
A device busy for a moment is tried once more; a service down is a 503, and the text stands, silent.

The policy for a speaker with no voice is the app's: the RPG speaks them in the narrator's voice, Storyteller in
a neutral voice (``neutral_voice``) and flags the line (``speech_plan``'s ``unknown_voice``).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Protocol

from fastapi import HTTPException, Response
from fastapi.responses import StreamingResponse

from app.conversation.tts_stream_contract import CHAT_STREAM_MIN_REPETITION_PENALTY

from .voice_casting import DEFAULT_VOICE, as_wav, castable_voices, pcm_of, render_key, split_sentences

logger = logging.getLogger(__name__)
# A sentence is streamed as live speech streams it: the CUDA-graph decode (the parity decode runs slower than real
# time on a 4090), in chunks as the read-aloud player takes them, with live chat's least repetition penalty and, per
# sentence, its token budget. Part of the audio's identity in each app's cache.
SPEECH_GENERATION: dict[str, Any] = {"chunk_size": 8, "parity_mode": False,
                                     "repetition_penalty": CHAT_STREAM_MIN_REPETITION_PENALTY}
PCM16 = "application/x-omnix-pcm16"  # mono little-endian 16-bit samples, at ``X-Omnix-Sample-Rate``
CODEC_STEPS_PER_SECOND = 12.5  # the Qwen3-TTS tokenizer's: one codec step per 80 ms of audio
RUNAWAY_FRACTION = 0.95  # audio this close to its budget ran into the cap instead of ending (as audiobook's check)
SENTENCE_MAX_CHARS = 300  # what one speech-audio request may carry: a sentence of a plan, no more


class SpeechCache(Protocol):
    """Where an app keeps its spoken sentences, by render key: in its own table, in the reader's workspace."""

    def get(self, key: str) -> bytes | None:
        """The sentence's WAV, or None."""

    def put(self, key: str, *, voice_id: str, audio: bytes) -> None:
        """Keep a whole sentence's WAV."""


def neutral_voice(voices: list[dict[str, Any]], narrator_voice: str) -> str:
    """The voice for a line whose speaker is not known: a castable voice other than the narrator's (the first by
    id), the narrator's when it is the only one, the service's own when none is castable."""
    others = sorted(row["voice_id"] for row in voices if row["voice_id"] != narrator_voice)
    return others[0] if others else (narrator_voice or DEFAULT_VOICE)


def speech_plan(voices: Mapping[str, str], blocks: Iterable[tuple[str, str]], *,
                unknown_voice: str) -> list[dict[str, Any]]:
    """Each block (speaker id, text) as it is spoken: in its speaker's voice, or ``unknown_voice`` for a speaker
    with none (the app's policy), sentence by sentence."""
    return [{"speaker_id": speaker_id, "voice_id": voices.get(speaker_id) or unknown_voice or DEFAULT_VOICE,
             "sentences": split_sentences(text)} for speaker_id, text in blocks]


def sentence_key(text: str, voice: str) -> str:
    """A sentence's render identity: its text, the voice as it is now (its recording's revision), and the service
    that speaks it."""
    from app.providers.service import selected_tts_provider_id
    from app.runtime.config import get_runtime_config

    revision = next((item["revision"] for item in castable_voices() if item["voice_id"] == voice), "")
    runtime = get_runtime_config()
    return render_key(text, voice_id=voice, revision=revision, provider=selected_tts_provider_id(),
                      model=runtime.tts.url if runtime.tts else "", parameters=SPEECH_GENERATION)


def _first_piece(text: str, voice: str, generation: dict[str, Any]) -> tuple[Any, bytes, int]:
    """The sentence's stream and its first piece, before the answer starts: a service down is a 503, not a silent
    stream; a device busy for a moment (live speech or an audiobook on it) is tried once more after it says."""
    from app.providers import tts_service
    from app.providers.qwen_http_gateway import TtsServiceSaturated

    for attempt in (1, 2):
        pieces = tts_service.stream_audio_pcm16(text, speaker=voice, generation=generation)
        try:
            first, rate = next(pieces)
            return pieces, first, rate
        except TtsServiceSaturated as busy:
            pieces.close()
            if attempt == 1:
                time.sleep(min(3.0, float(busy.retry_after or 1)))
                continue
        except Exception:  # StopIteration included: no audio at all
            pieces.close()
        break
    raise HTTPException(status_code=503, detail={"ok": False, "error": "speech_unavailable"})


def speak_sentence(text: str, voice: str, key: str, cache: SpeechCache, *, label: str) -> Response:
    """A sentence in ``voice`` as PCM16 (``PCM16``): from ``cache``, else streamed from the speech service as it is
    synthesized and kept once it is whole. ``label`` names the sentence's owner in the logs."""
    from app.conversation.tts_stream_contract import estimate_chat_stream_max_new_tokens

    cached = cache.get(key)
    if cached is not None:
        pcm, rate = pcm_of(cached)
        return Response(content=pcm, media_type=PCM16,
                        headers={"X-Omnix-Speech-Cache": "hit", "X-Omnix-Sample-Rate": str(rate)})
    budget = estimate_chat_stream_max_new_tokens(text)  # a model that fails to stop is cut off
    pieces, first, rate = _first_piece(text, voice, {**SPEECH_GENERATION, "max_new_tokens": budget})

    def spoken() -> Iterator[bytes]:
        heard = [first]
        try:
            yield first
            for piece, _ in pieces:
                heard.append(piece)
                yield piece
        except Exception:  # the stream broke: what was heard stands, and nothing is kept
            logger.warning("speech_stream_failed %s", label, exc_info=True)
            return
        finally:
            pieces.close()
        audio = b"".join(heard)
        if len(audio) / 2 / rate >= RUNAWAY_FRACTION * budget / CODEC_STEPS_PER_SECOND:
            # It ran out its budget instead of ending on its own: a model failure, not this sentence's audio.
            logger.warning("speech_ran_out_its_budget %s chars=%s", label, len(text))
            return
        try:  # whole: kept, and played from the cache from now on
            cache.put(key, voice_id=voice, audio=as_wav(audio, sample_rate=rate))
        except Exception:  # the audio has been heard; not keeping it only costs a later synthesis
            logger.warning("speech_not_kept %s", label, exc_info=True)

    return StreamingResponse(spoken(), media_type=PCM16,
                             headers={"X-Omnix-Speech-Cache": "miss", "X-Omnix-Sample-Rate": str(rate)})


__all__ = [
    "CODEC_STEPS_PER_SECOND", "PCM16", "RUNAWAY_FRACTION", "SENTENCE_MAX_CHARS", "SPEECH_GENERATION", "SpeechCache",
    "neutral_voice", "sentence_key", "speak_sentence", "speech_plan",
]
