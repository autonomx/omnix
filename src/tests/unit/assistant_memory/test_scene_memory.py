"""Characters remember each other (companion 6.6): the scene line job, what it keeps, and for whom."""
from __future__ import annotations

from typing import Any

import pytest

from app.conversation.scene import HEARD_TEXT_KEY, SPEAKER_ID_KEY, SceneMember
from app.platform.assistant_memory import scene_memory
from app.platform.assistant_memory.owner_repository import OwnerAwareInMemoryMemoryRepository
from app.platform.assistant_memory.owner_service import OwnerAwareMemoryService
from app.platform.assistant_memory.scene_memory import (
    CLAIM_CONFIDENCE,
    SCENE_LINES_DELAY_SECONDS,
    SCENE_THREAD_MARK,
    SELF_CONFIDENCE,
    create_scene_lines_job_request,
    enqueue_scene_lines_job,
    process_scene_lines_job,
)
from app.platform.assistant_memory.scope import resolve_session_memory_scope
from app.platform.assistant_memory.turn_reactions import remember_scene_line
from app.platform.chat.models import ChatMessage, ChatSession
from tests.support.in_memory_jobs import InMemoryJobStore

_AT = "2026-11-15T20:00:00+00:00"
_NAMES = {"mara": "Mara", "bea": "Bea", "theo": "Theo"}


def _member(character_id: str) -> SceneMember | None:
    name = _NAMES.get(character_id)
    return SceneMember(character_id, name) if name else None


def _line(message_id: str, speaker: str, content: str, **metadata: Any) -> ChatMessage:
    metadata[SPEAKER_ID_KEY] = speaker
    metadata.setdefault("initiative_reason", f"scene_line:{speaker}")
    return ChatMessage(id=message_id, role="assistant", content=content, created_at=_AT, metadata=metadata)


def _person(message_id: str, content: str) -> ChatMessage:
    return ChatMessage(id=message_id, role="user", content=content, created_at=_AT)


def _session(*messages: ChatMessage, **fields: Any) -> ChatSession:
    return ChatSession.model_validate({
        "id": "chat:1", "title": "Call", "created_at": _AT, "updated_at": _AT, "interaction_mode": "character",
        "character_id": "mara", "write_memory": True, "messages": list(messages), **fields,
    })


class _Chats:
    def __init__(self, session: ChatSession) -> None:
        self.session = session

    def get_session(self, session_id: str) -> ChatSession | None:
        return self.session if session_id == self.session.id else None


class _Reader:
    def __init__(self, *answers: list[dict[str, Any]]) -> None:
        self.answers = list(answers)
        self.documents: list[dict[str, Any]] = []

    def read(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        self.documents.append(document)
        return self.answers.pop(0) if self.answers else []


class _Characters:
    def character_named(self, name: str) -> str | None:
        return {"Theo": "theo"}.get(name)


def _learning(line: int, about: str, content: str, topic: str = "fear of storms", kind: str = "semantic_fact"):
    return {"line": line, "about": about, "content": content, "kind": kind, "topic": topic}


@pytest.fixture
def runtime(tmp_path, monkeypatch, request):
    monkeypatch.setattr(scene_memory, "scene_memory_enabled", lambda: True)
    store = InMemoryJobStore(tmp_path / "jobs")
    service = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository(f"scene-memory:{request.node.name}"))
    return store, service


def _run(store, service, session, message_id, reader, *, members=("mara", "bea")):
    job = enqueue_scene_lines_job(session.id, message_id, members, job_store=store)
    assert job is not None
    return process_scene_lines_job(
        job, chat_store=_Chats(session), memory_service=service, job_store=store, reader=reader,
        member=_member, characters=_Characters(),
    )


def _memories(service, session, character_id: str):
    view = session.model_copy(update={"character_id": character_id})
    return service.list_active(resolve_session_memory_scope(view))


