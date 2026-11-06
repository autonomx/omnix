"""Understanding the person, through the production app on PostgreSQL.

From finished turns in the owner's log, through the job handler the worker runs
and the planner the convergence sweep runs, to the prompt of a new chat and the
Memory tab. Only the model's answer is stubbed; what it may say is the subject.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.composition.production import create_production_app
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.platform.assistant_memory import conversation_reading as reading_module
from app.platform.assistant_memory import feature
from app.platform.assistant_memory.chat_prompt import _v2_space_and_scopes
from app.platform.assistant_memory.conversation_reading import (
    ConversationReadingResponse,
    due_conversations,
    queue_due_readings,
)
from app.platform.assistant_memory.jobs import MEMORY_READ_JOB_TYPE
from app.platform.assistant_memory.v2.curated_records import MemoryV2CuratedConvergence
from app.platform.assistant_memory.v2.runtime import PostgresMemoryV2Runtime
from app.platform.assistant_memory.v2.understanding import active_readings
from app.platform.assistant_memory.v2.understanding_view import read_understanding
from app.platform.chat.models import SendChatMessageRequest
from app.runtime.config import GatewayRole, RuntimeConfig
from app.runtime.tenant_context import pop_tenant, push_tenant

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="needs a scratch PostgreSQL database",
)


class StubReader:
    """Answers with what it is told to; numbers refer to the turns it is shown."""

    provider_id = "stub"
    model_id = "stub-model"

    def __init__(self, answer: dict) -> None:
        self.answer = answer
        self.documents: list[dict] = []

    def read(self, document: dict) -> ConversationReadingResponse:
        self.documents.append(document)
        return ConversationReadingResponse.model_validate(self.answer)


EMPTY = {
    "person": [], "connections": [], "ended_connections": [], "relationship": None, "moods": [], "episode": None,
    "triggers": [], "reactions": [], "stance": None, "promises": [], "kept_promises": [], "jokes": [],
}
FIRST_ANSWER = {
    "person": [
        {"aspect": "humor", "statement": "Teases back when teased", "changed": False, "confidence": 0.8, "turns": [1, 3]},
        {"aspect": "communication_style", "statement": "Wants short answers", "changed": False, "confidence": 0.9, "turns": [3]},
        # none of these may be kept
        {"aspect": "diagnosis", "statement": "Seems depressed", "changed": False, "confidence": 0.9, "turns": [1]},
        {"aspect": "values", "statement": "Rests only on the other one's words", "changed": False, "confidence": 0.9, "turns": [2]},
        {"aspect": "temperament", "statement": "Barely shown", "changed": False, "confidence": 0.2, "turns": [1]},
        {"aspect": "what_helps", "statement": "A fair impression is kept", "changed": False, "confidence": 0.5, "turns": [3]},
        {"aspect": "interests", "statement": "Has a password of hunter2", "changed": False, "confidence": 0.9, "turns": [1]},
    ],
    "connections": [
        {"subject": "Anna", "relation": "is the sister of", "object": "The user", "confidence": 0.9, "turns": [1]},
        {"subject": "Anna", "relation": "lives in", "object": "Toronto", "confidence": 0.9, "turns": [3]},
        {"subject": "Zed", "relation": "works at", "object": "Acme", "confidence": 0.9, "turns": [3]},  # never said
    ],
    "ended_connections": [],
    "relationship": {
        "interpretation": "They trust you enough to complain to you.",
        "closeness": 0.6, "trust": 0.7, "ease": 0.8, "confidence": 0.7, "turns": [1, 3],
    },
    "moods": [
        {"turn": 3, "emotion": "stressed", "valence": -0.4, "arousal": 0.5, "confidence": 0.8},
        {"turn": 2, "emotion": "happy", "valence": 0.8, "arousal": 0.5, "confidence": 0.9},  # the other one's turn
        {"turn": 1, "emotion": "enlightened", "valence": 0.8, "arousal": 0.5, "confidence": 0.9},  # not a mood we keep
    ],
    "episode": {"title": "Talked about Anna", "summary": "They complained about Anna moving to Toronto.", "importance": 0.6},
    "triggers": [], "reactions": [], "stance": None, "promises": [], "kept_promises": [], "jokes": [],
}


@pytest.fixture(scope="module")
def app_client():
    # Module-wide, and undone afterwards: other tests in the run expect their own persistence mode.
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("OMNIX_DATABASE_URL", os.environ["OMNIX_TEST_DATABASE_URL"])
        patch.setenv("OMNIX_PERSISTENCE_MODE", "postgresql")
        patch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
        patch.setenv("OMNIX_MEMORY_STRUCTURED_EXTRACTION_MODE", "deterministic")  # no model behind any test here
        database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_DATABASE_URL"], pool_min=1, pool_max=4))
        tenant = ensure_local_identity(database)
        database.close()
        app = create_production_app(RuntimeConfig(gateway_role=GatewayRole.API))
        with TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"}) as client:
            yield SimpleNamespace(client=client, app=app, tenant=tenant)


class Scene:
    """A character with one chat, driven through the job handlers the worker runs."""

    def __init__(self, context) -> None:
        self.client = context.client
        self.services = context.app.state.runtime_services
        self.tenant = context.tenant
        self.character = f"understanding-{uuid.uuid4().hex[:8]}"
        created = self.client.post("/api/characters", json={
            "id": self.character, "display_name": "Test", "personality_prompt": "Be yourself.", "default_greeting": "Hey.",
        })
        assert created.status_code == 201, created.text
        self.chat_id = self.new_chat()

    def new_chat(self) -> str:
        created = self.client.post("/api/chat/sessions", json={
            "title": "Talk", "interaction_mode": "character", "character_id": self.character,
            "transcript_policy": "persistent",
        })
        assert created.status_code in {200, 201}, created.text
        return created.json()["id"]

    def run_as_tenant(self, function, *args, **kwargs):
        token = push_tenant(self.tenant)
        try:
            return function(*args, **kwargs)
        finally:
            pop_tenant(token)

    def space(self):
        session = self.run_as_tenant(self.services.chat.get_session, self.chat_id)
        return self.run_as_tenant(_v2_space_and_scopes, session)


def _write_turns(scene: Scene, turns: list[tuple[str, str]], *, chat_id: str | None = None, minutes_ago: float = 30) -> None:
    """Turns written the way ``record_turn`` writes them, already old enough to be read."""
    from app.platform.assistant_memory import conversation_reading as module

    session_id = chat_id or scene.chat_id
    session = scene.run_as_tenant(scene.services.chat.get_session, session_id)
    runtime = PostgresMemoryV2Runtime()
    start = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)

    def write() -> None:
        for index, (speaker, text) in enumerate(turns):
            message = SimpleNamespace(
                id=f"{session_id}-{uuid.uuid4().hex[:8]}",
                role=speaker,
                content=text,
                created_at=(start + timedelta(seconds=index)).isoformat(),
            )
            space, scopes = _v2_space_and_scopes(session)
            runtime.append_authoritative_next(
                module._turn_request(
                    space, scopes[0], session, message,
                    event_type="user_said" if speaker == "user" else "assistant_generated",
                    user_id=scene.tenant.user_id,
                )
            )

    scene.run_as_tenant(write)


def _read(scene: Scene, reader: StubReader, monkeypatch) -> None:
    """The sweep queues it and the worker's handler runs it, with the model stubbed."""
    jobs = scene.services.jobs
    monkeypatch.setattr(reading_module, "default_conversation_reader", lambda: reader)
    queue_due_readings(jobs)
    pending = [
        job for job in scene.run_as_tenant(lambda: list(jobs.iter_jobs(job_types=(MEMORY_READ_JOB_TYPE,))))
        if job.input_payload.get("owner_id") == scene.character and job.status in {"queued", "pending"}
    ]
    assert pending, "the sweep queued nothing"
    for job in pending:
        scene.run_as_tenant(
            feature._execute_conversation_reading,
            SimpleNamespace(services=scene.services, job_store=jobs),
            job,
        )


