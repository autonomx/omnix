"""What a model's reading of a conversation may become, and which model reads it."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.platform.assistant_memory import conversation_reading as module
from app.platform.assistant_memory.conversation_reading import ConversationReadingResponse, build_reading
from app.platform.assistant_memory.v2.contracts import (
    MemorySpaceKey,
    Observation,
    ObservationProvenance,
    VisibilityScope,
)
from app.platform.assistant_memory.v2.understanding import Understanding
from app.providers.base import ProviderConfig
from app.providers.claude_cli_provider import ClaudeCliProvider

SPACE = MemorySpaceKey(principal_id="p", owner_type="character", owner_id="jinx")
SCOPE = VisibilityScope(kind="global", scope_id="me")
NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
EMPTY = {
    "person": [], "connections": [], "ended_connections": [], "relationship": None, "moods": [], "episode": None,
    "triggers": [], "reactions": [], "stance": None, "promises": [], "kept_promises": [], "jokes": [],
}


def _turn(number: int, text: str, *, user: bool = True) -> Observation:
    return Observation(
        observation_id=f"o{number}", authority_sequence=number, idempotency_key=f"k{number}", space=SPACE,
        visibility_scope=SCOPE, event_type="user_said" if user else "assistant_generated", occurred_at=NOW,
        recorded_at=NOW, payload={"text": text}, correlation_id=f"c{number}", content_digest="d" * 64,
        provenance=ObservationProvenance(
            source_type="user" if user else "assistant", source_id="x",
            trust_level="user_explicit" if user else "assistant_inference",
        ),
    )


TURNS = (_turn(1, "My sister Anna moved to Toronto."), _turn(2, "Oh nice.", user=False), _turn(3, "I want to take over the city."))


def _links(*links: tuple[str, str, str]):
    answer = ConversationReadingResponse.model_validate({**EMPTY, "connections": [
        {"subject": subject, "relation": relation, "object": object_, "confidence": 0.9, "turns": [1, 3]}
        for subject, relation, object_ in links
    ]})
    return [
        (link.subject, link.object)
        for link in build_reading(TURNS, answer, Understanding(), [], through_sequence=3, session_id="s").connections
    ]


def test_a_connection_joins_two_names_the_person_said() -> None:
    assert _links(("Anna", "lives in", "Toronto")) == [("Anna", "Toronto")]
    assert _links(("Zed", "works at", "Acme")) == [], "nobody said those"
    assert _links(("The user", "wants to", "take over the whole damn city")) == [], "a plan, not a name"


def test_a_note_rests_on_the_users_own_words() -> None:
    answer = ConversationReadingResponse.model_validate({**EMPTY, "person": [
        {"aspect": "humor", "statement": "Only the other one joked", "changed": False, "confidence": 0.9, "turns": [2]},
        {"aspect": "interests", "statement": "Follows family news", "changed": False, "confidence": 0.5, "turns": [1]},
    ]})
    reading = build_reading(TURNS, answer, Understanding(), [], through_sequence=3, session_id="s")
    assert [note.aspect for note in reading.person] == ["interests"]


def _reacting(turns, *reactions: tuple[int, str, str]):
    answer = ConversationReadingResponse.model_validate({**EMPTY, "reactions": [
        {"turn": turn, "kind": kind, "helped": True, "reaction": "They pushed back", "why": "The reply lectured",
         "aspect": "what_to_avoid", "lesson": lesson, "advice": "Make one point, then stop", "same_as": None,
         "confidence": 0.7}
        for turn, kind, lesson in reactions
    ]})
    return build_reading(turns, answer, Understanding(), [], through_sequence=len(turns), session_id="s").reactions


def test_a_reaction_answers_the_reply_before_it_and_its_lesson_is_a_pattern() -> None:
    turns = (
        _turn(1, "Explain it."), _turn(2, "Here is a long lecture.", user=False),
        _turn(3, "Ugh."), _turn(4, "Too long, stop."),
    )
    kept = _reacting(turns, (4, "pushed_back", "They tend to tune out long lectures."))
    assert [(item.reply_id, item.helped, item.lesson) for item in kept] == [("o2", False, "Tune out long lectures")]
    assert _reacting(turns, (1, "pushed_back", "Hates lectures")) == (), "nothing came before it"
    assert _reacting(turns, (4, "sulked", "Hates lectures")) == (), "not a kind of reaction"


def test_lessons_add_up_and_the_most_seen_reach_the_prompt() -> None:
    from app.platform.assistant_memory.v2.understanding import Reading, add_up, project_readings
    from app.platform.assistant_memory.v2.understanding_view import UnderstandingItem, prompt_items

    turns = (_turn(1, "Explain it."), _turn(2, "A lecture.", user=False), _turn(3, "Stop."))
    first = _reacting(turns, (3, "pushed_back", "Tunes out long lectures"))
    again = first[0].model_copy(update={"observation_id": "o9"})
    readings = [
        _turn(10 + index, "").model_copy(update={
            "event_type": "conversation_reading", "payload": Reading(through_sequence=3 + index, reactions=(item,)).model_dump(mode="json"),
        })
        for index, item in enumerate((first[0], again))
    ]
    understood = add_up(readings)
    assert [len(seen) for seen in understood.lessons.values()] == [2]
    (lesson,) = [item for item in project_readings(SPACE, readings).assertions if item.predicate.startswith("lesson_")]
    assert (lesson.predicate, lesson.object.literal, lesson.revision) == ("lesson_what_to_avoid", "Tunes out long lectures", 2)

    items = [
        UnderstandingItem(key=f"k{seen}", kind="lesson", text=f"Lesson {seen}", category="trait", at=NOW, seen=seen)
        for seen in range(1, 9)
    ]
    assert [item.text for item in prompt_items(items, "", now=NOW)] == [
        f"Learned from how they react: Lesson {seen}" for seen in range(8, 2, -1)
    ], "told as guidance, the most seen first"
    avoid = UnderstandingItem(key="a", kind="person", text="Long lectures", category="trait", label="what_to_avoid")
    humor = UnderstandingItem(key="h", kind="person", text="Dry", category="trait", label="humor")
    assert [(item.category, item.text) for item in prompt_items([avoid, humor], "", now=NOW)] == [
        ("guidance", "Avoid with them: Long lectures"), ("trait", "Dry"),
    ]


def _as_reading(number: int, reading) -> Observation:
    return _turn(number, "").model_copy(update={
        "event_type": "conversation_reading", "payload": reading.model_dump(mode="json"),
    })


def test_a_trigger_is_a_pattern_about_something_the_person_named() -> None:
    turns = (_turn(1, "My manager moved the deadline."), _turn(2, "Ugh.", user=False), _turn(3, "I hate that."))

    def kept(**change):
        trigger = {"emotion": "stressed", "pattern": "Stressed when deadlines move", "about": ["manager", "deadline"],
                   "same_as": None, "confidence": 0.7, "turns": [1], **change}
        answer = ConversationReadingResponse.model_validate({**EMPTY, "triggers": [trigger]})
        return build_reading(turns, answer, Understanding(), [], through_sequence=3, session_id="s").triggers

    (trigger,) = kept()
    assert (trigger.pattern, trigger.about, trigger.evidence) == ("Stressed when deadlines move", ("manager", "deadline"), ("o1",))
    assert kept(about=["Mondays"]) == (), "nothing the person named"
    assert kept(turns=[2]) == (), "the other one's turn"
    assert kept(emotion="moody") == (), "not a mood we keep"
    assert kept(pattern="A long sentence about how the user feels whenever anything at work changes") == ()


def test_a_note_turned_around_keeps_the_one_before_and_the_persons_own_words_stand_alone() -> None:
    from app.platform.assistant_memory.v2.understanding import PersonNote, Reading, add_up, project_readings

    def note(statement: str, *, changed: bool = False) -> PersonNote:
        return PersonNote(aspect="interests", statement=statement, confidence=0.8, evidence=("o1",), replaces_known=changed)

    readings = [
        _as_reading(10, Reading(through_sequence=1, person=(note("Loves horror"),))),
        _as_reading(11, Reading(through_sequence=2, person=(note("Loves horror, slashers most"),))),
        _as_reading(12, Reading(through_sequence=3, person=(note("Cannot stand horror", changed=True),))),
    ]
    understood = add_up(readings)
    assert [earlier.statement for earlier, _source, _at in understood.earlier["interests"]] == ["Loves horror, slashers most"]
    superseded = [item for item in project_readings(SPACE, readings).assertions if item.status == "superseded"]
    assert [item.object.literal for item in superseded] == ["Loves horror, slashers most"]

    corrected = _as_reading(13, Reading(through_sequence=4, from_owner=True, person=(note("Likes thrillers"),)))
    assert "interests" not in add_up([*readings, corrected]).earlier


def test_the_owners_side_keeps_its_own_promises_and_only_jokes_that_came_back() -> None:
    turns = (
        _turn(1, "Build me a tracker."), _turn(2, "I'll build you a tracker. Chocolate is my fee.", user=False),
        _turn(3, "Chocolate again?"), _turn(4, "Always chocolate.", user=False),
    )

    def side(**answer):
        reply = ConversationReadingResponse.model_validate({**EMPTY, **answer})
        return build_reading(turns, reply, Understanding(), [], through_sequence=4, session_id="s")

    promised = side(promises=[
        {"what": "build them a tracker", "confidence": 0.8, "turns": [2]},
        {"what": "Bring chocolate", "confidence": 0.8, "turns": [1, 3]},
        {"what": "Do a very long list of things that nobody could ever keep track of in one promise at all", "confidence": 0.8, "turns": [2]},
    ]).promises
    assert [(item.what, item.evidence) for item in promised] == [("Build them a tracker", ("o2",))]
    jokes = side(jokes=[
        {"joke": "Chocolate as the fee", "same_as": None, "confidence": 0.7, "turns": [2, 3, 4]},
        {"joke": "Said once", "same_as": None, "confidence": 0.7, "turns": [4]},
    ]).jokes
    assert [item.joke for item in jokes] == ["Chocolate as the fee"]
    stance = side(stance={"statement": "You let them in a little.", "confidence": 0.2, "turns": [2]}).stance
    assert stance is None, "a hunch about the owner's side is not kept"


def test_how_they_talk_is_never_the_machines_transcription_but_the_subject_may_be() -> None:
    turns = (_turn(1, "I fixd the speech to text servic"), _turn(2, "Nice.", user=False), _turn(3, "Ya"))

    def notes(aspect: str, statement: str):
        answer = ConversationReadingResponse.model_validate({**EMPTY, "person": [
            {"aspect": aspect, "statement": statement, "changed": False, "confidence": 0.8, "turns": [1]},
        ]})
        return build_reading(turns, answer, Understanding(), [], through_sequence=3, session_id="s").person

    assert notes("communication_style", "Terse, often with transcription-style slips") == ()
    assert notes("communication_style", "Words often run together") == ()
    assert [note.statement for note in notes("interests", "Works on speech-to-text and transcription")] == [
        "Works on speech-to-text and transcription"
    ], "a subject they care about is theirs"


def test_a_lesson_carries_advice_and_reaches_a_reply_as_it() -> None:
    from app.platform.assistant_memory.v2.understanding import Reading, project_readings
    from app.platform.assistant_memory.v2.understanding_view import UnderstandingItem, prompt_items

    turns = (_turn(1, "Explain it."), _turn(2, "A lecture.", user=False), _turn(3, "Stop."))
    (reaction,) = _reacting(turns, (3, "pushed_back", "Tunes out long lectures"))
    assert reaction.advice == "Make one point, then stop"
    projected = project_readings(SPACE, [_as_reading(10, Reading(through_sequence=3, reactions=(reaction,)))]).assertions
    assert sorted(item.predicate for item in projected) == ["advice_what_to_avoid", "lesson_what_to_avoid"]
    lesson = UnderstandingItem(key="k", kind="lesson", text="Tunes out long lectures", category="trait",
                               label="what_to_avoid", advice="Make one point, then stop")
    assert [item.text for item in prompt_items([lesson], "", now=NOW)] == [
        "Learned from how they react: Make one point, then stop"
    ]


def test_a_remembered_fact_says_when_it_was_noted_and_an_impression_does_not() -> None:
    from types import SimpleNamespace

    from app.conversation.contracts import PromptMemoryItem
    from app.platform.assistant_memory.v2.understanding_view import how_long_ago
    from app.platform.chat.prompt_rendering import _memory_section

    assert [how_long_ago(datetime(2026, 11, day, tzinfo=timezone.utc), NOW) for day in (5, 4, 1)] == [
        "earlier today", "yesterday", "4 days ago",
    ]
    assert how_long_ago(datetime(2026, 7, 1, tzinfo=timezone.utc), NOW) == "4 months ago"
    fact = PromptMemoryItem(memory_id="m1", content="Lives in Toronto.", scope="retrieved", category="fact",
                            revision=1, source="memory_v2", noted="3 months ago")
    trait = fact.model_copy(update={"memory_id": "m2", "content": "Teases back", "category": "trait"})
    rendered = _memory_section(SimpleNamespace(approved_memory=[fact, trait]))
    assert "- [memory-v2/fact; m1; noted 3 months ago] Lives in Toronto." in rendered
    assert "- [memory-v2/trait; m2] Teases back" in rendered


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("", "sonnet"), ("claude-opus-5-5", "claude-opus-5-5")],
)
def test_reading_does_not_use_the_fast_live_model(monkeypatch, configured: str, expected: str) -> None:
    from app.providers import service as provider_service

    live = ClaudeCliProvider(ProviderConfig(provider_type="claude_cli", model="claude-haiku-4-5-20251001"))
    monkeypatch.setattr(provider_service, "get_provider", lambda _name=None: live)
    monkeypatch.setenv("OMNIX_MEMORY_STRUCTURED_EXTRACTION_MODE", "auto")
    monkeypatch.setenv("OMNIX_MEMORY_READING_MODEL", configured)
    reader = module.default_conversation_reader()
    assert reader is not None and reader.model_id == expected
    assert live.config.model == "claude-haiku-4-5-20251001", "live replies keep their model"