def test_the_job_waits_a_minute_and_is_queued_once_per_line(tmp_path, monkeypatch):
    monkeypatch.setattr(scene_memory, "scene_memory_enabled", lambda: True)
    store = InMemoryJobStore(tmp_path / "jobs")
    request = create_scene_lines_job_request("chat:1", "m:2", ["mara", "bea"])
    assert request._available_after_seconds == SCENE_LINES_DELAY_SECONDS == 60
    first = enqueue_scene_lines_job("chat:1", "m:2", ["mara", "bea"], job_store=store)
    second = enqueue_scene_lines_job("chat:1", "m:2", ["mara", "bea"], job_store=store)
    assert first is not None and second is not None and first.id == second.id
    monkeypatch.setattr(scene_memory, "scene_memory_enabled", lambda: False)
    assert enqueue_scene_lines_job("chat:1", "m:3", ["mara"], job_store=store) is None


def test_the_consumer_honours_memory_writes(monkeypatch):
    calls = []
    monkeypatch.setattr(scene_memory, "enqueue_scene_lines_job", lambda *args, **kwargs: calls.append(args))
    event = {"workspace_id": "ws", "payload": {
        "session_id": "chat:1", "message_id": "m:2", "user_id": "u", "speaker_id": "bea",
        "member_ids": ["mara", "bea"], "memory_writes_allowed": False,
    }}
    assert remember_scene_line(None, event) == {"skipped": "memory_writes_off"}
    assert calls == []


def test_a_self_statement_is_kept_by_the_other_member_about_the_speaker(runtime):
    store, service = runtime
    session = _session(_person("m:1", "Tell me about storms"), _line("m:2", "bea", "I'm afraid of storms."))
    reader = _Reader([_learning(1, "Bea", "Bea is afraid of storms")])

    result = _run(store, service, session, "m:2", reader)

    [kept] = _memories(service, session, "mara")
    assert (kept.content, kept.about_character_id, kept.confidence) == ("Bea is afraid of storms", "bea",
                                                                       SELF_CONFIDENCE)
    assert (kept.trust_level, kept.provenance_type, kept.source) == ("unverified_agent", "assistant_inference",
                                                                     "assistant_suggested")
    assert _memories(service, session, "bea") == []  # nobody keeps a memory of their own line
    assert result.root_id == "m:1" and result.through_line_id == "m:2"
    assert reader.documents[0]["lines"] == [{"line": 1, "speaker": "Bea", "text": "I'm afraid of storms."}]
    assert reader.documents[0]["person_said"] == "Tell me about storms"


def test_a_claim_about_another_character_is_kept_with_lower_confidence(runtime):
    store, service = runtime
    session = _session(_person("m:1", "Hi"), _line("m:2", "bea", "Theo hates the sea, you know."))
    reader = _Reader([_learning(1, "Theo", "Bea says Theo hates the sea", topic="the sea")])

    _run(store, service, session, "m:2", reader)

    [kept] = _memories(service, session, "mara")
    assert (kept.about_character_id, kept.confidence) == ("theo", CLAIM_CONFIDENCE)


def test_nothing_about_the_person_is_kept(runtime):
    store, service = runtime
    session = _session(_person("m:1", "Hi"), _line("m:2", "bea", "You look tired today."))
    reader = _Reader([_learning(1, "the person", "The person looks tired")])

    result = _run(store, service, session, "m:2", reader)

    assert _memories(service, session, "mara") == []
    assert "character_unknown" in result.skipped_reasons


def test_a_memory_must_name_its_character_and_a_claim_its_speaker(runtime):
    store, service = runtime
    session = _session(_person("m:1", "Hi"), _line("m:2", "bea", "I love rain. Theo hates it."))
    reader = _Reader([
        _learning(1, "Bea", "She loves rain", topic="rain"),
        _learning(1, "Theo", "Theo hates rain", topic="rain"),
    ])

    result = _run(store, service, session, "m:2", reader)

    assert _memories(service, session, "mara") == []
    assert {"character_unnamed", "claim_unattributed"} <= set(result.skipped_reasons)