def _converge(scene: Scene) -> None:
    space, _ = scene.space()
    MemoryV2CuratedConvergence(scene.services.jobs.database).run(space=space, max_steps=20)


FIRST_TURNS = [
    ("user", "My sister Anna is driving me up the wall."),
    ("assistant", "Tell me everything, I love drama."),
    ("user", "Short version: Anna moved to Toronto and I'm swamped."),
    ("assistant", "That sounds like a lot."),
]


def _tab(scene: Scene) -> dict:
    response = scene.client.get(f"/api/memory-owners/{scene.character}")
    assert response.status_code == 200, response.text
    return response.json()["understanding"]


def test_a_reading_reaches_the_tab_and_every_new_chat(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, FIRST_TURNS)
    reader = StubReader(FIRST_ANSWER)
    _read(scene, reader, monkeypatch)
    _converge(scene)

    tab = _tab(scene)
    assert {item["aspect"]: item["statement"] for item in tab["person"]} == {
        "humor": "Teases back when teased",
        "communication_style": "Wants short answers",
        "what_helps": "A fair impression is kept",
    }, "invented aspects, the other one's words, weak notes and secrets are not kept"
    assert {(item["subject"], item["relation"], item["object"]) for item in tab["connections"]} == {
        ("Anna", "is the sister of", "The user"),
        ("Anna", "lives in", "Toronto"),
    }, "a name the person never said is not kept"
    assert tab["relationship"]["statement"] == "They trust you enough to complain to you."
    assert [item["emotion"] for item in tab["moods"]] == ["stressed"]
    assert [item["title"] for item in tab["episodes"]] == ["Talked about Anna"]

    # A different chat with the same character knows, without the turn's words matching.
    other_chat = scene.new_chat()
    session = scene.run_as_tenant(scene.services.chat.get_session, other_chat)
    from app.platform.assistant_memory.chat_prompt import resolve_prompt_memory

    memory, _diagnostics = scene.run_as_tenant(resolve_prompt_memory, session, query_text="Where does my sister live?")
    said = {item.content for item in memory}
    assert "They trust you enough to complain to you." in said
    assert "Teases back when teased" in said
    assert any("seemed stressed" in text and "may have passed" in text for text in said)
    assert any("Talked about Anna" in text for text in said)
    assert "Anna lives in Toronto" in said, "my sister finds Anna, and one step on, her city"
    assert sum("Talked about Anna" in text for text in said) == 1, "the same episode, once"
    assert len([item for item in memory if item.category == "relationship"]) == 1

    from app.platform.chat.prompt_rendering import _memory_section

    rendered = _memory_section(SimpleNamespace(approved_memory=memory))
    assert "never recite them" in rendered, "the character is told these are its own impressions"
    assert "closeness" not in rendered.casefold() and "0.6" not in rendered, "no scores reach the prompt"


