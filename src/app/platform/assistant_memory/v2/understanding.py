"""What a character has come to understand about the person it talks to.

A background reader writes one ``conversation_reading`` observation per stretch
of conversation. Those are the only place this understanding is authored:
notes on the person, connections between things they mentioned, how the
relationship stands, their moods and what happened are all projected from the
readings here, deterministically and with no model, so a governance rebuild can
replay them. The model's words reach this module as a proposal the reader has
already validated.

Forgetting rewrites the readings that hold the item and purges the originals,
so the text leaves the log and the rebuild removes it from every derived table.
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from app.persistence.database import PostgresDatabase

from .contracts import (
    AffectObservation,
    Episode,
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemorySpaceKey,
    Observation,
    ObservationProvenance,
    RelationshipMetric,
    RelationshipState,
    VisibilityScope,
)
from .observation_store import ObservationAppendRequest

READING_EVENT = "conversation_reading"
USER_TURN_EVENT = "user_said"
ASSISTANT_TURN_EVENT = "assistant_generated"
TURN_EVENTS = (USER_TURN_EVENT, ASSISTANT_TURN_EVENT)
DERIVATION = "memory-v2-understanding@1"
READING_SCHEMA = "memory-v2-conversation-reading@1"
ACTOR = "memory-v2-understanding"

# The only things a note on the person may be about; health, beliefs and the like have no aspect.
PERSON_ASPECTS = (
    "communication_style",
    "humor",
    "interests",
    "values",
    "temperament",
    "what_helps",
    "what_to_avoid",
)
MOODS = (
    "happy",
    "excited",
    "calm",
    "affectionate",
    "playful",
    "curious",
    "bored",
    "tired",
    "stressed",
    "anxious",
    "sad",
    "frustrated",
    "angry",
)
# How the person reacted to a reply, after VoiceMem's reaction attribution (rightbrain/brain.py).
REACTIONS = ("corrected", "pushed_back", "brushed_off", "thanked", "approved", "mood_changed")
# As there: a correction or pushback says the reply did not help, thanks or approval that it did,
# whatever the model thinks; for the rest its judgement stands.
REACTION_HELPED = {"corrected": False, "pushed_back": False, "thanked": True, "approved": True}
FORGET_KINDS = (
    "person", "earlier", "connection", "relationship", "mood", "episode", "lesson", "trigger",
    "stance", "promise", "joke",
)
USER_ENTITY = "The user"
_USER_SPELLINGS = frozenset({"user", "the user", "the person", "me", "i"})
_MOODS_KEPT = 50
_LESSONS_KEPT = 40
_TRIGGERS_KEPT = 40
_EARLIER_KEPT = 3  # views a note turned away from, newest last
_TOPICS_KEPT = 3
TOPIC_SEPARATOR = "\x1f"  # never in a cleaned name: str.split() treats it as whitespace
# A trigger comes back only when a turn names what it concerns, never as retrieval's catch-all.
TRIGGER_ID_PREFIX = "understanding:trigger:"
STANCE_ID_PREFIX = "understanding:stance:"
PROMISE_ID_PREFIX = "understanding:promise:"
JOKE_ID_PREFIX = "understanding:joke:"
ADVICE_ID_PREFIX = "understanding:advice:"
# What the prompt takes from the understanding alone: retrieval would return them worded differently (notes
# and lessons as plain statements, not as guidance), or when unrelated.
UNDERSTANDING_ONLY_PREFIXES = (
    TRIGGER_ID_PREFIX, STANCE_ID_PREFIX, PROMISE_ID_PREFIX, JOKE_ID_PREFIX,
    "understanding:person:", "understanding:lesson:", ADVICE_ID_PREFIX,
)
_PROMISES_KEPT = 20
_JOKES_KEPT = 20
_READINGS_LOADED = 2000


class PersonNote(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    aspect: str
    statement: str = Field(min_length=1, max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[str, ...] = ()
    # It turns the known note around rather than refining it, so the known one is kept as an earlier view.
    replaces_known: bool = False


class Connection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1, max_length=120)
    relation: str = Field(min_length=1, max_length=120)
    object: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[str, ...] = ()


class RelationshipReading(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    interpretation: str = Field(min_length=1, max_length=600)
    closeness: float | None = Field(default=None, ge=0.0, le=1.0)
    trust: float | None = Field(default=None, ge=0.0, le=1.0)
    ease: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[str, ...] = ()


class MoodReading(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str
    observed_at: datetime
    emotion: str
    valence: float = Field(ge=-1.0, le=1.0)
    arousal: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class EpisodeReading(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=800)
    importance: float = Field(ge=0.0, le=1.0)
    observation_ids: tuple[str, ...] = Field(min_length=1)
    started_at: datetime
    ended_at: datetime


class ReactionReading(BaseModel):
    """The person reacting to a reply, and the lasting pattern about them it shows.

    One piece of evidence for a lesson: every reaction with the same ``lesson_key``
    is the same pattern seen again, worded as it was first seen.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str  # the person's turn
    reply_id: str  # the reply they reacted to
    observed_at: datetime
    kind: str
    helped: bool
    reaction: str = Field(min_length=1, max_length=200)
    why: str = Field(min_length=1, max_length=200)
    lesson_key: str = Field(min_length=1, max_length=64)
    aspect: str
    lesson: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    advice: str | None = Field(default=None, max_length=200)  # what to do from now on: VoiceMem's next_time


