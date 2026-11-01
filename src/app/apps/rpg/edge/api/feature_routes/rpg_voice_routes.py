"""A campaign's voices (evolution roadmap EV-13): its cast, and the player's choice of a voice for a speaker.

Reading the cast casts anyone first heard or met since, in the campaign's voice cast (outside its document): no turn,
no model call. Only castable voices are cast or offered.
"""
from __future__ import annotations

from typing import Any

import logging

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.edge.api.web_contracts import RpgSpeechPlanResponse, RpgVoiceCastResponse, documented
from app.conversation.tts_stream_contract import CHAT_STREAM_MIN_REPETITION_PENALTY

logger = logging.getLogger(__name__)
_ROUTE_SENTINEL = "_omnix_rpg_voice_routes_registered"
# A sentence is streamed as live speech streams it: the CUDA-graph decode (the parity decode runs slower than real
# time on a 4090), in chunks as the read-aloud player takes them, with live chat's least repetition penalty and, per
# sentence, its token budget. Part of the audio's identity in the campaign's cache.
SPEECH_GENERATION: dict[str, Any] = {"chunk_size": 8, "parity_mode": False,
                                     "repetition_penalty": CHAT_STREAM_MIN_REPETITION_PENALTY}
PCM16 = "application/x-omnix-pcm16"  # mono little-endian 16-bit samples, at ``X-Omnix-Sample-Rate``
CODEC_STEPS_PER_SECOND = 12.5  # the Qwen3-TTS tokenizer's: one codec step per 80 ms of audio
RUNAWAY_FRACTION = 0.95  # audio this close to its budget ran into the cap instead of ending (as audiobook's check)


def _first_piece(tts_service: Any, text: str, voice: str, generation: dict[str, Any]) -> tuple[Any, bytes, int]:
    """The sentence's stream and its first piece, before the answer starts: a service down is a 503, not a silent
    stream; a device busy for a moment (live speech or an audiobook on it) is tried once more after it says."""
    import time

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


class RpgSpeechBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speaker_id: str = Field(default="narrator", max_length=200)
    text: str = Field(min_length=1, max_length=8000)


class RpgSpeechSentence(RpgSpeechBlock):
    text: str = Field(min_length=1, max_length=300)  # one sentence of a response (``split_sentences``), no more


class RpgSpeechPlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[RpgSpeechBlock] = Field(min_length=1, max_length=24)


class RpgVoiceChoiceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice_id: str = Field(min_length=1, max_length=200)


def _response(work: Any, context: Any, session_id: str, document: Any) -> dict[str, Any]:
    from app.apps.rpg.session.voice_cast import cast_for
    from app.platform.voice.contracts import castable_voices

    return {"ok": True, "session_id": session_id, "cast": cast_for(work, context, session_id, document),
            "voices": [{key: row[key] for key in ("voice_id", "name", "description")} for row in castable_voices()]}


