"""Reading the understanding back: for every reply's prompt, and for the Memory tab.

``understanding`` projects the readings into the derived tables; this module reads
them in one short transaction on a reply's path, and changes them only through
``understanding``'s forgetting and correcting.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from app.persistence.database import PostgresDatabase

from .contracts import MemorySpaceKey, VisibilityScope
from .understanding import (
    DERIVATION,
    FORGET_KINDS,
    PERSON_ASPECTS,
    TOPIC_SEPARATOR,
    USER_ENTITY,
    connection_key,
    correct_item,
    forget_item,
)

logger = logging.getLogger(__name__)

_LINKS_LOADED = 200
_TRAIT_ROWS = 160  # notes, lessons and triggers: each kind is kept to a few dozen
_EARLIER_ROWS = 32
_LESSONS_PROMPTED = 6
_TRIGGERS_PROMPTED = 3
_OWN_SIDE_ROWS = 64
_PROMISES_PROMPTED = 5
_JOKES_PROMPTED = 3
_OWN_SIDE = {"own_stance": "stance", "promised": "promise", "running_joke": "joke"}


@dataclass(frozen=True)
class UnderstandingItem:
    key: str
    kind: str
    text: str
    category: str
    at: datetime | None = None
    label: str | None = None
    corrected: bool = False
    metrics: tuple[tuple[str, float], ...] = ()
    seen: int = 1
    about: tuple[str, ...] = ()
    advice: str | None = None


def _visible(scopes: Any, visible: tuple[VisibilityScope, ...]) -> bool:
    allowed = {(scope.kind, scope.scope_id) for scope in visible}
    return any((str(scope.get("kind")), str(scope.get("scope_id"))) in allowed for scope in scopes or ())


def how_long_ago(moment: datetime, now: datetime) -> str:
    """"3 days ago": the prompt states no date, so an age is what a reply can use."""
    days = (now.date() - moment.date()).days
    if days <= 0:
        return "earlier today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    return f"{days // 30} months ago"


def _when(moment: datetime, now: datetime) -> str:
    text = how_long_ago(moment, now)
    return text[0].upper() + text[1:]


def _join_policy(item_type: str, ref: str) -> str:
    return (
        "JOIN omnix_memory_v2_derived_policy_envelopes p"
        f" ON p.item_type = '{item_type}' AND p.ref_id = {ref}"
        " AND p.principal_id = %s AND p.owner_type = %s AND p.owner_id = %s"
    )


def _trait_item(row: Any) -> UnderstandingItem:
    predicate, text, at = str(row[0]), str(dict(row[1]).get("literal")), row[2]
    if predicate.startswith("advice_"):
        return UnderstandingItem(key=str(row[5]).rsplit(":", 1)[-1], kind="advice", text=text, category="trait", at=at)
    if predicate.startswith("lesson_"):
        return UnderstandingItem(
            key=str(row[5]).rsplit(":", 1)[-1], kind="lesson", text=text, category="trait", at=at,
            label=predicate.removeprefix("lesson_"), seen=int(row[6]),
        )
    if predicate.startswith("trigger_"):
        return UnderstandingItem(
            key=str(row[5]).rsplit(":", 1)[-1], kind="trigger", text=text, category="trait", at=at,
            label=predicate.removeprefix("trigger_"), seen=int(row[6]),
            about=tuple(str(row[7]).split(TOPIC_SEPARATOR)),
        )
    aspect = predicate.removeprefix("person_")
    return UnderstandingItem(
        key=aspect, kind="person", text=text, category="trait", at=at, label=aspect, corrected=float(row[4]) >= 1.0,
    )


def read_understanding(
    database: PostgresDatabase,
    space: MemorySpaceKey,
    visible: tuple[VisibilityScope, ...],
    *,
    episodes: int = 20,
    moods: int = 20,
) -> list[UnderstandingItem]:
    """The current understanding from the derived tables, in one short transaction."""
    values = (space.principal_id, space.owner_type, space.owner_id)
    items: list[UnderstandingItem] = []
    with database.transaction() as connection:
        rows = connection.execute(
            f"""
            SELECT r.relationship_id, r.prompt_interpretation, r.updated_at, p.effective_visibility, NULL,
                   (SELECT jsonb_object_agg(m.metric_name, m.metric_value)
                      FROM omnix_memory_v2_relationship_metrics m
                     WHERE m.relationship_id = r.relationship_id)
              FROM omnix_memory_v2_relationships r
              {_join_policy('relationship', 'r.relationship_id')}
             WHERE r.principal_id = %s AND r.owner_type = %s AND r.owner_id = %s AND r.status = 'active'
             LIMIT 8
            """,
            (*values, *values),
        ).fetchall()
        for row in rows:
            if _visible(row[3], visible):
                numbers = dict(row[5] or {})
                items.append(UnderstandingItem(
                    key="current", kind="relationship", text=str(row[1]), category="relationship", at=row[2],
                    corrected=not numbers,  # a reading always scores it; the person's own wording does not
                    metrics=tuple((str(name), float(value)) for name, value in sorted(numbers.items())),
                ))
        rows = connection.execute(
            f"""
            SELECT a.predicate, a.object_value, a.valid_from, p.effective_visibility, a.confidence,
                   a.assertion_id, a.revision, a.subject_entity_id
              FROM omnix_memory_v2_graph_assertions a
              {_join_policy('assertion', 'a.assertion_id')}
             WHERE a.principal_id = %s AND a.owner_type = %s AND a.owner_id = %s
               AND a.domain = 'trait' AND a.status = 'active' AND a.derivation_version = %s
             ORDER BY a.predicate, a.assertion_id
             LIMIT {_TRAIT_ROWS}
            """,
            (*values, *values, DERIVATION),
        ).fetchall()
        traits = [_trait_item(row) for row in rows if _visible(row[3], visible)]
        advice = {item.key: item.text for item in traits if item.kind == "advice"}
        items.extend(
            UnderstandingItem(**{**item.__dict__, "advice": advice.get(item.key)}) if item.kind == "lesson" else item
            for item in traits
            if item.kind != "advice"
        )
        rows = connection.execute(
            f"""
            SELECT a.predicate, a.object_value, a.valid_until, p.effective_visibility
              FROM omnix_memory_v2_graph_assertions a
              {_join_policy('assertion', 'a.assertion_id')}
             WHERE a.principal_id = %s AND a.owner_type = %s AND a.owner_id = %s
               AND a.domain = 'trait' AND a.status = 'superseded' AND a.derivation_version = %s
               AND a.predicate LIKE 'person%%'
             ORDER BY a.valid_until DESC
             LIMIT {_EARLIER_ROWS}
            """,
            (*values, *values, DERIVATION),
        ).fetchall()
        for row in rows:
            if _visible(row[3], visible):
                aspect = str(row[0]).removeprefix("person_")
                items.append(UnderstandingItem(
                    key=aspect, kind="earlier", text=str(dict(row[1]).get("literal")), category="trait", at=row[2],
                    label=aspect,
                ))
        rows = connection.execute(
            f"""
            SELECT a.predicate, a.object_value, a.valid_from, p.effective_visibility, a.assertion_id, a.revision,
                   a.status
              FROM omnix_memory_v2_graph_assertions a
              {_join_policy('assertion', 'a.assertion_id')}
             WHERE a.principal_id = %s AND a.owner_type = %s AND a.owner_id = %s
               AND a.domain IN ('relationship', 'open_loop') AND a.status IN ('active', 'superseded')
               AND a.predicate IN ('own_stance', 'promised', 'running_joke') AND a.derivation_version = %s
             ORDER BY a.valid_from DESC
             LIMIT {_OWN_SIDE_ROWS}
            """,
            (*values, *values, DERIVATION),
        ).fetchall()
        for row in rows:
            if _visible(row[3], visible):
                kind = _OWN_SIDE[str(row[0])]
                items.append(UnderstandingItem(
                    key="current" if kind == "stance" else str(row[4]).rsplit(":", 1)[-1], kind=kind,
                    text=str(dict(row[1]).get("literal")), category="promise" if kind == "promise" else "relationship",
                    at=row[2], seen=int(row[5]), label="kept" if row[6] == "superseded" else None,
                ))
        rows = connection.execute(
            f"""
            SELECT a.affect_id, a.emotion_distribution, a.observed_at, p.effective_visibility
              FROM omnix_memory_v2_affect_observations a
              {_join_policy('affect', 'a.affect_id')}
             WHERE a.principal_id = %s AND a.owner_type = %s AND a.owner_id = %s
             ORDER BY a.observed_at DESC
             LIMIT {int(moods)}
            """,
            (*values, *values),
        ).fetchall()
        for row in rows:
            if _visible(row[3], visible):
                emotion = next(iter(dict(row[1])), "")
                if emotion:
                    items.append(UnderstandingItem(
                        key=str(row[0]), kind="mood", text=emotion, category="affect", at=row[2],
                    ))
        rows = connection.execute(
            f"""
            SELECT e.episode_id, e.title, e.summary, COALESCE(e.ended_at, e.started_at), p.effective_visibility
              FROM omnix_memory_v2_episodes e
              {_join_policy('episode', 'e.episode_id')}
             WHERE e.principal_id = %s AND e.owner_type = %s AND e.owner_id = %s
               AND e.derivation_version = %s
             ORDER BY COALESCE(e.ended_at, e.started_at) DESC
             LIMIT {int(episodes)}
            """,
            (*values, *values, DERIVATION),
        ).fetchall()
        for row in rows:
            if _visible(row[4], visible):
                items.append(UnderstandingItem(
                    key=str(row[0]), kind="episode", text=str(row[2]), category="episode", at=row[3], label=str(row[1]),
                ))
        rows = connection.execute(
            f"""
            SELECT a.subject_entity_id, a.predicate, a.object_value, a.valid_from, p.effective_visibility
              FROM omnix_memory_v2_graph_assertions a
              {_join_policy('assertion', 'a.assertion_id')}
             WHERE a.principal_id = %s AND a.owner_type = %s AND a.owner_id = %s
               AND a.domain = 'fact' AND a.status = 'active' AND a.derivation_version = %s
             ORDER BY a.valid_from DESC, a.assertion_id
             LIMIT {_LINKS_LOADED}
            """,
            (*values, *values, DERIVATION),
        ).fetchall()
        for row in rows:
            if _visible(row[4], visible):
                subject = str(row[0])
                relation = str(row[1]).replace("_", " ")
                object_ = str(dict(dict(row[2]).get("entity") or {}).get("entity_id"))
                items.append(UnderstandingItem(
                    key=connection_key(subject, relation, object_), kind="connection",
                    text=f"{subject} {relation} {object_}", category="fact", at=row[3],
                    label="\x1f".join((subject, relation, object_)),
                ))
    return items


_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)


def _words(text: str) -> frozenset[str]:
    return frozenset(word.casefold() for word in _WORD.findall(text))


def connected_to(links: list[UnderstandingItem], text: str, *, limit: int = 6) -> list[UnderstandingItem]:
    """Connections the turn touches, and those one step on: "my sister" finds Anna, and Anna's city.

    A word of the turn naming an end of a connection, or its relation, starts
    from it; the user is an end of too many to spread from.
    """
    said = _words(text)
    if not said:
        return []
    parts = {item.key: (item.label or "").split("\x1f") for item in links}

    def ends(item: UnderstandingItem) -> set[str]:
        subject, _relation, object_ = parts[item.key]
        return {name for name in (subject, object_) if name != USER_ENTITY}

    touched = [item for item in links if said & _words(item.text)]
    names = {name for item in touched for name in ends(item)}
    onward = [item for item in links if item not in touched and ends(item) & names]
    return [*touched, *onward][:limit]


def triggered_by(triggers: list[UnderstandingItem], text: str) -> list[UnderstandingItem]:
    """What brings on a feeling, when the turn names what it concerns: VoiceMem's anchored recall."""
    said = _words(text)
    touched = [item for item in triggers if said & _words(" ".join(item.about))]
    return sorted(touched, key=lambda item: item.seen, reverse=True)[:_TRIGGERS_PROMPTED]