def test_prompt_read_stays_within_a_reply_budget(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, FIRST_TURNS)
    _read(scene, StubReader(FIRST_ANSWER), monkeypatch)
    _converge(scene)
    space, scopes = scene.space()
    database = scene.services.jobs.database
    read_understanding(database, space, scopes, episodes=2, moods=1)  # a warm connection, as on a live call
    started = time.perf_counter()
    for _ in range(10):
        read_understanding(database, space, scopes, episodes=2, moods=1)
    assert (time.perf_counter() - started) / 10 < 0.05


def test_later_readings_build_on_earlier_ones(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, FIRST_TURNS)
    _read(scene, StubReader(FIRST_ANSWER), monkeypatch)
    _converge(scene)

    _write_turns(scene, [
        ("user", "Anna moved back to Paris last week."),
        ("assistant", "Paris, huh."),
        ("user", "Yes, Anna is in Paris for good."),
    ])
    second = StubReader({
        **EMPTY,
        "person": [{"aspect": "humor", "statement": "Jokes to deflect", "changed": False, "confidence": 0.8, "turns": [1]}],
        "connections": [{"subject": "anna", "relation": "lives in", "object": "Paris", "confidence": 0.9, "turns": [1, 3]}],
        "ended_connections": [2],
    })
    _read(scene, second, monkeypatch)
    _converge(scene)

    shown = second.documents[0]
    assert [turn["text"] for turn in shown["turns"]][0] == "Anna moved back to Paris last week.", "only what is unread"
    assert shown["known"]["relationship"] == "They trust you enough to complain to you."
    assert shown["known"]["connections"][1]["object"] == "Toronto"

    tab = _tab(scene)
    assert {item["statement"] for item in tab["person"] if item["aspect"] == "humor"} == {"Jokes to deflect"}
    assert {(item["subject"], item["object"]) for item in tab["connections"]} == {
        ("Anna", "The user"),
        ("Anna", "Paris"),
    }, "the old city ended, and one Anna however she is spelled"
    assert tab["relationship"]["statement"] == "They trust you enough to complain to you.", "said nothing new: it stands"


def test_forgetting_removes_the_text_everywhere_and_it_does_not_come_back(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, FIRST_TURNS)
    _read(scene, StubReader(FIRST_ANSWER), monkeypatch)
    _converge(scene)
    tab = _tab(scene)
    link = next(item for item in tab["connections"] if item["object"] == "Toronto")

    for kind, key in (
        ("person", "humor"),
        ("connection", link["key"]),
        ("relationship", "current"),
        ("mood", tab["moods"][0]["key"]),
        ("episode", tab["episodes"][0]["key"]),
    ):
        response = scene.client.delete(f"/api/memory-owners/{scene.character}/understanding/{kind}/{key}")
        assert response.status_code == 200, (kind, response.text)

    _converge(scene)
    tab = _tab(scene)
    assert [item["aspect"] for item in tab["person"]] == ["communication_style", "what_helps"], "other notes stay"
    assert [item["object"] for item in tab["connections"]] == ["The user"]
    assert tab["relationship"] is None and tab["moods"] == [] and tab["episodes"] == []

    # Nothing anywhere still holds the words: not the derived tables, the log, the search index or old decisions.
    space, _ = scene.space()
    values = (space.principal_id, space.owner_type, space.owner_id)
    database = scene.services.jobs.database
    with database.transaction() as connection:
        for table, column in (
            ("omnix_memory_v2_observations", "payload"),
            ("omnix_memory_v2_graph_assertions", "object_value"),
            ("omnix_memory_v2_search_index_entries", "content"),
            ("omnix_memory_v2_consolidation_decision_sets", "deterministic_decisions"),
        ):
            rows = connection.execute(
                f"SELECT {column}::text FROM {table} WHERE principal_id = %s AND owner_type = %s AND owner_id = %s",
                values,
            ).fetchall()
            for phrase in ("Teases back", "complain to you", "Talked about Anna"):
                assert not any(phrase in str(row[0]) for row in rows), (table, phrase)

    # The next reading is told only what remains.
    _write_turns(scene, [("user", "Hello again."), ("assistant", "Hi."), ("user", "Still here.")])
    third = StubReader(EMPTY)
    _read(scene, third, monkeypatch)
    known = third.documents[0]["known"]
    assert {note["aspect"] for note in known["person"]} == {"communication_style", "what_helps"}
    assert known["relationship"] is None


