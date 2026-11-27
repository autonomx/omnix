"""A story's voices on PostgreSQL (Storyteller roadmap ST-4.1, ST-4.2): the cast, the writer's choice, re-casting,
speech plans with an unknown speaker flagged, the sentence cache, and one account kept from another's."""
from __future__ import annotations

import os

import pytest

from tests.persistence.test_row_level_security import _as_probe, probe_role  # noqa: F401 (fixture)
from tests.story.test_story_projects_postgres import _as, two_accounts  # noqa: F401 (fixture)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="PostgreSQL integration tests need OMNIX_TEST_DATABASE_URL",
    ),
]

VOICES = [
    {"voice_id": "v-warm", "name": "Warm", "description": "warm gentle narrator storyteller", "revision": "r1"},
    {"voice_id": "v-gravel", "name": "Gravel", "description": "deep gravel old sailor", "revision": "r1"},
    {"voice_id": "v-bright", "name": "Bright", "description": "bright young child", "revision": "r1"},
]


@pytest.fixture
def castable(monkeypatch):
    """The castable voices, as the voice library would list them; the list can change mid-test."""
    from app.apps.story import voices as story_voices
    from app.platform.voice import speech_service, voice_casting

    voices = [dict(row) for row in VOICES]
    monkeypatch.setattr(voice_casting, "castable_voices", lambda: voices)
    monkeypatch.setattr(story_voices, "castable_voices", lambda: voices)
    monkeypatch.setattr(speech_service, "castable_voices", lambda: voices)
    return voices


@pytest.fixture
def story(two_accounts, castable, monkeypatch):  # noqa: F811
    from app.apps.story import routes, service
    from app.apps.story.contracts import StoryPageCreate, StoryProjectCreate

    database, account, other = two_accounts
    monkeypatch.setattr(routes, "default_database", lambda: database)
    with _as(account):
        project = service.create_project(database, account, StoryProjectCreate(premise="p", mode="interactive"))
        service.replace_characters(database, account, project.id, [
            {"id": "mara", "name": "Mara", "role": "sailor", "description": "old and deep voiced"},
            {"id": "pip", "name": "Pip", "description": "a bright young child"}])
        page = routes.append_story_page(project.id, StoryPageCreate(blocks=[
            {"kind": "narration", "text": "Dusk fell. The tide turned."},
            {"kind": "dialogue", "speaker_id": "mara", "text": "“Who goes there?”"},
            {"kind": "dialogue", "speaker_id": "ghost", "text": "“Only me.”"},
            {"kind": "narration", "text": "   "}]))
    return database, account, other, project.id, page.pages[-1].id


def _cast(body):
    return {row.speaker_id: row for row in body.cast}


def test_a_project_is_cast_by_description_the_same_every_time(story):
    from app.apps.story import routes

    _, account, _, project_id, _ = story
    with _as(account):
        first = _cast(routes.get_story_voices(project_id))
        again = _cast(routes.get_story_voices(project_id))
    assert list(first) == ["narrator", "mara", "pip"]
    assert {speaker: row.voice_id for speaker, row in first.items()} == {
        "narrator": "v-warm", "mara": "v-gravel", "pip": "v-bright"}
    assert {row.chosen_by for row in first.values()} == {"auto"}
    assert {speaker: row.voice_id for speaker, row in again.items()} == {
        speaker: row.voice_id for speaker, row in first.items()}


def test_the_writers_choice_wins_and_a_voice_not_castable_is_refused(story):
    from fastapi import HTTPException

    from app.apps.story import routes
    from app.apps.story.contracts import StoryVoiceChoice

    _, account, _, project_id, _ = story
    with _as(account):
        routes.get_story_voices(project_id)
        chosen = _cast(routes.choose_story_voice(project_id, "pip", StoryVoiceChoice(voice_id="v-gravel")))
        assert (chosen["pip"].voice_id, chosen["pip"].chosen_by) == ("v-gravel", "writer")
        assert _cast(routes.get_story_voices(project_id))["pip"].voice_id == "v-gravel"
        for speaker, voice, status in (("pip", "not-on-the-list", 422), ("nobody", "v-warm", 404)):
            with pytest.raises(HTTPException) as refused:
                routes.choose_story_voice(project_id, speaker, StoryVoiceChoice(voice_id=voice))
            assert refused.value.status_code == status


def test_a_voice_whose_recording_changed_or_went_is_cast_again(story, castable):
    from app.apps.story import routes
    from app.apps.story.contracts import StoryVoiceChoice

    _, account, _, project_id, _ = story
    with _as(account):
        routes.choose_story_voice(project_id, "pip", StoryVoiceChoice(voice_id="v-gravel"))
        castable[1]["revision"] = "r2"  # v-gravel was re-recorded
        cast = _cast(routes.get_story_voices(project_id))
        assert cast["pip"].voice_revision == "r2" or cast["pip"].voice_id != "v-gravel"
        assert cast["pip"].chosen_by == "auto"
        castable[:] = [row for row in castable if row["voice_id"] != "v-bright"]
        cast = _cast(routes.get_story_voices(project_id))
    assert {row.voice_id for row in cast.values()} <= {"v-warm", "v-gravel"}