class TriggerReading(BaseModel):
    """What brings on a feeling in the person, as it would happen again, and what it concerns.

    VoiceMem's situation pattern ("tense before design reviews"), anchored to the
    things it is about so that naming one brings it back. Every trigger with the
    same ``trigger_key`` is the same pattern seen again, worded as first seen.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trigger_key: str = Field(min_length=1, max_length=64)
    emotion: str
    pattern: str = Field(min_length=1, max_length=120)
    about: tuple[str, ...] = Field(min_length=1, max_length=_TOPICS_KEPT)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[str, ...] = ()
    observed_at: datetime


class StanceReading(BaseModel):
    """How the owner's own attitude toward the person has come to stand, spoken to the owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[str, ...] = ()


class PromiseReading(BaseModel):
    """Something the owner said it would do for or with the person, not yet done; evidence is its own turns."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    promise_key: str = Field(min_length=1, max_length=64)
    what: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[str, ...] = ()
    observed_at: datetime


class JokeReading(BaseModel):
    """A running joke or shared bit the two came back to; the same key seen again is the same joke."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    joke_key: str = Field(min_length=1, max_length=64)
    joke: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[str, ...] = ()
    observed_at: datetime


class Reading(BaseModel):
    """One stretch of conversation, read. ``through_sequence`` is the last turn it covers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    through_sequence: int = Field(ge=0)
    session_id: str | None = None
    from_owner: bool = False  # the person corrected it themselves: no model may overwrite a note
    person: tuple[PersonNote, ...] = ()
    connections: tuple[Connection, ...] = ()
    ended_connections: tuple[str, ...] = ()
    relationship: RelationshipReading | None = None
    moods: tuple[MoodReading, ...] = ()
    episode: EpisodeReading | None = None
    reactions: tuple[ReactionReading, ...] = ()
    triggers: tuple[TriggerReading, ...] = ()
    # The owner's own side: how it has come to stand toward the person, what it promised, what they joke about.
    stance: StanceReading | None = None
    promises: tuple[PromiseReading, ...] = ()
    kept_promises: tuple[str, ...] = ()
    jokes: tuple[JokeReading, ...] = ()


def _digest(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _space_id(space: MemorySpaceKey, scope_id: str) -> str:
    return _digest(space.principal_id, space.owner_type, space.owner_id, scope_id)[:32]


def _normal(text: str) -> str:
    return " ".join(text.split()).casefold()


def connection_key(subject: str, relation: str, object_: str) -> str:
    return _digest(_normal(subject), _normal(relation), _normal(object_))[:32]


def lesson_key(aspect: str, lesson: str) -> str:
    return _digest(aspect, _normal(lesson).rstrip("."))[:32]


def trigger_key(emotion: str, pattern: str) -> str:
    return _digest("trigger", emotion, _normal(pattern).rstrip("."))[:32]


def promise_key(what: str) -> str:
    return _digest("promise", _normal(what).rstrip("."))[:32]


def joke_key(joke: str) -> str:
    return _digest("joke", _normal(joke).rstrip("."))[:32]


def _slug(relation: str) -> str:
    return "_".join(relation.split())[:160] or "relates_to"


def reading_of(observation: Observation) -> Reading | None:
    try:
        return Reading.model_validate(dict(observation.payload))
    except ValueError:  # a purged reading's payload is gone, and it would not be listed anyway
        return None


@dataclass
class Understanding:
    """Everything the readings of one person add up to."""

    notes: dict[str, tuple[PersonNote, Observation, int]] = field(default_factory=dict)
    # Per aspect: a note the current one turned away from, the reading it came from, and when it changed.
    earlier: dict[str, list[tuple[PersonNote, Observation, datetime]]] = field(default_factory=dict)
    corrected_aspects: set[str] = field(default_factory=set)
    links: dict[str, tuple[Connection, Observation, datetime | None]] = field(default_factory=dict)
    relationship: tuple[RelationshipReading, Observation, int] | None = None
    moods: list[tuple[MoodReading, Observation]] = field(default_factory=list)
    episodes: list[tuple[EpisodeReading, Observation]] = field(default_factory=list)
    lessons: dict[str, list[tuple[ReactionReading, Observation]]] = field(default_factory=dict)
    triggers: dict[str, list[tuple[TriggerReading, Observation]]] = field(default_factory=dict)
    stance: tuple[StanceReading, Observation, int] | None = None
    # Per promise: what was promised, the reading it came from, and when it was kept or dropped (None: still open).
    promises: dict[str, tuple[PromiseReading, Observation, datetime | None]] = field(default_factory=dict)
    jokes: dict[str, list[tuple[JokeReading, Observation]]] = field(default_factory=dict)
    read_through: int = 0


def _ordered(readings: Iterable[Observation]) -> list[tuple[Observation, Reading]]:
    parsed = [(item, reading_of(item)) for item in readings]
    kept = [(item, reading) for item, reading in parsed if reading is not None]
    return sorted(kept, key=lambda pair: (pair[1].through_sequence, pair[0].authority_sequence))


def add_up(readings: Iterable[Observation], *, active: frozenset[str] | None = None) -> Understanding:
    """Replay readings in order. ``active`` narrows evidence to what has not been forgotten."""

    def live(ids: Iterable[str]) -> tuple[str, ...]:
        return tuple(item for item in ids if active is None or item in active)

    result = Understanding()
    spelling: dict[str, str] = {}

    def spelled(name: str) -> str:
        key = _normal(name)
        if key in _USER_SPELLINGS:
            return USER_ENTITY
        return spelling.setdefault(key, " ".join(name.split()))

    for observation, reading in _ordered(readings):
        result.read_through = max(result.read_through, reading.through_sequence)
        for note in reading.person:
            if note.aspect in result.corrected_aspects and not reading.from_owner:
                continue
            evidence = live(note.evidence)
            if not evidence and not reading.from_owner:
                continue
            previous = result.notes.get(note.aspect)
            if reading.from_owner:
                result.earlier.pop(note.aspect, None)  # the person's own wording stands alone
            elif previous is not None and note.replaces_known:
                history = [*result.earlier.get(note.aspect, []), (previous[0], previous[1], observation.occurred_at)]
                result.earlier[note.aspect] = history[-_EARLIER_KEPT:]
            revision = previous[2] + 1 if previous is not None else 1
            result.notes[note.aspect] = (note.model_copy(update={"evidence": evidence}), observation, revision)
            if reading.from_owner:
                result.corrected_aspects.add(note.aspect)
        for link in reading.connections:
            evidence = live(link.evidence)
            if not evidence:
                continue
            named = link.model_copy(update={
                "subject": spelled(link.subject), "object": spelled(link.object), "evidence": evidence,
            })
            result.links[connection_key(named.subject, named.relation, named.object)] = (named, observation, None)
        for key in reading.ended_connections:
            if key in result.links:
                link, source, _ended = result.links[key]
                result.links[key] = (link, source, observation.occurred_at)
        if reading.relationship is not None:
            evidence = live(reading.relationship.evidence)
            if evidence or reading.from_owner:
                revision = result.relationship[2] + 1 if result.relationship else 1
                result.relationship = (
                    reading.relationship.model_copy(update={"evidence": evidence}), observation, revision,
                )
        for mood in reading.moods:
            if active is None or mood.observation_id in active:
                result.moods.append((mood, observation))
        if reading.episode is not None:
            turns = live(reading.episode.observation_ids)
            if turns:
                result.episodes.append((reading.episode.model_copy(update={"observation_ids": turns}), observation))
        for reaction in reading.reactions:
            if active is None or reaction.observation_id in active:
                result.lessons.setdefault(reaction.lesson_key, []).append((reaction, observation))
        for trigger in reading.triggers:
            evidence = live(trigger.evidence)
            if evidence:
                result.triggers.setdefault(trigger.trigger_key, []).append(
                    (trigger.model_copy(update={"evidence": evidence}), observation)
                )
        _add_own_side(result, observation, reading, live)
    result.moods = sorted(result.moods, key=lambda pair: pair[0].observed_at)[-_MOODS_KEPT:]
    result.lessons = _newest(result.lessons, _LESSONS_KEPT)
    result.triggers = _newest(result.triggers, _TRIGGERS_KEPT)
    result.jokes = _newest(result.jokes, _JOKES_KEPT)
    by_age = sorted(result.promises.items(), key=lambda pair: pair[1][0].observed_at)
    result.promises = dict(by_age[-_PROMISES_KEPT:])
    return result


def _add_own_side(result: Understanding, observation: Observation, reading: Reading, live: Any) -> None:
    if reading.stance is not None:
        evidence = live(reading.stance.evidence)
        if evidence:
            revision = result.stance[2] + 1 if result.stance else 1
            result.stance = (reading.stance.model_copy(update={"evidence": evidence}), observation, revision)
    for promise in reading.promises:
        evidence = live(promise.evidence)
        if evidence and promise.promise_key not in result.promises:
            result.promises[promise.promise_key] = (promise.model_copy(update={"evidence": evidence}), observation, None)
    for key in reading.kept_promises:
        if key in result.promises and result.promises[key][2] is None:
            promise, source, _kept = result.promises[key]
            result.promises[key] = (promise, source, observation.occurred_at)
    for joke in reading.jokes:
        evidence = live(joke.evidence)
        if evidence:
            result.jokes.setdefault(joke.joke_key, []).append((joke.model_copy(update={"evidence": evidence}), observation))


def _newest(patterns: dict[str, list[Any]], kept: int) -> dict[str, list[Any]]:
    """The patterns seen most recently: each entry lists (item with observed_at, reading)."""
    recent = sorted(patterns.items(), key=lambda pair: max(item.observed_at for item, _ in pair[1]))
    return dict(recent[-kept:])


def topics_of(seen: Iterable[tuple[TriggerReading, Observation]]) -> tuple[str, ...]:
    """What a trigger concerns, across every time it was seen, each name once however it was spelled."""
    names: dict[str, str] = {}
    for trigger, _reading in seen:
        for name in trigger.about:
            names.setdefault(_normal(name), name)
    return tuple(names.values())[:_TOPICS_KEPT]


def episode_key(space: MemorySpaceKey, episode: EpisodeReading, scope_id: str) -> str:
    return f"understanding:episode:{_digest(_space_id(space, scope_id), episode.observation_ids[0])[:40]}"


def mood_key(space: MemorySpaceKey, mood: MoodReading, scope_id: str) -> str:
    return f"understanding:mood:{_digest(_space_id(space, scope_id), mood.observation_id)[:40]}"


def _note_id(space: MemorySpaceKey, scope_id: str, aspect: str) -> str:
    return f"understanding:person:{_space_id(space, scope_id)}:{aspect}"


def _link_id(space: MemorySpaceKey, scope_id: str, key: str) -> str:
    return f"understanding:link:{_space_id(space, scope_id)}:{key}"


def relationship_id(space: MemorySpaceKey, scope_id: str) -> str:
    return f"understanding:relationship:{_space_id(space, scope_id)}"


def _lesson_id(space: MemorySpaceKey, scope_id: str, key: str) -> str:
    return f"understanding:lesson:{_space_id(space, scope_id)}:{key}"


@dataclass(frozen=True)
class Projected:
    assertions: tuple[GraphAssertion, ...] = ()
    episodes: tuple[Episode, ...] = ()
    relationships: tuple[RelationshipState, ...] = ()
    affect: tuple[AffectObservation, ...] = ()


def _evidence(observation: Observation, turns: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((observation.observation_id, *turns)))


def _project_one(space: MemorySpaceKey, scope: VisibilityScope, understood: Understanding) -> Projected:
    person = GraphEntityRef(entity_id=USER_ENTITY, entity_type="person")
    assertions: list[GraphAssertion] = []
    for aspect, (note, observation, revision) in understood.notes.items():
        assertions.append(GraphAssertion(
            assertion_id=_note_id(space, scope.scope_id, aspect),
            space=space,
            visibility_scopes=(scope,),
            subject=person,
            predicate=f"person_{aspect}",
            object=GraphValue(kind="literal", literal=note.statement),
            domain="trait",
            confidence=note.confidence,
            valid_from=observation.occurred_at,
            evidence_observation_ids=_evidence(observation, note.evidence),
            derivation_version=DERIVATION,
            revision=revision,
        ))
    for key, seen in understood.lessons.items():
        first, first_reading = seen[0]
        assertions.append(GraphAssertion(
            assertion_id=_lesson_id(space, scope.scope_id, key),
            space=space,
            visibility_scopes=(scope,),
            subject=person,
            predicate=f"lesson_{first.aspect}",
            object=GraphValue(kind="literal", literal=first.lesson),
            domain="trait",
            confidence=max(reaction.confidence for reaction, _ in seen),
            valid_from=first_reading.occurred_at,
            evidence_observation_ids=tuple(dict.fromkeys(
                item for reaction, reading in seen for item in (reading.observation_id, reaction.observation_id)
            )),
            derivation_version=DERIVATION,
            revision=len(seen),  # how often it was seen
        ))
        # The newest advice: a lesson's wording stays as first seen, but what to do about it can improve.
        advice = next((reaction.advice for reaction, _ in reversed(seen) if reaction.advice), None)
        if advice is not None:
            assertions.append(GraphAssertion(
                assertion_id=f"{ADVICE_ID_PREFIX}{_space_id(space, scope.scope_id)}:{key}",
                space=space,
                visibility_scopes=(scope,),
                subject=person,
                predicate=f"advice_{first.aspect}",
                object=GraphValue(kind="literal", literal=advice),
                domain="trait",
                confidence=max(reaction.confidence for reaction, _ in seen),
                valid_from=first_reading.occurred_at,
                evidence_observation_ids=tuple(dict.fromkeys(
                    item for reaction, reading in seen for item in (reading.observation_id, reaction.observation_id)
                )),
                derivation_version=DERIVATION,
                revision=len(seen),
            ))
    for aspect, history in understood.earlier.items():
        for note, source, changed_at in history:
            assertions.append(GraphAssertion(
                assertion_id=f"{_note_id(space, scope.scope_id, aspect)}:earlier:{_digest(source.observation_id)[:16]}",
                space=space,
                visibility_scopes=(scope,),
                subject=person,
                predicate=f"person_{aspect}",
                object=GraphValue(kind="literal", literal=note.statement),
                domain="trait",
                confidence=note.confidence,
                valid_from=source.occurred_at,
                valid_until=max(changed_at, source.occurred_at),
                evidence_observation_ids=_evidence(source, note.evidence),
                derivation_version=DERIVATION,
                status="superseded",
            ))
    for key, seen in understood.triggers.items():
        first, first_reading = seen[0]
        assertions.append(GraphAssertion(
            assertion_id=f"{TRIGGER_ID_PREFIX}{_space_id(space, scope.scope_id)}:{key}",
            space=space,
            visibility_scopes=(scope,),
            # What it concerns, so that a turn naming one finds it.
            subject=GraphEntityRef(entity_id=TOPIC_SEPARATOR.join(topics_of(seen)), entity_type="topics"),
            predicate=f"trigger_{first.emotion}",
            object=GraphValue(kind="literal", literal=first.pattern),
            domain="trait",
            confidence=max(trigger.confidence for trigger, _ in seen),
            valid_from=first_reading.occurred_at,
            evidence_observation_ids=tuple(dict.fromkeys(
                item for trigger, reading in seen for item in (reading.observation_id, *trigger.evidence)
            )),
            derivation_version=DERIVATION,
            revision=len(seen),
        ))
    assertions.extend(_own_side_assertions(space, scope, understood))
    for key, (link, observation, ended_at) in understood.links.items():
        assertions.append(GraphAssertion(
            assertion_id=_link_id(space, scope.scope_id, key),
            space=space,
            visibility_scopes=(scope,),
            subject=GraphEntityRef(entity_id=link.subject, entity_type="thing"),
            predicate=_slug(link.relation),
            object=GraphValue(kind="entity", entity=GraphEntityRef(entity_id=link.object, entity_type="thing")),
            domain="fact",
            confidence=link.confidence,
            valid_from=observation.occurred_at,
            valid_until=max(ended_at, observation.occurred_at) if ended_at is not None else None,
            evidence_observation_ids=_evidence(observation, link.evidence),
            derivation_version=DERIVATION,
            status="superseded" if ended_at is not None else "active",
        ))
    relationships: list[RelationshipState] = []
    if understood.relationship is not None:
        reading, observation, revision = understood.relationship
        evidence = _evidence(observation, reading.evidence)
        relationships.append(RelationshipState(
            relationship_id=relationship_id(space, scope.scope_id),
            space=space,
            subject=GraphEntityRef(entity_id=f"{space.owner_type}:{space.owner_id}", entity_type=space.owner_type),
            counterpart=person,
            metrics=tuple(
                RelationshipMetric(
                    name=name, value=cast(float, value), confidence=reading.confidence, evidence_observation_ids=evidence,
                )
                for name, value in (("closeness", reading.closeness), ("trust", reading.trust), ("ease", reading.ease))
                if value is not None
            ),
            prompt_interpretation=reading.interpretation,
            evidence_observation_ids=evidence,
            derivation_version=DERIVATION,
            revision=revision,
        ))
    episodes = tuple(
        Episode(
            episode_id=episode_key(space, episode, scope.scope_id),
            space=space,
            visibility_scopes=(scope,),
            title=episode.title,
            summary=episode.summary,
            started_at=episode.started_at,
            ended_at=max(episode.ended_at, episode.started_at),
            observation_ids=_evidence(observation, episode.observation_ids),
            importance=episode.importance,
            derivation_version=DERIVATION,
        )
        for episode, observation in understood.episodes
    )
    affect = tuple(
        AffectObservation(
            affect_id=mood_key(space, mood, scope.scope_id),
            space=space,
            source_observation_id=mood.observation_id,
            source="semantic",
            observed_at=mood.observed_at,
            valence=mood.valence,
            arousal=mood.arousal,
            emotion_distribution={mood.emotion: mood.confidence},
            confidence=mood.confidence,
            model_version=DERIVATION,
        )
        for mood, _observation in understood.moods
    )
    return Projected(tuple(assertions), episodes, tuple(relationships), affect)


def _own_side_assertions(space: MemorySpaceKey, scope: VisibilityScope, understood: Understanding) -> list[GraphAssertion]:
    owner = GraphEntityRef(entity_id=f"{space.owner_type}:{space.owner_id}", entity_type=space.owner_type)
    space_id = _space_id(space, scope.scope_id)

    def told(assertion_id: str, predicate: str, literal: str, domain: Any, **fields: Any) -> GraphAssertion:
        return GraphAssertion(
            assertion_id=assertion_id, space=space, visibility_scopes=(scope,), subject=owner, predicate=predicate,
            object=GraphValue(kind="literal", literal=literal), domain=domain, derivation_version=DERIVATION, **fields,
        )

    assertions: list[GraphAssertion] = []
    if understood.stance is not None:
        stance, observation, revision = understood.stance
        assertions.append(told(
            f"{STANCE_ID_PREFIX}{space_id}", "own_stance", stance.statement, "relationship",
            confidence=stance.confidence, valid_from=observation.occurred_at,
            evidence_observation_ids=_evidence(observation, stance.evidence), revision=revision,
        ))
    for key, (promise, observation, kept_at) in understood.promises.items():
        assertions.append(told(
            f"{PROMISE_ID_PREFIX}{space_id}:{key}", "promised", promise.what, "open_loop",
            confidence=promise.confidence, valid_from=observation.occurred_at,
            valid_until=max(kept_at, observation.occurred_at) if kept_at is not None else None,
            status="superseded" if kept_at is not None else "active",
            evidence_observation_ids=_evidence(observation, promise.evidence),
        ))
    for key, seen in understood.jokes.items():
        first, first_reading = seen[0]
        assertions.append(told(
            f"{JOKE_ID_PREFIX}{space_id}:{key}", "running_joke", first.joke, "relationship",
            confidence=max(joke.confidence for joke, _ in seen), valid_from=first_reading.occurred_at,
            evidence_observation_ids=tuple(dict.fromkeys(
                item for joke, reading in seen for item in (reading.observation_id, *joke.evidence)
            )),
            revision=len(seen),
        ))
    return assertions


def project_readings(
    space: MemorySpaceKey,
    readings: Iterable[Observation],
    *,
    active: frozenset[str] | None = None,
) -> Projected:
    """The derived state of every reading, one understanding per person the space talks to."""
    by_scope: dict[tuple[str, str], list[Observation]] = {}
    for reading in readings:
        scope = reading.visibility_scope
        by_scope.setdefault((scope.kind, scope.scope_id), []).append(reading)
    parts = [
        _project_one(space, VisibilityScope(kind=cast(Any, kind), scope_id=scope_id), add_up(items, active=active))
        for (kind, scope_id), items in sorted(by_scope.items())
    ]
    return Projected(
        assertions=tuple(item for part in parts for item in part.assertions),
        episodes=tuple(item for part in parts for item in part.episodes),
        relationships=tuple(item for part in parts for item in part.relationships),
        affect=tuple(item for part in parts for item in part.affect),
    )


# -- the log -------------------------------------------------------------------


def _space_values(space: MemorySpaceKey) -> tuple[str, str, str]:
    return space.principal_id, space.owner_type, space.owner_id


def active_readings(database: PostgresDatabase, space: MemorySpaceKey) -> tuple[Observation, ...]:
    from .observation_store import _OBSERVATION_COLUMNS, _observation_from_row

    columns = ", ".join(f"o.{name.strip()}" for name in _OBSERVATION_COLUMNS.split(","))
    with database.transaction() as connection:
        rows = connection.execute(
            f"""
            SELECT {columns}
              FROM omnix_memory_v2_observations o
              LEFT JOIN omnix_memory_v2_observation_dispositions d
                ON d.observation_id = o.observation_id
             WHERE o.principal_id = %s AND o.owner_type = %s AND o.owner_id = %s
               AND o.event_type = %s
               AND COALESCE(d.state, 'active') = 'active'
             ORDER BY o.authority_sequence
             LIMIT {_READINGS_LOADED}
            """,
            (*_space_values(space), READING_EVENT),
        ).fetchall()
    return tuple(_observation_from_row(row) for row in rows)


def _still_active(database: PostgresDatabase, space: MemorySpaceKey, ids: Iterable[str]) -> frozenset[str]:
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return frozenset()
    with database.transaction() as connection:
        rows = connection.execute(
            """
            SELECT o.observation_id
              FROM omnix_memory_v2_observations o
              LEFT JOIN omnix_memory_v2_observation_dispositions d
                ON d.observation_id = o.observation_id
             WHERE o.principal_id = %s AND o.owner_type = %s AND o.owner_id = %s
               AND o.observation_id = ANY(%s)
               AND COALESCE(d.state, 'active') = 'active'
             LIMIT %s
            """,
            (*_space_values(space), wanted, len(wanted)),
        ).fetchall()
    return frozenset(str(row[0]) for row in rows)


def _evidence_named(readings: Iterable[Observation]) -> list[str]:
    named: list[str] = []
    for observation in readings:
        reading = reading_of(observation)
        if reading is None:
            continue
        named.extend(item for note in reading.person for item in note.evidence)
        named.extend(item for link in reading.connections for item in link.evidence)
        named.extend(reading.relationship.evidence if reading.relationship else ())
        named.extend(mood.observation_id for mood in reading.moods)
        named.extend(reading.episode.observation_ids if reading.episode else ())
        named.extend(reaction.observation_id for reaction in reading.reactions)
        named.extend(item for trigger in reading.triggers for item in trigger.evidence)
        named.extend(reading.stance.evidence if reading.stance else ())
        named.extend(item for promise in reading.promises for item in promise.evidence)
        named.extend(item for joke in reading.jokes for item in joke.evidence)
    return named


class MemoryPlanner:
    """The derive plan for everything in a memory space: curated records and readings, no model.

    The one planner of the space's derive job. A rebuild deletes whatever its
    plan leaves out, so a plan that ignored readings would erase the understanding.
    """

    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database

    def __call__(self, space: MemorySpaceKey, window: tuple[Observation, ...], _existing: tuple[Any, ...]) -> Any:
        from .convergence import DerivedPlanPayload
        from .curated_projection import curated_projector
        from .curated_records import CURATED_SCHEMA

        curated = curated_projector(window)
        if not any(item.event_type == READING_EVENT for item in window):
            return DerivedPlanPayload(assertions=curated, consolidator_version=CURATED_SCHEMA)
        readings = active_readings(self.database, space)
        projected = project_readings(
            space, readings, active=_still_active(self.database, space, _evidence_named(readings)),
        )
        return DerivedPlanPayload(
            assertions=(*curated, *projected.assertions),
            episodes=projected.episodes,
            relationships=projected.relationships,
            affect=projected.affect,
            consolidator_version=DERIVATION,
        )


def reading_request(
    space: MemorySpaceKey,
    scope: VisibilityScope,
    reading: Reading,
    *,
    occurred_at: datetime,
    provider_id: str | None = None,
    model_id: str | None = None,
) -> ObservationAppendRequest:
    return ObservationAppendRequest(
        space=space,
        visibility_scope=scope,
        event_type=READING_EVENT,
        occurred_at=occurred_at,
        provenance=ObservationProvenance(
            source_type="user" if reading.from_owner else "assistant",
            source_id=ACTOR,
            trust_level="user_explicit" if reading.from_owner else "assistant_inference",
            session_id=reading.session_id,
            provider_id=provider_id,
            model_id=model_id,
        ),
        # Never by content: that would find a purged twin and "succeed" without writing, losing a
        # correction made twice. Retries are safe anyway: a read stretch is no longer unread.
        idempotency_key=f"reading:{reading.through_sequence}:{uuid.uuid4().hex}",
        payload=reading.model_dump(mode="json"),
        schema_version=READING_SCHEMA,
    )


def _redact_decisions_after(connection: Any, space: MemorySpaceKey, sequence: int) -> None:
    """A plan re-emits every reading, so later decision sets hold a forgotten reading's text too."""
    stamp = datetime.now(timezone.utc)
    connection.execute(
        """
        UPDATE omnix_memory_v2_consolidation_decision_sets
           SET normalized_proposals = '[]'::jsonb,
               deterministic_decisions = '{"redacted":true}'::jsonb,
               redacted_at = COALESCE(redacted_at, %s),
               invalidated_at = COALESCE(invalidated_at, %s)
         WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
           AND input_observation_through >= %s
        """,
        (stamp, stamp, *_space_values(space), sequence),
    )