def test_a_later_line_makes_the_earlier_job_a_no_op_and_its_own_job_reads_the_thread(runtime):
    store, service = runtime
    session = _session(
        _person("m:1", "Hi"), _line("m:2", "bea", "I'm afraid of storms."), _line("m:3", "mara", "Since when?"),
    )
    reader = _Reader([_learning(1, "Bea", "Bea is afraid of storms")])

    earlier = _run(store, service, session, "m:2", reader)
    assert earlier.skipped_reasons == ["later_line_in_thread"] and reader.documents == []

    later = _run(store, service, session, "m:3", reader)
    assert [line["text"] for line in reader.documents[0]["lines"]] == ["I'm afraid of storms.", "Since when?"]
    assert later.through_line_id == "m:3"
    assert [memory.content for memory in _memories(service, session, "mara")] == ["Bea is afraid of storms"]


def test_an_abandoned_thread_is_read_once(runtime):
    store, service = runtime
    session = _session(_person("m:1", "Hi"), _line("m:2", "bea", "I'm afraid of storms."))
    reader = _Reader([_learning(1, "Bea", "Bea is afraid of storms")])
    job = enqueue_scene_lines_job(session.id, "m:2", ("mara", "bea"), job_store=store)

    process_scene_lines_job(job, chat_store=_Chats(session), memory_service=service, job_store=store,
                            reader=reader, member=_member, characters=_Characters())
    again = _run(store, service, session, "m:2", reader)  # the same job, redelivered

    assert len(reader.documents) == 1
    assert again.skipped_reasons == ["job_not_claimable"] or "thread_already_read" in again.skipped_reasons
    [completed] = store.list_jobs(status="completed")
    assert {"type": SCENE_THREAD_MARK, "session_id": "chat:1", "root_id": "m:1",
            "through_line_id": "m:2"} in completed.output_refs


def test_a_line_after_a_job_already_ran_is_still_read(runtime):
    store, service = runtime
    first = _session(_person("m:1", "Hi"), _line("m:2", "bea", "I'm afraid of storms."))
    reader = _Reader([_learning(1, "Bea", "Bea is afraid of storms")],
                     [_learning(1, "Mara", "Mara grew up by the sea", topic="childhood")])
    _run(store, service, first, "m:2", reader)

    later = _session(*first.messages, _line("m:3", "mara", "I grew up by the sea."))
    result = _run(store, service, later, "m:3", reader)

    assert [line["text"] for line in reader.documents[1]["lines"]] == ["I grew up by the sea."]
    assert result.through_line_id == "m:3"
    [bea_knows] = _memories(service, later, "bea")
    assert (bea_knows.content, bea_knows.about_character_id) == ("Mara grew up by the sea", "mara")


def test_the_heard_part_of_an_interrupted_line_is_what_is_read(runtime):
    store, service = runtime
    session = _session(_person("m:1", "Hi"), _line("m:2", "bea", "I'm afraid of storms and spiders.",
                                                  **{HEARD_TEXT_KEY: "I'm afraid of storms"}))
    reader = _Reader([])

    _run(store, service, session, "m:2", reader)

    assert reader.documents[0]["lines"][0]["text"] == "I'm afraid of storms"


@pytest.mark.parametrize("heard", [None, "", "   "])
def test_an_interrupted_line_nobody_is_known_to_have_heard_gives_nothing(runtime, heard):
    # A mismatched, missing or empty heard text (6.5): the unspoken words are never learned.
    store, service = runtime
    session = _session(_person("m:1", "Hi"), _line("m:2", "mara", "I grew up by the sea."),
                       _line("m:3", "bea", "I'm afraid of storms.", **{HEARD_TEXT_KEY: heard}))
    reader = _Reader([_learning(1, "Mara", "Mara grew up by the sea", topic="childhood")])

    _run(store, service, session, "m:3", reader)

    assert [line["text"] for line in reader.documents[0]["lines"]] == ["I grew up by the sea."]

    alone = _session(_person("m:4", "Hi"), _line("m:5", "bea", "I'm afraid of storms.", **{HEARD_TEXT_KEY: heard}))
    quiet = _Reader([_learning(1, "Bea", "Bea is afraid of storms")])
    result = _run(store, service, alone, "m:5", quiet)
    assert quiet.documents == [] and "nothing_heard" in result.skipped_reasons