# What helps and what puts them off, told as guidance: measured on Haiku, a note *about* the person was used to
# describe them ("I remember you, the vague routine") and did not change how the reply went. The reader words
# these two notes, and a lesson's advice, as advice to the owner.
_GUIDANCE = {"what_helps": "What works with them", "what_to_avoid": "Avoid with them"}


def _as_guidance(item: UnderstandingItem) -> UnderstandingItem:
    if item.kind == "lesson":
        # A lesson is a pattern in the person; its advice says what to do about it (older readings have none).
        text = (
            f"Learned from how they react: {item.advice}" if item.advice
            else f"Learned from how they react: {item.text}"
        )
    elif item.label in _GUIDANCE:
        text = f"{_GUIDANCE[item.label]}: {item.text}"
    else:
        return item
    return UnderstandingItem(
        key=item.key, kind=item.kind, category="guidance", at=item.at, label=item.label, seen=item.seen, text=text,
    )


def _newest_first(item: UnderstandingItem) -> datetime:
    return item.at or datetime.min.replace(tzinfo=timezone.utc)


def _own_side(items: list[UnderstandingItem], now: datetime) -> list[UnderstandingItem]:
    """The owner's side, told to it: how it now stands toward them, what it promised, what they joke about."""
    chosen = [item for item in items if item.kind == "stance"]
    promises = sorted((item for item in items if item.kind == "promise" and item.label != "kept"), key=_newest_first)
    for item in promises[-_PROMISES_PROMPTED:]:
        when = _when(item.at, now) if item.at is not None else "Before"
        chosen.append(UnderstandingItem(
            key=item.key, kind="promise", category="promise", at=item.at,
            text=f"{when}, you told them you would: {item.text}",
        ))
    jokes = sorted((item for item in items if item.kind == "joke"), key=lambda item: (item.seen, _newest_first(item)))
    for item in reversed(jokes[-_JOKES_PROMPTED:]):
        chosen.append(UnderstandingItem(
            key=item.key, kind="joke", category="relationship", at=item.at, text=f"A running joke between you: {item.text}",
        ))
    return chosen


