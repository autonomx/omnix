"""A campaign's voices (evolution roadmap EV-13): its cast, and the player's choice of a voice for a speaker.

Reading the cast casts anyone first heard or met since, in the campaign's voice cast (outside its document): no turn,
no model call. Only castable voices are cast or offered.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.edge.api.web_contracts import RpgVoiceCastResponse, documented

_ROUTE_SENTINEL = "_omnix_rpg_voice_routes_registered"


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
    from app.platform.voice.voice_casting import castable_voices

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

    @router.post("/api/rpg/sessions/{session_id}/speech-plan", tags=["rpg-session"])
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
        """A sentence of a final response in its speaker's cast voice, as WAV: from the campaign's audio cache, else
        synthesized once and kept (EV-13). With the speech service down, 503: the text stands, silent."""
        from app.apps.rpg.session.persistence.session_records import _context, _database, load_session_from_postgres
        from app.apps.rpg.session.voice_cast import cast_for
        from app.config.env import environment
        from app.persistence.unit_of_work import unit_of_work
        from app.platform.live_speech.tts_adapters import create_synthesizer_from_env
        from app.platform.voice.voice_casting import DEFAULT_VOICE, as_wav, castable_voices, render_key

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
            provider = environment().get("LIVE_SPEECH_TTS_PROVIDER", "fake").strip().lower()
            service = environment().get("LIVE_SPEECH_TTS_URL", "")
            key = render_key(request_body.text, voice_id=voice, revision=revision, provider=provider, model=service)
            cached = work.rpg_speech_audio.get(context, session_id, key)
            work.commit()
        if cached is not None:
            return Response(content=cached[0], media_type=cached[1], headers={"X-Omnix-Speech-Cache": "hit"})
        synthesizer = create_synthesizer_from_env()
        try:
            deltas = synthesizer.synthesize(request_body.text, voice=voice)
        except Exception:
            raise HTTPException(status_code=503, detail={"ok": False, "error": "speech_unavailable"}) from None
        if not deltas:
            raise HTTPException(status_code=503, detail={"ok": False, "error": "speech_unavailable"})
        audio = as_wav(b"".join(delta.pcm for delta in deltas), sample_rate=int(deltas[0].sample_rate))
        with unit_of_work(database) as work:
            work.rpg_speech_audio.put(_context(database), session_id, key, voice_id=voice, audio=audio)
            work.commit()
        return Response(content=audio, media_type="audio/wav", headers={"X-Omnix-Speech-Cache": "miss"})

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
    from app.platform.voice.voice_casting import DEFAULT_VOICE, split_sentences

    voices = {row["speaker_id"]: row.get("voice_id") or DEFAULT_VOICE for row in cast}
    return [{"speaker_id": block.speaker_id, "voice_id": voices.get(block.speaker_id) or voices.get("narrator")
             or DEFAULT_VOICE, "sentences": split_sentences(block.text)} for block in blocks]


__all__ = ["register_rpg_voice_routes"]