def purge_observations(
    runtime: Any, space: MemorySpaceKey, observations: Iterable[Observation], *, reason: str,
) -> int:
    """Purge observations (their text goes) and every decision set written since the first."""
    chosen = tuple(observations)
    if not chosen:
        return 0

    def decide(connection: Any) -> list[tuple[str, str, str]]:
        _redact_decisions_after(connection, space, min(item.authority_sequence for item in chosen))
        return [(item.observation_id, "purged", reason) for item in chosen]

    return int(runtime.govern_authoritative(space, decide, actor_id=ACTOR))


def _without(reading: Reading, space: MemorySpaceKey, scope_id: str, kind: str, key: str) -> Reading | None:
    """The reading with one item gone, or None when it does not hold that item."""
    update: dict[str, Any]
    if kind == "person":
        kept_notes = tuple(note for note in reading.person if note.aspect != key)
        if len(kept_notes) == len(reading.person):
            return None
        update = {"person": kept_notes}
    elif kind == "connection":
        kept_links = tuple(
            link for link in reading.connections
            if connection_key(link.subject, link.relation, link.object) != key
        )
        if len(kept_links) == len(reading.connections):
            return None
        update = {"connections": kept_links}
    elif kind == "relationship":
        if reading.relationship is None:
            return None
        update = {"relationship": None}
    elif kind == "mood":
        kept_moods = tuple(mood for mood in reading.moods if mood_key(space, mood, scope_id) != key)
        if len(kept_moods) == len(reading.moods):
            return None
        update = {"moods": kept_moods}
    elif kind == "episode":
        if reading.episode is None or episode_key(space, reading.episode, scope_id) != key:
            return None
        update = {"episode": None}
    elif kind == "lesson":
        kept_reactions = tuple(reaction for reaction in reading.reactions if reaction.lesson_key != key)
        if len(kept_reactions) == len(reading.reactions):
            return None
        update = {"reactions": kept_reactions}
    elif kind == "trigger":
        kept_triggers = tuple(trigger for trigger in reading.triggers if trigger.trigger_key != key)
        if len(kept_triggers) == len(reading.triggers):
            return None
        update = {"triggers": kept_triggers}
    elif kind == "stance":
        if reading.stance is None:
            return None
        update = {"stance": None}
    elif kind == "promise":
        kept_promises = tuple(promise for promise in reading.promises if promise.promise_key != key)
        if len(kept_promises) == len(reading.promises) and key not in reading.kept_promises:
            return None
        update = {"promises": kept_promises, "kept_promises": tuple(item for item in reading.kept_promises if item != key)}
    elif kind == "joke":
        kept_jokes = tuple(joke for joke in reading.jokes if joke.joke_key != key)
        if len(kept_jokes) == len(reading.jokes):
            return None
        update = {"jokes": kept_jokes}
    else:
        raise ValueError(f"unknown understanding kind: {kind}")
    return reading.model_copy(update=update)