def prompt_items(items: list[UnderstandingItem], query_text: str, *, now: datetime) -> list[UnderstandingItem]:
    """What every reply should know, with nothing from the model's numbers and no stale mood stated as current."""
    chosen: list[UnderstandingItem] = []
    chosen.extend(item for item in items if item.kind == "relationship")
    chosen.extend(_own_side(items, now))
    chosen.extend(_as_guidance(item) for item in items if item.kind == "person")
    # A note that turned around keeps the view before it, as VoiceMem marks an old state.
    noted = {item.key for item in items if item.kind == "person"}
    earlier: dict[str, UnderstandingItem] = {}
    for item in sorted((item for item in items if item.kind == "earlier"), key=_newest_first, reverse=True):
        if item.key in noted and item.key not in earlier and item.at is not None:
            earlier[item.key] = item
            chosen.append(UnderstandingItem(
                key=f"{item.key}:earlier", kind="earlier", category="trait", at=item.at,
                text=f"Changed {how_long_ago(item.at, now)}; before that: {item.text}",
            ))
    # What the person's reactions taught: the patterns seen most often, then the newest.
    lessons = [item for item in items if item.kind == "lesson"]
    lessons.sort(key=lambda item: (item.seen, _newest_first(item)), reverse=True)
    chosen.extend(_as_guidance(item) for item in lessons[:_LESSONS_PROMPTED])
    chosen.extend(triggered_by([item for item in items if item.kind == "trigger"], query_text))
    mood = next((item for item in items if item.kind == "mood" and item.at is not None), None)
    if mood is not None and mood.at is not None and (now - mood.at).days < 7:
        chosen.append(UnderstandingItem(
            key=mood.key, kind="mood", category="affect", at=mood.at,
            text=f"{_when(mood.at, now)}, the user seemed {mood.text}. That may have passed.",
        ))
    for episode in [item for item in items if item.kind == "episode"][:2]:
        when = _when(episode.at, now) if episode.at is not None else "Before"
        chosen.append(UnderstandingItem(
            key=episode.key, kind="episode", category="episode", at=episode.at,
            text=f"{when}: {episode.label}. {episode.text}",
        ))
    chosen.extend(connected_to([item for item in items if item.kind == "connection"], query_text))
    return chosen