def test_a_correction_stands_against_later_readings(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, FIRST_TURNS)
    _read(scene, StubReader(FIRST_ANSWER), monkeypatch)
    _converge(scene)

    response = scene.client.patch(
        f"/api/memory-owners/{scene.character}/understanding/person/humor",
        json={"text": "Dry humor, never slapstick"},
    )
    assert response.status_code == 200, response.text
    _converge(scene)
    shown = {item["aspect"]: item for item in _tab(scene)["person"]}
    assert shown["humor"]["statement"] == "Dry humor, never slapstick" and shown["humor"]["corrected"] is True

    _write_turns(scene, [("user", "Ha, slapstick is the best."), ("assistant", "Ha."), ("user", "I mean it.")])
    _read(scene, StubReader({
        **EMPTY, "person": [{"aspect": "humor", "statement": "Loves slapstick", "changed": False, "confidence": 0.9, "turns": [1]}],
    }), monkeypatch)
    _converge(scene)
    assert {item["aspect"]: item["statement"] for item in _tab(scene)["person"]}["humor"] == "Dry humor, never slapstick"


def _reaction(turn: int, kind: str, lesson: str, *, helped: bool = True, same_as: int | None = None) -> dict:
    return {
        "turn": turn, "kind": kind, "helped": helped, "reaction": "They stopped the reply short",
        "why": "It jumped to a list of steps", "aspect": "what_helps", "lesson": lesson, "same_as": same_as,
        "advice": "Listen first, and offer steps only when asked",
        "confidence": 0.7,
    }


def test_reactions_to_replies_add_up_to_lessons_that_reach_every_chat(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, [
        ("user", "Can you help me with my week?"),
        ("assistant", "Here are ten steps to plan it."),
        ("user", "Stop, I just wanted to vent."),
        ("assistant", "Sorry. Tell me what happened."),
        ("user", "Thanks, that is better."),
    ])
    _read(scene, StubReader({**EMPTY, "reactions": [
        _reaction(1, "pushed_back", "Wants to be heard"),  # nothing to react to yet
        _reaction(2, "approved", "Wants to be heard"),  # the other one's turn
        _reaction(3, "pushed_back", "The user wants to be heard before advice.", helped=True),
        _reaction(5, "approved", "A whole sentence about how the user feels about advice in general terms"),
        _reaction(5, "thanked", "wants to be heard before advice", helped=False),
    ]}), monkeypatch)
    _converge(scene)
    space, _ = scene.space()
    reactions = [
        reaction for item in active_readings(scene.services.jobs.database, space)
        for reaction in item.payload.get("reactions", [])
    ]
    assert [(item["kind"], item["helped"]) for item in reactions] == [("pushed_back", False), ("thanked", True)], (
        "pushback did not help and thanks did, whatever the model said"
    )
    assert {item["lesson"] for item in reactions} == {"Wants to be heard before advice"}

    _write_turns(scene, [
        ("user", "Can you look at my code?"),
        ("assistant", "Sure, try these five fixes."),
        ("user", "No, you missed the point."),
    ])
    second = StubReader({**EMPTY, "reactions": [_reaction(3, "corrected", "Needs to feel listened to", same_as=1)]})
    _read(scene, second, monkeypatch)
    _converge(scene)
    assert second.documents[0]["known"]["lessons"] == [
        {"number": 1, "aspect": "what_helps", "lesson": "Wants to be heard before advice", "seen": 2},
    ]
    lessons = _tab(scene)["lessons"]
    assert [(item["lesson"], item["aspect"], item["seen"]) for item in lessons] == [
        ("Wants to be heard before advice", "what_helps", 3),
    ], "seen again is the same lesson, worded as first seen"

    session = scene.run_as_tenant(scene.services.chat.get_session, scene.new_chat())
    from app.platform.assistant_memory.chat_prompt import resolve_prompt_memory

    memory, _diagnostics = scene.run_as_tenant(resolve_prompt_memory, session, query_text="Hello")
    assert [item.content for item in memory].count(
        "Learned from how they react: Listen first, and offer steps only when asked"
    ) == 1, "the lesson reaches a reply as what to do about it"
    assert not any("heard before advice" in item.content for item in memory), "once, as guidance"
    assert lessons[0]["advice"] == "Listen first, and offer steps only when asked"

    response = scene.client.delete(f"/api/memory-owners/{scene.character}/understanding/lesson/{lessons[0]['key']}")
    assert response.status_code == 200, response.text
    _converge(scene)
    assert _tab(scene)["lessons"] == []
    with scene.services.jobs.database.transaction() as connection:
        rows = connection.execute(
            "SELECT payload::text FROM omnix_memory_v2_observations WHERE principal_id = %s AND owner_type = %s"
            " AND owner_id = %s AND event_type = 'conversation_reading'",
            (space.principal_id, space.owner_type, space.owner_id),
        ).fetchall()
    assert not any("heard before advice" in str(row[0]) for row in rows)