def forget_item(runtime: Any, space: MemorySpaceKey, scope_id: str, kind: str, key: str) -> int:
    """Remove one item from every reading that holds it. Returns the readings rewritten.

    The earlier views of a note go as that aspect's note in every reading but the
    one the current note came from.
    """
    rewritten: list[Observation] = []
    readings = [item for item in active_readings(runtime.database, space) if item.visibility_scope.scope_id == scope_id]
    spared: str | None = None
    if kind == "earlier":
        current = add_up(readings).notes.get(key)
        if current is None:
            return 0
        spared, kind = current[1].observation_id, "person"
    for observation in readings:
        if observation.observation_id == spared:
            continue
        reading = reading_of(observation)
        kept = _without(reading, space, scope_id, kind, key) if reading is not None else None
        if kept is None:
            continue
        runtime.append_authoritative_next(
            reading_request(space, observation.visibility_scope, kept, occurred_at=observation.occurred_at),
            actor_id=ACTOR,
        )
        rewritten.append(observation)
    purge_observations(runtime, space, rewritten, reason="forgotten in the memory tab")
    return len(rewritten)


def correct_item(
    runtime: Any, space: MemorySpaceKey, scope: VisibilityScope, kind: str, key: str, text: str, *, at: datetime,
) -> None:
    """The person's own wording replaces what was read."""
    forget_item(runtime, space, scope.scope_id, kind, key)
    understood = add_up(item for item in active_readings(runtime.database, space) if item.visibility_scope == scope)
    if kind == "person":
        correction = Reading(
            through_sequence=understood.read_through,
            from_owner=True,
            person=(PersonNote(aspect=key, statement=text, confidence=1.0),),
        )
    elif kind == "relationship":
        correction = Reading(
            through_sequence=understood.read_through,
            from_owner=True,
            relationship=RelationshipReading(interpretation=text, confidence=1.0),
        )
    else:
        raise ValueError(f"{kind} cannot be reworded")
    runtime.append_authoritative_next(reading_request(space, scope, correction, occurred_at=at), actor_id=ACTOR)