def register_rpg_voice_routes(router: APIRouter, state) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.get("/api/rpg/sessions/{session_id}/voices", tags=["rpg-session"], responses=documented(RpgVoiceCastResponse))
    def rpg_voice_cast(session_id: str) -> dict[str, Any]:
        from app.apps.rpg.session.persistence.session_records import _context, _database, load_session_from_postgres
        from app.persistence.unit_of_work import unit_of_work

        document = load_session_from_postgres(session_id)
        if document is None:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found"})
        database = _database()
        with unit_of_work(database) as work:
            payload = _response(work, _context(database), session_id, document)
            work.commit()
        return payload

    @router.post("/api/rpg/sessions/{session_id}/speech-plan", tags=["rpg-session"],
                 responses=documented(RpgSpeechPlanResponse))
    def rpg_speech_plan(session_id: str, request_body: RpgSpeechPlanBody) -> dict[str, Any]:
        """How a final response is spoken: only its shown text, block by block in each speaker's cast voice."""
        from app.apps.rpg.session.persistence.session_records import _context, _database, load_session_from_postgres
        from app.apps.rpg.session.voice_cast import cast_for
        from app.persistence.unit_of_work import unit_of_work

        document = load_session_from_postgres(session_id)
        if document is None:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found"})
        database = _database()
        with unit_of_work(database) as work:
            cast = cast_for(work, _context(database), session_id, document)
            work.commit()
        return {"ok": True, "session_id": session_id, "segments": _speech_plan(cast, request_body.blocks)}

    @router.post("/api/rpg/sessions/{session_id}/speech-audio", tags=["rpg-session"], response_class=Response)
    def rpg_speech_audio(session_id: str, request_body: RpgSpeechSentence) -> Response:
        """A sentence of a final response in its speaker's cast voice, as PCM16 (``PCM16``): from the campaign's audio
        cache, else streamed from the speech service as it is synthesized and kept once it is whole (EV-13). With the
        speech service down, 503: the text stands, silent."""
        from app.apps.rpg.session.persistence.session_records import _context, _database, load_session_from_postgres
        from app.apps.rpg.session.voice_cast import cast_for
        from app.conversation.tts_stream_contract import estimate_chat_stream_max_new_tokens
        from app.persistence.unit_of_work import unit_of_work
        from app.platform.voice.contracts import DEFAULT_VOICE, as_wav, castable_voices, pcm_of, render_key
        from app.providers import tts_service
        from app.providers.service import selected_tts_provider_id
        from app.runtime.config import get_runtime_config

        document = load_session_from_postgres(session_id)
        if document is None:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found"})
        database = _database()
        with unit_of_work(database) as work:
            context = _context(database)
            cast = {row["speaker_id"]: row for row in cast_for(work, context, session_id, document)}
            row = cast.get(request_body.speaker_id) or cast.get("narrator") or {}
            voice = row.get("voice_id") or DEFAULT_VOICE
            # The voice as it is now (its recording's revision), and the service that speaks it.
            revision = next((item["revision"] for item in castable_voices() if item["voice_id"] == voice), "")
            runtime = get_runtime_config()
            key = render_key(request_body.text, voice_id=voice, revision=revision, provider=selected_tts_provider_id(),
                             model=runtime.tts.url if runtime.tts else "", parameters=SPEECH_GENERATION)
            cached = work.rpg_speech_audio.get(context, session_id, key)
            work.commit()
        if cached is not None:
            pcm, rate = pcm_of(cached[0])
            return Response(content=pcm, media_type=PCM16,
                            headers={"X-Omnix-Speech-Cache": "hit", "X-Omnix-Sample-Rate": str(rate)})
        budget = estimate_chat_stream_max_new_tokens(request_body.text)  # a model that fails to stop is cut off
        pieces, first, rate = _first_piece(tts_service, request_body.text, voice,
                                           {**SPEECH_GENERATION, "max_new_tokens": budget})

        def spoken() -> Any:
            heard = [first]
            try:
                yield first
                for piece, _ in pieces:
                    heard.append(piece)
                    yield piece
            except Exception:  # the stream broke: what was heard stands, and nothing is kept
                logger.warning("rpg_speech_stream_failed session=%s", session_id, exc_info=True)
                return
            finally:
                pieces.close()
            audio = b"".join(heard)
            if len(audio) / 2 / rate >= RUNAWAY_FRACTION * budget / CODEC_STEPS_PER_SECOND:
                # It ran out its budget instead of ending on its own: a model failure, not this sentence's audio.
                logger.warning("rpg_speech_ran_out_its_budget session=%s chars=%s", session_id, len(request_body.text))
                return
            try:  # whole: kept, and played from the cache from now on
                with unit_of_work(database) as work:
                    work.rpg_speech_audio.put(context, session_id, key, voice_id=voice,
                                              audio=as_wav(audio, sample_rate=rate))
                    work.commit()
            except Exception:  # the audio has been heard; not keeping it only costs a later synthesis
                logger.warning("rpg_speech_not_kept session=%s", session_id, exc_info=True)

        return StreamingResponse(spoken(), media_type=PCM16,
                                 headers={"X-Omnix-Speech-Cache": "miss", "X-Omnix-Sample-Rate": str(rate)})

    @router.put("/api/rpg/sessions/{session_id}/voices/{speaker_id:path}", tags=["rpg-session"],
                responses=documented(RpgVoiceCastResponse))
    def rpg_choose_voice(session_id: str, speaker_id: str, request_body: RpgVoiceChoiceBody) -> dict[str, Any]:
        from app.apps.rpg.session.persistence.session_records import _context, _database, load_session_from_postgres
        from app.apps.rpg.session.voice_cast import choose
        from app.persistence.unit_of_work import unit_of_work

        document = load_session_from_postgres(session_id)
        if document is None:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found"})
        database = _database()
        with unit_of_work(database) as work:
            context = _context(database)
            if choose(work, context, session_id, speaker_id, request_body.voice_id, document) is None:
                work.rollback()
                raise HTTPException(status_code=422, detail={"ok": False, "error": "voice_not_castable"})
            payload = _response(work, context, session_id, document)
            work.commit()
        return payload


def _speech_plan(cast: list[dict[str, Any]], blocks: list[RpgSpeechBlock]) -> list[dict[str, Any]]:
    """A final response's blocks as they are spoken: each in its speaker's voice (the narrator's for anyone not
    cast), sentence by sentence."""
    from app.platform.voice.contracts import DEFAULT_VOICE, split_sentences

    voices = {row["speaker_id"]: row.get("voice_id") or DEFAULT_VOICE for row in cast}
    return [{"speaker_id": block.speaker_id, "voice_id": voices.get(block.speaker_id) or voices.get("narrator")
             or DEFAULT_VOICE, "sentences": split_sentences(block.text)} for block in blocks]


__all__ = ["register_rpg_voice_routes"]