def test_the_same_correction_can_be_made_again_after_forgetting_it(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, FIRST_TURNS)
    _read(scene, StubReader(FIRST_ANSWER), monkeypatch)
    _converge(scene)
    url = f"/api/memory-owners/{scene.character}/understanding/person/humor"
    for _ in range(2):
        assert scene.client.patch(url, json={"text": "Dry humor"}).status_code == 200
        _converge(scene)
        assert {item["aspect"]: item["statement"] for item in _tab(scene)["person"]}["humor"] == "Dry humor"
        assert scene.client.delete(url).status_code == 200
        _converge(scene)
        assert "humor" not in {item["aspect"] for item in _tab(scene)["person"]}


def test_deleting_a_chat_takes_its_turns_and_what_was_read_from_them(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, FIRST_TURNS)
    _read(scene, StubReader(FIRST_ANSWER), monkeypatch)
    _converge(scene)
    space, _ = scene.space()

    assert scene.client.delete(f"/api/chat/sessions/{scene.chat_id}").status_code in {200, 204}
    from app.events.outbox_relay import OutboxRelayWorker

    OutboxRelayWorker(scene.services.jobs.database, app_client.app.state.outbox_consumers).run_once()
    _converge(scene)

    tab = _tab(scene)
    assert tab["person"] == [] and tab["connections"] == [] and tab["episodes"] == [] and tab["moods"] == []
    assert tab["relationship"] is None
    database = scene.services.jobs.database
    with database.transaction() as connection:
        rows = connection.execute(
            "SELECT payload::text FROM omnix_memory_v2_observations"
            " WHERE principal_id = %s AND owner_type = %s AND owner_id = %s",
            (space.principal_id, space.owner_type, space.owner_id),
        ).fetchall()
    assert not any("Anna" in str(row[0]) for row in rows)