def test_a_page_is_planned_block_by_block_and_an_unknown_speaker_is_flagged(story):
    from app.apps.story import routes
    from app.apps.story.contracts import StorySpeechPlanRequest

    _, account, _, project_id, page_id = story
    with _as(account):
        plan = routes.plan_story_speech(project_id, StorySpeechPlanRequest(page_id=page_id))
    assert [(row.block_index, row.speaker_id, row.voice_id, row.unknown_speaker) for row in plan.segments] == [
        (0, "narrator", "v-warm", False), (1, "mara", "v-gravel", False), (2, "ghost", "v-bright", True)]
    assert plan.segments[0].sentences == ["Dusk fell.", "The tide turned."]


def _stream(spoken: list):
    def stream(text: str, *, speaker: str, generation: dict):
        spoken.append((text, speaker))
        yield b"\x00\x01" * 120, 24000
        yield b"\x02\x03" * 120, 24000

    return stream


def _body(response) -> bytes:
    if hasattr(response, "body_iterator"):
        import asyncio

        async def drain():
            return b"".join([piece async for piece in response.body_iterator])

        return asyncio.run(drain())
    return response.body


def test_a_sentence_is_spoken_once_then_plays_from_the_projects_audio(story, monkeypatch):
    from app.apps.story import routes
    from app.apps.story.contracts import StorySpeechSentence
    from app.providers import tts_service

    spoken: list = []
    monkeypatch.setattr(tts_service, "stream_audio_pcm16", _stream(spoken))
    _, account, _, project_id, page_id = story
    sentence = StorySpeechSentence(page_id=page_id, speaker_id="mara", text="“Who goes there?”")
    with _as(account):
        first = routes.speak_story_sentence(project_id, sentence)
        assert first.headers["X-Omnix-Speech-Cache"] == "miss"
        heard = _body(first)
        second = routes.speak_story_sentence(project_id, sentence)
        unknown = routes.speak_story_sentence(project_id, sentence.model_copy(update={"speaker_id": ""}))
        _body(unknown)
    assert second.headers["X-Omnix-Speech-Cache"] == "hit"
    assert _body(second) == heard == b"\x00\x01" * 120 + b"\x02\x03" * 120
    assert spoken == [("“Who goes there?”", "v-gravel"), ("“Who goes there?”", "v-bright")]


def test_a_sentence_for_a_page_not_in_the_project_is_refused(story, monkeypatch):
    from fastapi import HTTPException

    from app.apps.story import routes
    from app.apps.story.contracts import StorySpeechSentence
    from app.providers import tts_service

    spoken: list = []
    monkeypatch.setattr(tts_service, "stream_audio_pcm16", _stream(spoken))
    _, account, _, project_id, _ = story
    with _as(account), pytest.raises(HTTPException) as refused:
        routes.speak_story_sentence(project_id, StorySpeechSentence(page_id="not-a-page", text="Dusk fell."))
    assert (refused.value.status_code, refused.value.detail) == (404, "story_page_not_found")
    assert spoken == []


def test_a_speech_service_down_is_a_503_and_nothing_is_kept(story, monkeypatch):
    from fastapi import HTTPException

    from app.apps.story import routes
    from app.apps.story.contracts import StorySpeechSentence
    from app.providers import tts_service

    def down(text, *, speaker, generation):
        raise ConnectionError("down")
        yield  # pragma: no cover

    monkeypatch.setattr(tts_service, "stream_audio_pcm16", down)
    _, account, _, project_id, page_id = story
    with _as(account), pytest.raises(HTTPException) as refused:
        routes.speak_story_sentence(project_id, StorySpeechSentence(page_id=page_id, text="Dusk fell."))
    assert refused.value.status_code == 503


def test_one_account_cannot_read_or_change_anothers_voices_or_audio(story, probe_role, monkeypatch):  # noqa: F811
    from fastapi import HTTPException

    from app.apps.story import routes
    from app.apps.story.contracts import StorySpeechPlanRequest, StorySpeechSentence, StoryVoiceChoice
    from app.providers import tts_service

    monkeypatch.setattr(tts_service, "stream_audio_pcm16", _stream([]))
    database, account, other, project_id, page_id = story
    sentence = StorySpeechSentence(page_id=page_id, text="Dusk fell.")
    with _as(account):
        routes.get_story_voices(project_id)
        _body(routes.speak_story_sentence(project_id, sentence))
    with _as(other):
        for call in (lambda: routes.get_story_voices(project_id),
                     lambda: routes.choose_story_voice(project_id, "pip", StoryVoiceChoice(voice_id="v-warm")),
                     lambda: routes.plan_story_speech(project_id, StorySpeechPlanRequest(page_id=page_id)),
                     lambda: routes.speak_story_sentence(project_id, sentence)):
            with pytest.raises(HTTPException) as refused:
                call()
            assert refused.value.status_code == 404
    seen = {}
    for workspace_id in (account.workspace_id, other.workspace_id):
        # A runtime-like role, no workspace filter: only the policies keep A's rows from B.
        with _as_probe(workspace_id) as connection:
            seen[workspace_id] = [connection.execute(f"SELECT count(*) FROM {table} WHERE project_id = %s",
                                                     (project_id,)).fetchone()[0]
                                  for table in ("omnix_story_voice_cast", "omnix_story_speech_audio")]
    assert seen == {account.workspace_id: [3, 1], other.workspace_id: [0, 0]}
    with _as(account):
        assert _cast(routes.get_story_voices(project_id))["pip"].chosen_by == "auto"
