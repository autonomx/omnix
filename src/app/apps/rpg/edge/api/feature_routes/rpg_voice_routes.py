"""A campaign's voices (evolution roadmap EV-13): its cast, and the player's choice of a voice for a speaker.

Reading the cast casts anyone first heard or met since, in the campaign's voice cast (outside its document): no turn,
no model call. Only castable voices are cast or offered.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.edge.api.web_contracts import documented
from app.apps.rpg.edge.api.web_contracts_voice import RpgSpeechPlanResponse, RpgVoiceCastResponse

_ROUTE_SENTINEL = "_omnix_rpg_voice_routes_registered"


class _CampaignSpeechCache:
    """The campaign's spoken sentences (``omnix_rpg_speech_audio``), for the shared speech service."""

    def __init__(self, database: Any, context: Any, campaign_id: str) -> None:
        self.database, self.context, self.campaign_id = database, context, campaign_id

    def get(self, key: str) -> bytes | None:
        from app.persistence.unit_of_work import unit_of_work

        with unit_of_work(self.database) as work:
            cached = work.rpg_speech_audio.get(self.context, self.campaign_id, key)
            work.commit()
        return cached[0] if cached is not None else None

    def put(self, key: str, *, voice_id: str, audio: bytes) -> None:
        from app.persistence.unit_of_work import unit_of_work

        with unit_of_work(self.database) as work:
            work.rpg_speech_audio.put(self.context, self.campaign_id, key, voice_id=voice_id, audio=audio)
            work.commit()


class RpgSpeechBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speaker_id: str = Field(default="narrator", max_length=200)
    text: str = Field(min_length=1, max_length=8000)


class RpgSpeechSentence(RpgSpeechBlock):
    text: str = Field(min_length=1, max_length=300)  # one sentence of a response (``SENTENCE_MAX_CHARS``), no more


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
        from app.persistence.unit_of_work import unit_of_work
        from app.platform.voice.contracts import DEFAULT_VOICE, sentence_key, speak_sentence

        document = load_session_from_postgres(session_id)
        if document is None:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found"})
        database = _database()
        with unit_of_work(database) as work:
            context = _context(database)
            cast = {row["speaker_id"]: row for row in cast_for(work, context, session_id, document)}
            work.commit()
        row = cast.get(request_body.speaker_id) or cast.get("narrator") or {}
        voice = row.get("voice_id") or DEFAULT_VOICE
        return speak_sentence(request_body.text, voice, sentence_key(request_body.text, voice),
                              _CampaignSpeechCache(database, context, session_id), label=f"rpg session={session_id}")

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
    from app.platform.voice.contracts import DEFAULT_VOICE, speech_plan

    voices = {row["speaker_id"]: row.get("voice_id") or DEFAULT_VOICE for row in cast}
    return speech_plan(voices, [(block.speaker_id, block.text) for block in blocks],
                       unknown_voice=voices.get("narrator") or DEFAULT_VOICE)


__all__ = ["register_rpg_voice_routes"]