def test_after_a_chat_is_deleted_the_chats_read_after_it_are_read_again(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    episode = {**EMPTY, "episode": {"title": "A talk", "summary": "They talked.", "importance": 0.3}}
    _write_turns(scene, FIRST_TURNS, minutes_ago=40)
    other_chat = scene.new_chat()
    _write_turns(scene, [("user", "My dog loves the park."), ("assistant", "Cute."), ("user", "He does.")],
                 chat_id=other_chat, minutes_ago=30)
    _read(scene, StubReader(episode), monkeypatch)
    _read(scene, StubReader(episode), monkeypatch)
    _converge(scene)
    assert len(_tab(scene)["episodes"]) == 2

    # The other chat was read after this one, so its reading goes too, and the cursor goes back to where
    # the first job of all once started: the same unread turns must be read again, not found already done.
    assert scene.client.delete(f"/api/chat/sessions/{scene.chat_id}").status_code in {200, 204}
    from app.events.outbox_relay import OutboxRelayWorker

    OutboxRelayWorker(scene.services.jobs.database, app_client.app.state.outbox_consumers).run_once()
    _converge(scene)
    assert _tab(scene)["episodes"] == []
    again = StubReader(episode)
    _read(scene, again, monkeypatch)
    _converge(scene)
    assert [turn["text"] for turn in again.documents[0]["turns"]][0] == "My dog loves the park."
    assert len(_tab(scene)["episodes"]) == 1


def test_deleting_a_chat_reaches_every_character_it_talked_to(app_client, monkeypatch) -> None:
    """Found on a real chat, switched from Jinx to Morgan: the turns stay in the log of whoever heard them."""
    scene = Scene(app_client)
    _write_turns(scene, FIRST_TURNS)
    _read(scene, StubReader(FIRST_ANSWER), monkeypatch)
    _converge(scene)
    space, _ = scene.space()

    other = f"understanding-{uuid.uuid4().hex[:8]}"
    created = scene.client.post("/api/characters", json={
        "id": other, "display_name": "Other", "personality_prompt": "Be yourself.", "default_greeting": "Hey.",
    })
    assert created.status_code == 201, created.text
    moved = scene.client.post(
        f"/api/chat/sessions/{scene.chat_id}/interaction",
        json={"interaction_mode": "character", "character_id": other},
    )
    assert moved.status_code in {200, 201}, moved.text

    assert scene.client.delete(f"/api/chat/sessions/{scene.chat_id}").status_code in {200, 204}
    from app.events.outbox_relay import OutboxRelayWorker

    OutboxRelayWorker(scene.services.jobs.database, app_client.app.state.outbox_consumers).run_once()
    MemoryV2CuratedConvergence(scene.services.jobs.database).run(space=space, max_steps=20)
    tab = _tab(scene)
    assert tab["person"] == [] and tab["relationship"] is None, "the first character forgot too"
    with scene.services.jobs.database.transaction() as connection:
        rows = connection.execute(
            "SELECT payload::text FROM omnix_memory_v2_observations"
            " WHERE principal_id = %s AND owner_type = %s AND owner_id = %s",
            (space.principal_id, space.owner_type, space.owner_id),
        ).fetchall()
    assert not any("Anna" in str(row[0]) for row in rows)


def test_curated_memories_survive_a_rebuild_with_readings_and_the_reverse(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    saved = scene.client.post(
        f"/api/memory-owners/{scene.character}/records", json={"category": "fact", "content": "Likes chocolate."},
    )
    assert saved.status_code == 201, saved.text
    _write_turns(scene, FIRST_TURNS)
    _read(scene, StubReader(FIRST_ANSWER), monkeypatch)
    _converge(scene)

    # Forgetting a saved memory rebuilds the space, and the rebuild deletes whatever its plan leaves out.
    forgotten = scene.client.delete(
        f"/api/memory-owners/{scene.character}/records/{saved.json()['id']}",
        params={"expected_revision": saved.json()["revision"]},
    )
    assert forgotten.status_code in {200, 204}, forgotten.text
    _converge(scene)
    assert _tab(scene)["relationship"] is not None, "the understanding survived a curated rebuild"

    kept = scene.client.post(
        f"/api/memory-owners/{scene.character}/records", json={"category": "fact", "content": "Likes tea."},
    )
    assert kept.status_code == 201
    _converge(scene)
    assert scene.client.delete(f"/api/memory-owners/{scene.character}/understanding/person/humor").status_code == 200
    _converge(scene)
    assert [row["content"] for row in scene.client.get(f"/api/memory-owners/{scene.character}").json()["records"]] == [
        "Likes tea."
    ], "a saved memory survived an understanding rebuild"


def _prompt(scene: Scene, query: str) -> tuple[list, str]:
    from app.platform.assistant_memory.chat_prompt import resolve_prompt_memory
    from app.platform.chat.prompt_rendering import _memory_section

    session = scene.run_as_tenant(scene.services.chat.get_session, scene.new_chat())
    memory, _diagnostics = scene.run_as_tenant(resolve_prompt_memory, session, query_text=query)
    return memory, _memory_section(SimpleNamespace(approved_memory=memory))


def test_what_sets_off_a_mood_comes_back_when_its_subject_does(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, [
        ("user", "My manager moved the deadline again, I'm so stressed."),
        ("assistant", "Again? That is rough."),
        ("user", "Every time the deadlines move I can't sleep."),
    ])
    trigger = {
        "emotion": "stressed", "pattern": "The user gets stressed when deadlines move.", "about": ["deadlines", "manager"],
        "same_as": None, "confidence": 0.8, "turns": [1, 3],
    }
    _read(scene, StubReader({**EMPTY, "triggers": [
        trigger,
        {**trigger, "pattern": "Hates Mondays", "about": ["Mondays"]},  # never said
        {**trigger, "pattern": "Gets moody", "emotion": "moody", "about": ["manager"]},  # not a mood we keep
        {**trigger, "pattern": "Dreads reviews", "turns": [2]},  # the other one's turn
    ]}), monkeypatch)
    _converge(scene)
    _write_turns(scene, [("user", "The deadlines moved again."), ("assistant", "Oh no."), ("user", "Yes, again.")])
    second = StubReader({**EMPTY, "triggers": [{**trigger, "pattern": "Anxious about schedules", "same_as": 1}]})
    _read(scene, second, monkeypatch)
    _converge(scene)
    assert second.documents[0]["known"]["triggers"] == [{
        "number": 1, "emotion": "stressed", "pattern": "Gets stressed when deadlines move",
        "about": ["deadlines", "manager"], "seen": 1,
    }]
    triggers = _tab(scene)["triggers"]
    assert [(item["pattern"], item["emotion"], item["about"], item["seen"]) for item in triggers] == [
        ("Gets stressed when deadlines move", "stressed", ["deadlines", "manager"], 2),
    ]

    memory, _rendered = _prompt(scene, "My manager wants to talk tomorrow.")
    assert "Gets stressed when deadlines move" in {item.content for item in memory}, "naming the manager brings it back"
    memory, _rendered = _prompt(scene, "What should I cook tonight?")
    assert "Gets stressed when deadlines move" not in {item.content for item in memory}, "nothing it concerns"

    response = scene.client.delete(f"/api/memory-owners/{scene.character}/understanding/trigger/{triggers[0]['key']}")
    assert response.status_code == 200, response.text
    _converge(scene)
    assert _tab(scene)["triggers"] == []


def test_a_note_that_turns_around_keeps_the_view_before_it(app_client, monkeypatch) -> None:
    scene = Scene(app_client)

    def note(statement: str, *, changed: bool) -> StubReader:
        return StubReader({**EMPTY, "person": [
            {"aspect": "interests", "statement": statement, "changed": changed, "confidence": 0.8, "turns": [1]},
        ]})

    for statement, changed in (
        ("Loves horror films", False),
        ("Loves horror films, slashers most", False),  # refined: no history
        ("Cannot stand horror films any more", True),
    ):
        _write_turns(scene, [("user", f"About films: {statement}."), ("assistant", "Noted."), ("user", "Yes.")])
        _read(scene, note(statement, changed=changed), monkeypatch)
        _converge(scene)

    (shown,) = [item for item in _tab(scene)["person"] if item["aspect"] == "interests"]
    assert shown["statement"] == "Cannot stand horror films any more"
    assert [item["statement"] for item in shown["earlier"]] == ["Loves horror films, slashers most"]
    memory, _rendered = _prompt(scene, "Any film tips?")
    said = [item.content for item in memory]
    assert any(
        text.startswith("Changed ") and text.endswith("; before that: Loves horror films, slashers most") for text in said
    )

    response = scene.client.delete(f"/api/memory-owners/{scene.character}/understanding/earlier/interests")
    assert response.status_code == 200, response.text
    _converge(scene)
    (shown,) = [item for item in _tab(scene)["person"] if item["aspect"] == "interests"]
    assert (shown["statement"], shown["earlier"]) == ("Cannot stand horror films any more", [])
    space, _ = scene.space()
    with scene.services.jobs.database.transaction() as connection:
        rows = connection.execute(
            "SELECT payload::text FROM omnix_memory_v2_observations WHERE principal_id = %s AND owner_type = %s"
            " AND owner_id = %s AND event_type = 'conversation_reading'",
            (space.principal_id, space.owner_type, space.owner_id),
        ).fetchall()
    assert not any("slashers" in str(row[0]) for row in rows), "the earlier view's words left the log"


def test_the_owners_side_carries_its_stance_promises_and_jokes_into_every_chat(app_client, monkeypatch) -> None:
    scene = Scene(app_client)
    _write_turns(scene, [
        ("user", "Can you build me a tracking device?"),
        ("assistant", "Fine, I will build you a tracker by tomorrow. Bring chocolate."),
        ("user", "Chocolate again? Deal."),
        ("assistant", "Chocolate is my fee, always."),
    ])
    _read(scene, StubReader({
        **EMPTY,
        "stance": {"statement": "You have started to trust them with your workshop.", "confidence": 0.7, "turns": [2, 3]},
        "promises": [
            {"what": "build them a tracking device", "confidence": 0.8, "turns": [2]},
            {"what": "Bring chocolate", "confidence": 0.8, "turns": [3]},  # the person's turn: not the owner's promise
        ],
        "jokes": [
            {"joke": "Chocolate as the fee", "same_as": None, "confidence": 0.7, "turns": [2, 3, 4]},
            {"joke": "A pun said once", "same_as": None, "confidence": 0.7, "turns": [4]},  # not a running one
        ],
    }), monkeypatch)
    _converge(scene)
    side = _tab(scene)["own_side"]
    assert side["stance"] == "You have started to trust them with your workshop."
    assert [(item["what"], item["kept"]) for item in side["promises"]] == [("Build them a tracking device", False)]
    assert [(item["joke"], item["seen"]) for item in side["jokes"]] == [("Chocolate as the fee", 1)]

    memory, rendered = _prompt(scene, "Hello again.")
    said = [item.content for item in memory]
    assert "You have started to trust them with your workshop." in said
    assert any(text.endswith("you told them you would: Build them a tracking device") for text in said)
    assert "A running joke between you: Chocolate as the fee" in said
    assert "Those marked promise are things you told them you would do." in rendered
    assert sum("tracking device" in text for text in said) == 1, "once, as the owner's promise, not again from retrieval"

    _write_turns(scene, [("user", "Did you finish the tracker?"), ("assistant", "Done. Chocolate first."), ("user", "Ha, fine.")])
    second = StubReader({
        **EMPTY, "kept_promises": [1],
        "jokes": [{"joke": "Chocolate payment", "same_as": 1, "confidence": 0.7, "turns": [2]}],
    })
    _read(scene, second, monkeypatch)
    _converge(scene)
    assert second.documents[0]["known"]["promises"] == [{"number": 1, "what": "Build them a tracking device"}]
    side = _tab(scene)["own_side"]
    assert [(item["what"], item["kept"]) for item in side["promises"]] == [("Build them a tracking device", True)]
    assert [(item["joke"], item["seen"]) for item in side["jokes"]] == [("Chocolate as the fee", 2)]
    memory, _rendered = _prompt(scene, "Hello again.")
    assert not any("tracking device" in item.content for item in memory), "a kept promise is no longer owed"

    for kind, key in (("joke", side["jokes"][0]["key"]), ("stance", "current"), ("promise", side["promises"][0]["key"])):
        response = scene.client.delete(f"/api/memory-owners/{scene.character}/understanding/{kind}/{key}")
        assert response.status_code == 200, (kind, response.text)
    _converge(scene)
    assert _tab(scene)["own_side"] == {"stance": None, "stance_updated_at": None, "promises": [], "jokes": []}


def test_a_saved_memory_says_how_long_ago_it_was_noted(app_client) -> None:
    scene = Scene(app_client)
    saved = scene.client.post(
        f"/api/memory-owners/{scene.character}/records", json={"category": "fact", "content": "Lives in Toronto."},
    )
    assert saved.status_code == 201, saved.text
    _converge(scene)
    _memory, rendered = _prompt(scene, "Where do I live, Toronto?")
    line = next(line for line in rendered.splitlines() if "Lives in Toronto." in line)
    assert "; noted earlier today]" in line, line


def test_several_unread_chats_are_each_read_in_turn(app_client, monkeypatch) -> None:
    """Found on real chats: they share a last turn, so one job per last turn read only the first."""
    scene = Scene(app_client)
    second_chat = scene.new_chat()
    _write_turns(scene, FIRST_TURNS)
    _write_turns(scene, [("user", "Other chat, first line."), ("assistant", "OK."), ("user", "Other chat, second line.")], chat_id=second_chat)
    first, second = StubReader(EMPTY), StubReader(EMPTY)
    _read(scene, first, monkeypatch)
    _read(scene, second, monkeypatch)
    assert {turn["text"] for turn in first.documents[0]["turns"]} == {text for _speaker, text in FIRST_TURNS}, "one chat at a time"
    assert second.documents[0]["turns"][0]["text"] == "Other chat, first line."
    space, _ = scene.space()
    assert scene.character not in {item.space.owner_id for item in due_conversations(scene.services.jobs.database, limit=512)}
    assert len(active_readings(scene.services.jobs.database, space)) == 2


def test_quiet_and_length_decide_when_a_conversation_is_read(app_client) -> None:
    scene = Scene(app_client)
    database = scene.services.jobs.database

    def due() -> set[str]:
        return {item.space.owner_id for item in due_conversations(database, limit=512)}

    _write_turns(scene, [("user", "Just one remark."), ("assistant", "OK.")])
    assert scene.character not in due(), "one remark waits for more"
    _write_turns(scene, [("user", "A second remark."), ("assistant", "OK.")], minutes_ago=1)
    assert scene.character not in due(), "still talking"
    _write_turns(scene, [("user", f"line {index}") for index in range(40)], minutes_ago=1)
    assert scene.character in due(), "a long conversation does not wait to end"


def test_real_turn_job_writes_the_turn_once_and_private_chats_write_nothing(app_client) -> None:
    scene = Scene(app_client)
    store = scene.services.chat
    runtime = PostgresMemoryV2Runtime()
    from app.platform.assistant_memory.conversation_reading import record_turn

    def turn_events(space) -> list[str]:
        return [
            item.event_type for item in runtime.observation_store.list(
                space, after_sequence=0, through_sequence=runtime.observation_store.watermark(space),
                include_inactive=False, limit=100,
            )
        ]

    def act() -> None:
        _, message = store.begin_user_message(scene.chat_id, SendChatMessageRequest(content="I like hiking."))
        session = store.get_session(scene.chat_id)
        record_turn(session, message, runtime=runtime)
        record_turn(session, message, runtime=runtime)

    scene.run_as_tenant(act)
    space, _ = scene.space()
    assert turn_events(space) == ["user_said"], "a retried job writes nothing new"

    private = scene.client.post("/api/chat/sessions", json={
        "title": "Quiet", "interaction_mode": "character", "character_id": scene.character,
        "transcript_policy": "private",
    })
    if private.status_code in {200, 201}:
        def act_private() -> None:
            from app.platform.assistant_memory.jobs import enqueue_memory_suggestion_job

            _, message = store.begin_user_message(private.json()["id"], SendChatMessageRequest(content="Secret plans."))
            job = enqueue_memory_suggestion_job(private.json()["id"], message.id, job_store=scene.services.jobs)
            feature._execute_memory_suggestion(SimpleNamespace(services=scene.services, job_store=scene.services.jobs), job)

        scene.run_as_tenant(act_private)
    assert turn_events(space) == ["user_said"]


def test_active_readings_are_bounded_and_scoped_to_the_owner(app_client, monkeypatch) -> None:
    scene, other = Scene(app_client), Scene(app_client)
    _write_turns(scene, FIRST_TURNS)
    _read(scene, StubReader(FIRST_ANSWER), monkeypatch)
    space, _ = scene.space()
    other_space, _ = other.space()
    database = scene.services.jobs.database
    assert len(active_readings(database, space)) == 1
    assert active_readings(database, other_space) == ()
