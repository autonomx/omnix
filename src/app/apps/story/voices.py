"""A story's voices (Storyteller roadmap ST-4.1, ST-4.2): its cast, its speech plans and its spoken sentences.

The narrator and each character get a castable voice, matched to the character's role, description and traits by
the shared matcher (``match_voices``), ties broken by a draw seeded by the project and the speaker, so a project
casts the same every time. The writer may choose any voice in the library for anyone, castable or not, and their
choice wins while its recording is unchanged. A voice given automatically that is no longer castable, or any voice
whose recording changed, is cast again.

A page is spoken block by block in its speakers' voices through the shared speech service. A line whose speaker is
not in the cast is spoken in a neutral voice (a castable voice other than the narrator's) and flagged in the plan.
"""
from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from typing import Any

from fastapi import Response

from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work
from app.platform.voice.contracts import (
    DEFAULT_VOICE,
    library_voices,
    match_voices,
    neutral_voice,
    sentence_key,
    speak_sentence,
)
from app.platform.voice.contracts import speech_plan as plan

from .contracts import StoryCastVoice, StorySpeechPlan, StorySpeechSegment, StoryVoiceCast, StoryVoiceOption
from .repository import PostgresStoryRepository
from .service import StoryNotFound, _require

NARRATOR = "narrator"


def _tie_break(project_id: str) -> Callable[[str], Callable[[], float]]:
    def draws(speaker_id: str) -> Callable[[], float]:
        seed = hashlib.sha256(f"story-voice:{project_id}:{speaker_id}".encode("utf-8")).digest()
        return random.Random(int.from_bytes(seed[:8], "big")).random

    return draws


def _speakers(repository: PostgresStoryRepository, context: TenantContext, project_id: str) -> list[dict[str, str]]:
    """The narrator, then each character, with the words their voice is matched by."""
    found = [{"speaker_id": NARRATOR, "name": "The narrator", "lore": "storyteller narrator"}]
    for character in repository.characters(context, project_id):
        traits = " ".join(str(trait) for trait in character.get("traits") or [])
        found.append({"speaker_id": character["id"], "name": character["name"],
                      "lore": f"{character.get('role', '')} {character.get('description', '')} {traits}"})
    return found


def _castable(voices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The library's voices that may be given to a part automatically."""
    return [row for row in voices if row["castable"]]


def _cast(repository: PostgresStoryRepository, context: TenantContext, project_id: str,
          voices: list[dict[str, Any]]) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    """The project's speakers and their voices (``voices`` is the library), casting anyone not cast yet, anyone whose
    voice went or changed, and anyone given a voice automatically that is no longer castable."""
    revisions = {row["voice_id"]: row["revision"] for row in voices}
    castable = _castable(voices)
    people = _speakers(repository, context, project_id)
    stored = repository.voice_cast(context, project_id)
    cast = {speaker: row for speaker, row in stored.items()
            if revisions.get(row["voice_id"]) == row["voice_revision"]
            and (row["chosen_by"] == "writer" or any(voice["voice_id"] == row["voice_id"] for voice in castable))}
    for speaker, row in match_voices(people, castable, cast, _tie_break(project_id)).items():
        # Only a stale row is replaced over the writer's choice; a speaker with no row yet takes the match
        # unless the writer chose a voice for them meanwhile.
        repository.put_voice(context, project_id, speaker, **row, replace=speaker in stored)
        cast[speaker] = row
    if set(cast) - set(stored):
        cast.update({speaker: row for speaker, row in repository.voice_cast(context, project_id).items()
                     if speaker in cast and speaker not in stored})
    return people, cast


def _response(project_id: str, people: list[dict[str, str]], cast: dict[str, dict[str, str]],
              voices: list[dict[str, Any]]) -> StoryVoiceCast:
    return StoryVoiceCast(
        project_id=project_id,
        cast=[StoryCastVoice(speaker_id=person["speaker_id"], name=person["name"], **cast.get(person["speaker_id"], {}))
              for person in people],
        voices=[StoryVoiceOption(voice_id=row["voice_id"], name=row["name"], description=row["description"],
                                 castable=row["castable"]) for row in voices],
    )


def voice_cast(database: Any, context: TenantContext, project_id: str) -> StoryVoiceCast:
    voices = library_voices()
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, live=False)
        people, cast = _cast(repository, context, project_id, voices)
        work.commit()
    return _response(project_id, people, cast, voices)


class VoiceNotCastable(ValueError):
    pass