def test_the_characters_own_word_wins_over_a_claim(runtime):
    store, service = runtime
    claim = _session(_person("m:1", "Hi"), _line("m:2", "bea", "Theo is scared of storms."))
    _run(store, service, claim, "m:2", _Reader([_learning(1, "Theo", "Bea says Theo is scared of storms")]),
         members=("mara", "bea", "theo"))
    [kept] = _memories(service, claim, "mara")
    assert kept.confidence == CLAIM_CONFIDENCE

    own = _session(*claim.messages, _person("m:3", "Theo?"), _line("m:4", "theo", "I love storms."))
    _run(store, service, own, "m:4", _Reader([_learning(1, "Theo", "Theo loves storms")]),
         members=("mara", "bea", "theo"))
    [kept] = _memories(service, own, "mara")
    assert (kept.content, kept.confidence) == ("Theo loves storms", SELF_CONFIDENCE)

    again = _session(*own.messages, _person("m:5", "Bea?"), _line("m:6", "bea", "Theo fears storms."))
    result = _run(store, service, again, "m:6", _Reader([_learning(1, "Theo", "Bea says Theo fears storms")]),
                  members=("mara", "bea", "theo"))
    assert "own_word_kept" in result.skipped_reasons
    assert [memory.content for memory in _memories(service, again, "mara")] == ["Theo loves storms"]


def test_a_private_chat_or_memory_writes_off_reads_nothing(runtime):
    store, service = runtime
    reader = _Reader([_learning(1, "Bea", "Bea is afraid of storms")])
    private = _session(_person("m:1", "Hi"), _line("m:2", "bea", "I'm afraid of storms."),
                       transcript_policy="temporary")
    assert _run(store, service, private, "m:2", reader).skipped_reasons == ["private_session"]
    off = _session(_person("m:1", "Hi"), _line("m:2", "bea", "I'm afraid of storms."), id="chat:2",
                   write_memory=False)
    assert _run(store, service, off, "m:2", reader).skipped_reasons == ["character_memory_write_disabled"]
    assert reader.documents == []


def test_a_pinned_memory_about_a_character_reaches_the_prompt_only_while_they_are_present(runtime):
    from app.platform.assistant_memory.selection import select_memory_records

    _store, service = runtime
    context = resolve_session_memory_scope(_session())
    person = service.create_explicit_memory(
        context, scope="global", category="preference", content="The user likes tea", provenance_id="m:1",
    )
    heard = [
        service.create_heard_memory(
            context, about_character_id="bea", kind="semantic_fact", category="fact", content=content,
            confidence=SELF_CONFIDENCE, provenance_id=f"scene:chat:1:{index}",
        ).model_copy(update={"pinned": True, "updated_at": f"2026-11-15T20:00:0{index}+00:00"})
        for index, content in enumerate(("Bea is afraid of storms", "Bea grew up by the sea"))
    ]

    def chosen(present, limit):
        selection = select_memory_records(
            [person, *heard], context, token_budget=4000, present_characters=present, per_character_limit=limit,
        )
        return {record.content for record in selection.records}

    assert chosen((), 5) == {"The user likes tea"}
    assert chosen(("theo",), 5) == {"The user likes tea"}
    assert chosen(("bea",), 5) == {"The user likes tea", "Bea is afraid of storms", "Bea grew up by the sea"}
    assert chosen(("bea",), 1) == {"The user likes tea", "Bea grew up by the sea"}
    assert chosen(("bea",), 0) == {"The user likes tea"}


def test_the_characters_present_are_the_others_in_the_scene():
    from app.conversation.scene import Scene, with_scene
    from app.platform.assistant_memory.chat_prompt import _present_characters

    session = _session()
    assert _present_characters(session) == ()
    scene = Scene(host=_member("mara"), guests=(_member("bea"), _member("theo")), speaker_id="mara")
    assert _present_characters(with_scene(session, scene)) == ("bea", "theo")