# -- for the Memory tab: one owner, as the person looking at it --------------------


def _owner_authority(owner_type: str, owner_id: str, profile_id: str) -> tuple[Any, MemorySpaceKey, VisibilityScope]:
    from .curated_records import tenant_principal
    from .runtime import PostgresMemoryV2Runtime

    space = MemorySpaceKey(principal_id=tenant_principal(), owner_type=cast(Any, owner_type), owner_id=owner_id)
    return PostgresMemoryV2Runtime(), space, VisibilityScope(kind="global", scope_id=profile_id)


def _converge_now(runtime: Any, space: MemorySpaceKey) -> None:
    """So that the tab and the next reply show it now; the scheduled sweep retries if this fails."""
    from .curated_records import MemoryV2CuratedConvergence

    try:
        MemoryV2CuratedConvergence(runtime.database).run(space=space, max_steps=10)
    except Exception:  # noqa: BLE001
        logger.warning("memory_v2_inline_convergence_failed", exc_info=True)


def read_owner_understanding(owner_type: str, owner_id: str, profile_id: str) -> list[UnderstandingItem]:
    from app.persistence.runtime import uses_postgresql_runtime

    if not uses_postgresql_runtime():
        return []
    runtime, space, scope = _owner_authority(owner_type, owner_id, profile_id)
    return read_understanding(runtime.database, space, (scope,))


def forget_owner_understanding(owner_type: str, owner_id: str, profile_id: str, kind: str, key: str) -> int:
    """Returns the readings rewritten: none means nothing like that is remembered."""
    if kind not in FORGET_KINDS:
        return 0
    runtime, space, scope = _owner_authority(owner_type, owner_id, profile_id)
    rewritten = forget_item(runtime, space, scope.scope_id, kind, key)
    if rewritten:
        _converge_now(runtime, space)
    return rewritten


def correct_owner_understanding(owner_type: str, owner_id: str, profile_id: str, kind: str, key: str, text: str) -> bool:
    """False when this is not something that can be reworded."""
    if (kind, key) != ("relationship", "current") and not (kind == "person" and key in PERSON_ASPECTS):
        return False
    runtime, space, scope = _owner_authority(owner_type, owner_id, profile_id)
    correct_item(runtime, space, scope, kind, key, text, at=datetime.now(timezone.utc))
    _converge_now(runtime, space)
    return True


__all__ = [
    "UnderstandingItem",
    "connected_to",
    "correct_owner_understanding",
    "forget_owner_understanding",
    "how_long_ago",
    "prompt_items",
    "read_owner_understanding",
    "read_understanding",
    "triggered_by",
]