def forget_session(runtime: Any, space: MemorySpaceKey, session_id: str) -> int:
    """A deleted chat's turns leave the log, with every reading made from them or after them.

    A later reading saw an earlier one's conclusions, so it may carry the chat's
    content too. Turns that remain are read again by the next sweep.
    """
    from .observation_store import _OBSERVATION_COLUMNS, _observation_from_row

    columns = ", ".join(f"o.{name.strip()}" for name in _OBSERVATION_COLUMNS.split(","))
    with runtime.database.transaction() as connection:
        rows = connection.execute(
            f"""
            SELECT {columns}
              FROM omnix_memory_v2_observations o
              LEFT JOIN omnix_memory_v2_observation_dispositions d
                ON d.observation_id = o.observation_id
             WHERE o.principal_id = %s AND o.owner_type = %s AND o.owner_id = %s
               AND o.provenance->>'session_id' = %s
               AND o.event_type = ANY(%s)
               AND COALESCE(d.state, 'active') <> 'purged'
             ORDER BY o.authority_sequence
             LIMIT 20000
            """,
            (*_space_values(space), session_id, [*TURN_EVENTS, READING_EVENT]),
        ).fetchall()
    chosen = [_observation_from_row(row) for row in rows]
    first_turn = min((item.authority_sequence for item in chosen if item.event_type in TURN_EVENTS), default=None)
    if first_turn is not None:
        known = {item.observation_id for item in chosen}
        for observation in active_readings(runtime.database, space):
            reading = reading_of(observation)
            if (
                reading is not None
                and not reading.from_owner  # the person's own words came from no chat
                and reading.through_sequence >= first_turn
                and observation.observation_id not in known
            ):
                chosen.append(observation)
    return purge_observations(runtime, space, chosen, reason="chat deleted")