def choose_voice(database: Any, context: TenantContext, project_id: str, speaker_id: str,
                 voice_id: str) -> StoryVoiceCast:
    """The writer's choice of any library voice for the narrator or a character."""
    voices = library_voices()
    voice = next((row for row in voices if row["voice_id"] == voice_id), None)
    if voice is None:
        raise VoiceNotCastable("voice_not_castable")
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id)
        if speaker_id not in {person["speaker_id"] for person in _speakers(repository, context, project_id)}:
            work.rollback()
            raise StoryNotFound("story_speaker_not_found")
        repository.put_voice(context, project_id, speaker_id, voice_id=voice_id, voice_revision=voice["revision"],
                             chosen_by="writer")
        people, cast = _cast(repository, context, project_id, voices)
        work.commit()
    return _response(project_id, people, cast, voices)


def _voices_of(people: list[dict[str, str]], cast: dict[str, dict[str, str]],
               voices: list[dict[str, Any]]) -> tuple[dict[str, str], str]:
    """Each speaker's voice (the service's own while nothing is castable), and the neutral voice for a line whose
    speaker is not in the cast (a castable one: it is given, not chosen)."""
    by_speaker = {person["speaker_id"]: (cast.get(person["speaker_id"]) or {}).get("voice_id") or DEFAULT_VOICE
                  for person in people}
    return by_speaker, neutral_voice(_castable(voices), by_speaker[NARRATOR])


def _block_speaker(block: dict[str, Any]) -> str:
    return NARRATOR if block.get("kind") != "dialogue" else str(block.get("speaker_id") or "")


def speech_plan(database: Any, context: TenantContext, project_id: str, page_id: str) -> StorySpeechPlan:
    """How a page is spoken: only its blocks, each in its speaker's voice, sentence by sentence."""
    voices = library_voices()
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, live=False)
        page = next((row for row in repository.pages(context, project_id) if row["id"] == page_id), None)
        if page is None:
            work.rollback()
            raise StoryNotFound("story_page_not_found")
        people, cast = _cast(repository, context, project_id, voices)
        work.commit()
    by_speaker, neutral = _voices_of(people, cast, voices)
    blocks = [(index, block) for index, block in enumerate(page["blocks"] or []) if str(block.get("text") or "").strip()]
    segments = plan(by_speaker, [(_block_speaker(block), str(block["text"])) for _, block in blocks],
                    unknown_voice=neutral)
    return StorySpeechPlan(project_id=project_id, page_id=page_id, segments=[
        StorySpeechSegment(block_index=index, unknown_speaker=segment["speaker_id"] not in by_speaker, **segment)
        for (index, _), segment in zip(blocks, segments)])


class _ProjectSpeechCache:
    """The project's spoken sentences (``omnix_story_speech_audio``), for the shared speech service."""

    def __init__(self, database: Any, context: TenantContext, project_id: str, page_id: str) -> None:
        self.database, self.context, self.project_id, self.page_id = database, context, project_id, page_id

    def get(self, key: str) -> bytes | None:
        with unit_of_work(self.database) as work:
            audio = PostgresStoryRepository(work.connection).speech_audio(self.context, self.project_id, key)
            work.rollback()
        return audio

    def put(self, key: str, *, voice_id: str, audio: bytes) -> None:
        with unit_of_work(self.database) as work:
            PostgresStoryRepository(work.connection).put_speech_audio(
                self.context, self.project_id, key, page_id=self.page_id, voice_id=voice_id, audio=audio)
            work.commit()


def speak(database: Any, context: TenantContext, project_id: str, *, page_id: str, speaker_id: str,
          text: str) -> Response:
    """A sentence of a page in its speaker's voice (the neutral voice for a speaker with none), as PCM16."""
    voices = library_voices()
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, live=False)
        if not any(row["id"] == page_id for row in repository.pages(context, project_id)):
            work.rollback()
            raise StoryNotFound("story_page_not_found")
        people, cast = _cast(repository, context, project_id, voices)
        work.commit()
    by_speaker, neutral = _voices_of(people, cast, voices)
    voice = by_speaker.get(speaker_id) or neutral
    return speak_sentence(text, voice, sentence_key(text, voice),
                          _ProjectSpeechCache(database, context, project_id, page_id),
                          label=f"story project={project_id}")


__all__ = ["NARRATOR", "VoiceNotCastable", "choose_voice", "speak", "speech_plan", "voice_cast"]