def forget_chat_everywhere(runtime: Any, principal_id: str, session_id: str) -> int:
    """Forget a deleted chat in every owner's log: a chat can be switched between characters,
    so the character it ends with need not be the only one that holds its turns."""
    with runtime.database.transaction() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT owner_type, owner_id
              FROM omnix_memory_v2_observations
             WHERE principal_id = %s
               AND provenance->>'session_id' = %s
               AND event_type = ANY(%s)
             LIMIT 256
            """,
            (principal_id, session_id, [*TURN_EVENTS, READING_EVENT]),
        ).fetchall()
    return sum(
        forget_session(
            runtime,
            MemorySpaceKey(principal_id=principal_id, owner_type=cast(Any, str(row[0])), owner_id=str(row[1])),
            session_id,
        )
        for row in rows
    )


__all__ = [
    "ASSISTANT_TURN_EVENT",
    "Connection",
    "DERIVATION",
    "EpisodeReading",
    "FORGET_KINDS",
    "MOODS",
    "MemoryPlanner",
    "MoodReading",
    "PERSON_ASPECTS",
    "PersonNote",
    "REACTIONS",
    "REACTION_HELPED",
    "READING_EVENT",
    "ReactionReading",
    "Reading",
    "RelationshipReading",
    "ADVICE_ID_PREFIX",
    "JOKE_ID_PREFIX",
    "JokeReading",
    "PROMISE_ID_PREFIX",
    "PromiseReading",
    "STANCE_ID_PREFIX",
    "StanceReading",
    "TOPIC_SEPARATOR",
    "TRIGGER_ID_PREFIX",
    "UNDERSTANDING_ONLY_PREFIXES",
    "TURN_EVENTS",
    "TriggerReading",
    "USER_TURN_EVENT",
    "Understanding",
    "active_readings",
    "add_up",
    "connection_key",
    "correct_item",
    "forget_chat_everywhere",
    "forget_item",
    "forget_session",
    "joke_key",
    "lesson_key",
    "project_readings",
    "promise_key",
    "purge_observations",
    "reading_of",
    "reading_request",
    "topics_of",
    "trigger_key",
]
