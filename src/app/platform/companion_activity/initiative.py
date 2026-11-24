"""Session-scoped initiative lease authority with TTL and interruption semantics."""
from __future__ import annotations
from app.config.env import env_str as _env_str

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol, cast

from pydantic import Field

from app.persistence.database import PostgresDatabase, default_database

from .contracts import FrozenContract

InitiativeChannel = Literal["text", "avatar", "voice", "notification"]
InitiativeUrgency = Literal["low", "normal", "high", "critical"]
InitiativeInterruptibility = Literal[
    "never",
    "idle_only",
    "floor_available",
    "interrupt",
]
InitiativeDecisionReason = Literal[
    "initiative_acquired",
    "initiative_active",
    "initiative_spacing",
    "stale_generation",
    "preempted_by_critical_interrupt",
    # Characters talking to each other (companion 6.2).
    "scene_talk_closed",
    "scene_talk_backoff",
    "scene_talk_cap",
]
SceneTalkAttemptKind = Literal["reaction", "line", "start"]
SceneTalkOutcome = Literal["streamed", "declined", "skipped", "failed"]
# A declined line or reaction closes its anchor, and so does a second skipped one; a declined or skipped start
# backs off.
_CLOSING_OUTCOMES = frozenset({"declined", "skipped"})
_SKIPS_BEFORE_CLOSED = 2
SCENE_TALK_TEXT_CHARS = 240
_SCENE_TALK_RETENTION = timedelta(hours=24)
_SCENE_TALK_WINDOW = timedelta(hours=1)

_URGENCY_RANK: dict[InitiativeUrgency, int] = {
    "low": 0,
    "normal": 1,
    "high": 2,
    "critical": 3,
}


class SceneTalkAttemptRequest(FrozenContract):
    user_id: str = Field(min_length=1, max_length=200)
    anchor_message_id: str = Field(min_length=1, max_length=240)
    kind: SceneTalkAttemptKind
    # Line and start attempts an account may make an hour; a reaction does not count and is not capped.
    attempts_per_hour: int = Field(default=12, ge=0, le=100)
    # False for a line answering the person (a thread they started): it is neither capped nor counted.
    counted: bool = True


class SceneTalkAttempt(FrozenContract):
    """One scene talk attempt, keyed by the lease it ran under; ``outcome`` is None while it runs."""

    attempt_id: str
    user_id: str
    session_id: str
    anchor_message_id: str
    kind: SceneTalkAttemptKind
    outcome: SceneTalkOutcome | None = None
    streamed_text: str | None = None
    next_start_after: datetime | None = None
    created_at: datetime
    finished_at: datetime | None = None
    counted: bool = True


class InitiativeLease(FrozenContract):
    lease_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=200)
    generation: str = Field(min_length=1, max_length=160)
    owner: str = Field(min_length=1, max_length=120)
    intent_id: str = Field(min_length=1, max_length=240)
    channel: InitiativeChannel
    urgency: InitiativeUrgency
    interruptibility: InitiativeInterruptibility
    acquired_at: datetime
    expires_at: datetime


class InitiativeAcquireRequest(FrozenContract):
    session_id: str = Field(min_length=1, max_length=200)
    generation: str = Field(min_length=1, max_length=160)
    owner: str = Field(min_length=1, max_length=120)
    intent_id: str = Field(min_length=1, max_length=240)
    channel: InitiativeChannel
    urgency: InitiativeUrgency = "normal"
    interruptibility: InitiativeInterruptibility = "idle_only"
    requested_at: datetime
    ttl_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    minimum_spacing_seconds: float = Field(default=25.0, ge=0.0, le=600.0)
    # A scene talk attempt (companion 6.2): recorded with the lease, under the same lock, and refused when its
    # anchor is closed, a start is backing off, or the account's hourly cap is spent.
    scene_talk: SceneTalkAttemptRequest | None = None


class InitiativeDecision(FrozenContract):
    accepted: bool
    reason: InitiativeDecisionReason
    lease: InitiativeLease | None = None
    eligible_in_ms: int = Field(default=0, ge=0)


class InitiativeSnapshot(FrozenContract):
    session_id: str
    generation: str | None = None
    active_lease: InitiativeLease | None = None
    last_delivered_at: datetime | None = None
    last_delivered_owner: str | None = None
    consecutive_deliveries_by_owner: int = Field(default=0, ge=0)


class CompanionInitiativeAuthorityStore(Protocol):
    def register_generation(self, session_id: str, generation: str) -> InitiativeSnapshot: ...

    def acquire(self, request: InitiativeAcquireRequest) -> InitiativeDecision: ...

    def authorizes(self, lease: InitiativeLease, *, now: datetime) -> bool: ...

    def bind_intent(
        self,
        *,
        session_id: str,
        lease_id: str,
        intent_id: str,
        bound_at: datetime,
    ) -> InitiativeLease | None: ...

    def finish(
        self,
        *,
        session_id: str,
        lease_id: str,
        finished_at: datetime,
        delivered: bool,
    ) -> bool: ...

    def finish_intent(
        self,
        *,
        session_id: str,
        intent_id: str,
        finished_at: datetime,
        delivered: bool,
    ) -> bool: ...

    def snapshot(self, session_id: str, *, now: datetime | None = None) -> InitiativeSnapshot: ...

    def reset(self, session_id: str) -> None: ...

    # Scene talk (companion 6.2-6.3).
    def finish_owner(self, *, session_id: str, owner: str, finished_at: datetime, delivered: bool = False) -> bool:
        """Finish the active lease if ``owner`` holds it, under the same lock (the person took the floor)."""
        ...

    def record_scene_attempt(
        self, *, attempt_id: str, outcome: SceneTalkOutcome, finished_at: datetime,
        streamed_text: str | None = None, start_backoff_seconds: float = 0.0,
    ) -> SceneTalkAttempt | None:
        """Set a running attempt's outcome once; a closing start backs off further starts in its chat."""
        ...

    def active_scene_attempt(
        self, session_id: str, *, now: datetime, intent_id: str | None = None,
    ) -> SceneTalkAttempt | None:
        """The attempt the active lease runs, if any (and if it is bound to ``intent_id``, when given)."""
        ...


@dataclass(slots=True)
class _SessionInitiativeState:
    generation: str | None = None
    active: InitiativeLease | None = None
    last_delivered_at: datetime | None = None
    last_delivered_owner: str | None = None
    consecutive_deliveries_by_owner: int = 0


class CompanionInitiativeAuthority:
    """Deterministic in-memory authority used by isolated tests and no-DB development."""

    def __init__(self) -> None:
        # One lock for every session and account: the cap's count and insert cannot interleave.
        self._lock = threading.RLock()
        self._sessions: dict[str, _SessionInitiativeState] = {}
        self._attempts: dict[str, SceneTalkAttempt] = {}

    def register_generation(self, session_id: str, generation: str) -> InitiativeSnapshot:
        with self._lock:
            state = self._sessions.setdefault(session_id, _SessionInitiativeState())
            if state.generation != generation:
                state.generation = generation
                state.active = None
            return _snapshot(session_id, state)

    def acquire(self, request: InitiativeAcquireRequest) -> InitiativeDecision:
        with self._lock:
            state = self._sessions.setdefault(request.session_id, _SessionInitiativeState())
            return _acquire_with_attempt(state, _MemoryAttemptLog(self._attempts), request)

    def finish_owner(self, *, session_id: str, owner: str, finished_at: datetime, delivered: bool = False) -> bool:
        with self._lock:
            state = self._sessions.get(session_id)
            return state is not None and _finish_owner_state(state, owner=owner, finished_at=finished_at,
                                                             delivered=delivered)

    def record_scene_attempt(
        self, *, attempt_id: str, outcome: SceneTalkOutcome, finished_at: datetime,
        streamed_text: str | None = None, start_backoff_seconds: float = 0.0,
    ) -> SceneTalkAttempt | None:
        with self._lock:
            current = self._attempts.get(attempt_id)
            finished = _finished_attempt(current, outcome, finished_at, streamed_text, start_backoff_seconds)
            if finished is not None:
                self._attempts[attempt_id] = finished
            return finished

    def active_scene_attempt(
        self, session_id: str, *, now: datetime, intent_id: str | None = None,
    ) -> SceneTalkAttempt | None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return None
            _expire_active(state, now)
            lease = state.active
            if lease is None or (intent_id is not None and lease.intent_id != intent_id):
                return None
            return self._attempts.get(lease.lease_id)

    def authorizes(self, lease: InitiativeLease, *, now: datetime) -> bool:
        """Return true only while this exact lease is the active session authority."""

        with self._lock:
            state = self._sessions.get(lease.session_id)
            if state is None or state.generation != lease.generation:
                return False
            _expire_active(state, now)
            return state.active == lease

    def bind_intent(
        self,
        *,
        session_id: str,
        lease_id: str,
        intent_id: str,
        bound_at: datetime,
    ) -> InitiativeLease | None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return None
            return _bind_intent_state(
                state,
                lease_id=lease_id,
                intent_id=intent_id,
                bound_at=bound_at,
            )

    def finish(
        self,
        *,
        session_id: str,
        lease_id: str,
        finished_at: datetime,
        delivered: bool,
    ) -> bool:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return False
            return _finish_state(
                state,
                lease_id=lease_id,
                finished_at=finished_at,
                delivered=delivered,
            )

    def finish_intent(
        self,
        *,
        session_id: str,
        intent_id: str,
        finished_at: datetime,
        delivered: bool,
    ) -> bool:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return False
            return _finish_intent_state(
                state,
                intent_id=intent_id,
                finished_at=finished_at,
                delivered=delivered,
            )

    def snapshot(self, session_id: str, *, now: datetime | None = None) -> InitiativeSnapshot:
        with self._lock:
            state = self._sessions.setdefault(session_id, _SessionInitiativeState())
            _expire_active(state, now or _utcnow())
            return _snapshot(session_id, state)

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


class PostgresCompanionInitiativeAuthority:
    """Cross-worker initiative authority serialized by a PostgreSQL session row lock."""

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()

    def register_generation(self, session_id: str, generation: str) -> InitiativeSnapshot:
        with self.database.transaction() as connection:
            state = _locked_postgres_state(connection, session_id)
            if state.generation != generation:
                state.generation = generation
                state.active = None
                _persist_postgres_state(connection, session_id, state)
            return _snapshot(session_id, state)

    def acquire(self, request: InitiativeAcquireRequest) -> InitiativeDecision:
        with self.database.transaction() as connection:
            state = _locked_postgres_state(connection, request.session_id)
            if request.scene_talk is not None:
                # After the session row, so two chats of one account cannot both pass the cap.
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext('omnix_companion_scene_talk'), hashtext(%s))",
                    (request.scene_talk.user_id,),
                )
            decision = _acquire_with_attempt(state, _PostgresAttemptLog(connection), request)
            if decision.reason not in {"stale_generation", "scene_talk_closed", "scene_talk_backoff",
                                       "scene_talk_cap"}:
                _persist_postgres_state(connection, request.session_id, state)
            return decision

    def finish_owner(self, *, session_id: str, owner: str, finished_at: datetime, delivered: bool = False) -> bool:
        with self.database.transaction() as connection:
            state = _locked_postgres_state(connection, session_id)
            finished = _finish_owner_state(state, owner=owner, finished_at=finished_at, delivered=delivered)
            if finished:
                _persist_postgres_state(connection, session_id, state)
            return finished

    def record_scene_attempt(
        self, *, attempt_id: str, outcome: SceneTalkOutcome, finished_at: datetime,
        streamed_text: str | None = None, start_backoff_seconds: float = 0.0,
    ) -> SceneTalkAttempt | None:
        with self.database.transaction() as connection:
            log = _PostgresAttemptLog(connection)
            finished = _finished_attempt(log.get(attempt_id, lock=True), outcome, finished_at, streamed_text,
                                         start_backoff_seconds)
            if finished is not None:
                log.finish(finished)
            return finished

    def active_scene_attempt(
        self, session_id: str, *, now: datetime, intent_id: str | None = None,
    ) -> SceneTalkAttempt | None:
        with self.database.transaction() as connection:
            state = _locked_postgres_state(connection, session_id)
            if _expire_active(state, now):
                _persist_postgres_state(connection, session_id, state)
            lease = state.active
            if lease is None or (intent_id is not None and lease.intent_id != intent_id):
                return None
            return _PostgresAttemptLog(connection).get(lease.lease_id)

    def authorizes(self, lease: InitiativeLease, *, now: datetime) -> bool:
        with self.database.transaction() as connection:
            state = _locked_postgres_state(connection, lease.session_id)
            if state.generation != lease.generation:
                return False
            expired = _expire_active(state, now)
            if expired:
                _persist_postgres_state(connection, lease.session_id, state)
            return state.active == lease

    def bind_intent(
        self,
        *,
        session_id: str,
        lease_id: str,
        intent_id: str,
        bound_at: datetime,
    ) -> InitiativeLease | None:
        with self.database.transaction() as connection:
            state = _locked_postgres_state(connection, session_id)
            active = _bind_intent_state(
                state,
                lease_id=lease_id,
                intent_id=intent_id,
                bound_at=bound_at,
            )
            _persist_postgres_state(connection, session_id, state)
            return active

    def finish(
        self,
        *,
        session_id: str,
        lease_id: str,
        finished_at: datetime,
        delivered: bool,
    ) -> bool:
        with self.database.transaction() as connection:
            state = _locked_postgres_state(connection, session_id)
            finished = _finish_state(
                state,
                lease_id=lease_id,
                finished_at=finished_at,
                delivered=delivered,
            )
            _persist_postgres_state(connection, session_id, state)
            return finished

    def finish_intent(
        self,
        *,
        session_id: str,
        intent_id: str,
        finished_at: datetime,
        delivered: bool,
    ) -> bool:
        with self.database.transaction() as connection:
            state = _locked_postgres_state(connection, session_id)
            finished = _finish_intent_state(
                state,
                intent_id=intent_id,
                finished_at=finished_at,
                delivered=delivered,
            )
            _persist_postgres_state(connection, session_id, state)
            return finished

    def snapshot(self, session_id: str, *, now: datetime | None = None) -> InitiativeSnapshot:
        with self.database.transaction() as connection:
            state = _locked_postgres_state(connection, session_id)
            expired = _expire_active(state, now or _utcnow())
            if expired:
                _persist_postgres_state(connection, session_id, state)
            return _snapshot(session_id, state)

    def reset(self, session_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM omnix_companion_initiative_sessions WHERE session_id = %s",
                (session_id,),
            )


def _acquire_from_state(
    state: _SessionInitiativeState,
    request: InitiativeAcquireRequest,
) -> InitiativeDecision:
    if state.generation is None:
        state.generation = request.generation
    if state.generation != request.generation:
        return InitiativeDecision(accepted=False, reason="stale_generation")

    _expire_active(state, request.requested_at)
    if state.active is not None:
        if _can_preempt(state.active, request):
            lease = _new_lease(request)
            state.active = lease
            return InitiativeDecision(
                accepted=True,
                reason="preempted_by_critical_interrupt",
                lease=lease,
                eligible_in_ms=0,
            )
        remaining = max(
            0,
            int((state.active.expires_at - request.requested_at).total_seconds() * 1000),
        )
        return InitiativeDecision(
            accepted=False,
            reason="initiative_active",
            eligible_in_ms=remaining,
        )

    spacing = _effective_spacing_seconds(state, request)
    if state.last_delivered_at is not None and spacing > 0:
        elapsed = (request.requested_at - state.last_delivered_at).total_seconds()
        if elapsed < spacing:
            return InitiativeDecision(
                accepted=False,
                reason="initiative_spacing",
                eligible_in_ms=max(0, int((spacing - elapsed) * 1000)),
            )

    lease = _new_lease(request)
    state.active = lease
    return InitiativeDecision(
        accepted=True,
        reason="initiative_acquired",
        lease=lease,
    )


def _bind_intent_state(
    state: _SessionInitiativeState,
    *,
    lease_id: str,
    intent_id: str,
    bound_at: datetime,
) -> InitiativeLease | None:
    _expire_active(state, bound_at)
    active = state.active
    if active is None or active.lease_id != lease_id:
        return None
    active = active.model_copy(update={"intent_id": intent_id})
    state.active = active
    return active


def _finish_state(
    state: _SessionInitiativeState,
    *,
    lease_id: str,
    finished_at: datetime,
    delivered: bool,
) -> bool:
    _expire_active(state, finished_at)
    active = state.active
    if active is None or active.lease_id != lease_id:
        return False
    state.active = None
    if delivered:
        if state.last_delivered_owner == active.owner:
            state.consecutive_deliveries_by_owner += 1
        else:
            state.last_delivered_owner = active.owner
            state.consecutive_deliveries_by_owner = 1
        state.last_delivered_at = finished_at
    return True


def _finish_intent_state(
    state: _SessionInitiativeState,
    *,
    intent_id: str,
    finished_at: datetime,
    delivered: bool,
) -> bool:
    _expire_active(state, finished_at)
    active = state.active
    if active is None or active.intent_id != intent_id:
        return False
    return _finish_state(
        state,
        lease_id=active.lease_id,
        finished_at=finished_at,
        delivered=delivered,
    )


def _finish_owner_state(
    state: _SessionInitiativeState, *, owner: str, finished_at: datetime, delivered: bool,
) -> bool:
    _expire_active(state, finished_at)
    active = state.active
    if active is None or active.owner != owner:
        return False
    return _finish_state(state, lease_id=active.lease_id, finished_at=finished_at, delivered=delivered)


# --- scene talk attempts (companion 6.2) --------------------------------------------------------------------------


class _AttemptLog(Protocol):
    def closed(self, session_id: str, anchor_message_id: str) -> bool: ...

    def start_backoff_until(self, session_id: str) -> datetime | None: ...

    def counted_since(self, user_id: str, since: datetime) -> list[datetime]: ...

    def insert(self, attempt: SceneTalkAttempt, *, prune_before: datetime) -> None: ...


def _acquire_with_attempt(
    state: _SessionInitiativeState, log: _AttemptLog, request: InitiativeAcquireRequest,
) -> InitiativeDecision:
    """The lease decision, with a scene talk attempt checked first and recorded with the lease it gets."""
    talk = request.scene_talk
    if talk is not None:
        refusal = _scene_talk_refusal(log, request.session_id, talk, request.requested_at)
        if refusal is not None:
            return refusal
    decision = _acquire_from_state(state, request)
    if talk is not None and decision.accepted and decision.lease is not None:
        log.insert(
            SceneTalkAttempt(
                attempt_id=decision.lease.lease_id, user_id=talk.user_id, session_id=request.session_id,
                anchor_message_id=talk.anchor_message_id, kind=talk.kind, created_at=request.requested_at,
                counted=talk.counted and talk.kind in {"line", "start"},
            ),
            prune_before=request.requested_at - _SCENE_TALK_RETENTION,
        )
    return decision


def _scene_talk_refusal(
    log: _AttemptLog, session_id: str, talk: SceneTalkAttemptRequest, now: datetime,
) -> InitiativeDecision | None:
    if talk.kind in {"reaction", "line"} and log.closed(session_id, talk.anchor_message_id):
        return InitiativeDecision(accepted=False, reason="scene_talk_closed")
    if talk.kind == "start":
        until = log.start_backoff_until(session_id)
        if until is not None and until > now:
            return InitiativeDecision(accepted=False, reason="scene_talk_backoff",
                                      eligible_in_ms=int((until - now).total_seconds() * 1000))
    if talk.kind in {"line", "start"} and talk.counted:
        recent = sorted(log.counted_since(talk.user_id, now - _SCENE_TALK_WINDOW))
        if len(recent) >= talk.attempts_per_hour:
            frees_at = recent[-talk.attempts_per_hour] + _SCENE_TALK_WINDOW if talk.attempts_per_hour else now + _SCENE_TALK_WINDOW
            return InitiativeDecision(accepted=False, reason="scene_talk_cap",
                                      eligible_in_ms=max(0, int((frees_at - now).total_seconds() * 1000)))
    return None


def _finished_attempt(
    current: SceneTalkAttempt | None, outcome: SceneTalkOutcome, finished_at: datetime,
    streamed_text: str | None, start_backoff_seconds: float,
) -> SceneTalkAttempt | None:
    if current is None or current.outcome is not None:
        return None
    text = (streamed_text or "")[:SCENE_TALK_TEXT_CHARS] or None
    backoff = (
        finished_at + timedelta(seconds=start_backoff_seconds)
        if current.kind == "start" and outcome in _CLOSING_OUTCOMES and start_backoff_seconds > 0
        else None
    )
    return current.model_copy(update={
        "outcome": outcome, "streamed_text": text if outcome == "streamed" else None,
        "next_start_after": backoff, "finished_at": finished_at,
    })


def _anchor_closed(declined: int, skipped: int) -> bool:
    """No more reactions or lines follow an anchor once the director chose nobody, or once a chosen member's turn
    said SKIP twice: the first SKIP lets the call ask once more without that member (C1, 2026-11-23)."""
    return declined > 0 or skipped >= _SKIPS_BEFORE_CLOSED


class _MemoryAttemptLog:
    def __init__(self, attempts: dict[str, SceneTalkAttempt]) -> None:
        self.attempts = attempts

    def closed(self, session_id: str, anchor_message_id: str) -> bool:
        outcomes = [item.outcome for item in self.attempts.values()
                    if item.session_id == session_id and item.anchor_message_id == anchor_message_id
                    and item.kind in {"reaction", "line"}]
        return _anchor_closed(outcomes.count("declined"), outcomes.count("skipped"))

    def start_backoff_until(self, session_id: str) -> datetime | None:
        times = [item.next_start_after for item in self.attempts.values()
                 if item.session_id == session_id and item.kind == "start" and item.next_start_after is not None]
        return max(times) if times else None

    def counted_since(self, user_id: str, since: datetime) -> list[datetime]:
        return [item.created_at for item in self.attempts.values()
                if item.user_id == user_id and item.kind in {"line", "start"} and item.counted
                and item.created_at > since]

    def insert(self, attempt: SceneTalkAttempt, *, prune_before: datetime) -> None:
        for attempt_id in [key for key, item in self.attempts.items() if item.created_at < prune_before]:
            del self.attempts[attempt_id]
        self.attempts.setdefault(attempt.attempt_id, attempt)


_ATTEMPT_COLUMNS = (
    "attempt_id, user_id, session_id, anchor_message_id, kind, outcome, streamed_text, next_start_after, "
    "created_at, finished_at, counted"
)


class _PostgresAttemptLog:
    def __init__(self, connection) -> None:
        self.connection = connection

    def closed(self, session_id: str, anchor_message_id: str) -> bool:
        row = self.connection.execute(
            """
            SELECT count(*) FILTER (WHERE outcome = 'declined'), count(*) FILTER (WHERE outcome = 'skipped')
              FROM omnix_companion_scene_talk_attempts
             WHERE session_id = %s AND anchor_message_id = %s
               AND kind IN ('reaction', 'line') AND outcome IN ('declined', 'skipped')
            """,
            (session_id, anchor_message_id),
        ).fetchone()
        return row is not None and _anchor_closed(int(row[0] or 0), int(row[1] or 0))

    def start_backoff_until(self, session_id: str) -> datetime | None:
        row = self.connection.execute(
            """
            SELECT max(next_start_after) FROM omnix_companion_scene_talk_attempts
             WHERE session_id = %s AND kind = 'start' AND next_start_after IS NOT NULL
            """,
            (session_id,),
        ).fetchone()
        return row[0] if row else None

    def counted_since(self, user_id: str, since: datetime) -> list[datetime]:
        rows = self.connection.execute(
            """
            SELECT created_at FROM omnix_companion_scene_talk_attempts
             WHERE user_id = %s AND kind IN ('line', 'start') AND counted AND created_at > %s
            """,
            (user_id, since),
        ).fetchall()
        return [row[0] for row in rows]

    def insert(self, attempt: SceneTalkAttempt, *, prune_before: datetime) -> None:
        self.connection.execute(
            "DELETE FROM omnix_companion_scene_talk_attempts WHERE created_at < %s", (prune_before,),
        )
        self.connection.execute(
            f"""
            INSERT INTO omnix_companion_scene_talk_attempts ({_ATTEMPT_COLUMNS})
            VALUES (%s, %s, %s, %s, %s, NULL, NULL, NULL, %s, NULL, %s)
            ON CONFLICT (attempt_id) DO NOTHING
            """,
            (attempt.attempt_id, attempt.user_id, attempt.session_id, attempt.anchor_message_id, attempt.kind,
             attempt.created_at, attempt.counted),
        )

    def get(self, attempt_id: str, *, lock: bool = False) -> SceneTalkAttempt | None:
        row = self.connection.execute(
            f"SELECT {_ATTEMPT_COLUMNS} FROM omnix_companion_scene_talk_attempts WHERE attempt_id = %s"
            + (" FOR UPDATE" if lock else ""),
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        return SceneTalkAttempt(
            attempt_id=str(row[0]), user_id=str(row[1]), session_id=str(row[2]), anchor_message_id=str(row[3]),
            kind=cast(SceneTalkAttemptKind, str(row[4])),
            outcome=cast(SceneTalkOutcome, str(row[5])) if row[5] is not None else None,
            streamed_text=row[6], next_start_after=row[7], created_at=row[8], finished_at=row[9],
            counted=bool(row[10]),
        )

    def finish(self, attempt: SceneTalkAttempt) -> None:
        self.connection.execute(
            """
            UPDATE omnix_companion_scene_talk_attempts
               SET outcome = %s, streamed_text = %s, next_start_after = %s, finished_at = %s
             WHERE attempt_id = %s AND outcome IS NULL
            """,
            (attempt.outcome, attempt.streamed_text, attempt.next_start_after, attempt.finished_at,
             attempt.attempt_id),
        )


def _new_lease(request: InitiativeAcquireRequest) -> InitiativeLease:
    return InitiativeLease(
        lease_id=f"lease:{uuid.uuid4().hex}",
        session_id=request.session_id,
        generation=request.generation,
        owner=request.owner,
        intent_id=request.intent_id,
        channel=request.channel,
        urgency=request.urgency,
        interruptibility=request.interruptibility,
        acquired_at=request.requested_at,
        expires_at=request.requested_at + timedelta(seconds=request.ttl_seconds),
    )


def _expire_active(state: _SessionInitiativeState, now: datetime) -> bool:
    if state.active is not None and state.active.expires_at <= now:
        state.active = None
        return True
    return False


def _can_preempt(active: InitiativeLease, request: InitiativeAcquireRequest) -> bool:
    return (
        request.urgency == "critical"
        and request.interruptibility == "interrupt"
        and (
            _URGENCY_RANK[active.urgency] < _URGENCY_RANK[request.urgency]
            or active.interruptibility != "interrupt"
        )
    )


def _effective_spacing_seconds(
    state: _SessionInitiativeState,
    request: InitiativeAcquireRequest,
) -> float:
    if request.urgency == "critical" and request.interruptibility == "interrupt":
        return 0.0
    spacing = request.minimum_spacing_seconds
    if (
        state.last_delivered_owner == request.owner
        and state.consecutive_deliveries_by_owner >= 2
        and request.urgency in {"low", "normal"}
    ):
        return spacing * 2
    if request.urgency == "high":
        return spacing * 0.5
    return spacing


def _snapshot(session_id: str, state: _SessionInitiativeState) -> InitiativeSnapshot:
    return InitiativeSnapshot(
        session_id=session_id,
        generation=state.generation,
        active_lease=state.active,
        last_delivered_at=state.last_delivered_at,
        last_delivered_owner=state.last_delivered_owner,
        consecutive_deliveries_by_owner=state.consecutive_deliveries_by_owner,
    )


def _locked_postgres_state(connection, session_id: str) -> _SessionInitiativeState:
    connection.execute(
        """
        INSERT INTO omnix_companion_initiative_sessions (session_id)
        VALUES (%s)
        ON CONFLICT (session_id) DO NOTHING
        """,
        (session_id,),
    )
    row = connection.execute(
        """
        SELECT session_id, generation,
               active_lease_id, active_owner, active_intent_id, active_channel,
               active_urgency, active_interruptibility,
               active_acquired_at, active_expires_at,
               last_delivered_at, last_delivered_owner,
               consecutive_deliveries_by_owner
          FROM omnix_companion_initiative_sessions
         WHERE session_id = %s
         FOR UPDATE
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to lock companion initiative session row")
    return _postgres_state_from_row(row)


def _postgres_state_from_row(row) -> _SessionInitiativeState:
    generation = str(row[1]) if row[1] is not None else None
    active = None
    if all(row[index] is not None for index in range(2, 10)) and generation is not None:
        active = InitiativeLease(
            lease_id=str(row[2]),
            session_id=str(row[0]),
            generation=generation,
            owner=str(row[3]),
            intent_id=str(row[4]),
            # Stored values; the model validates them on construction.
            channel=cast(InitiativeChannel, str(row[5])),
            urgency=cast(InitiativeUrgency, str(row[6])),
            interruptibility=cast(InitiativeInterruptibility, str(row[7])),
            acquired_at=row[8],
            expires_at=row[9],
        )
    return _SessionInitiativeState(
        generation=generation,
        active=active,
        last_delivered_at=row[10],
        last_delivered_owner=str(row[11]) if row[11] is not None else None,
        consecutive_deliveries_by_owner=int(row[12] or 0),
    )


def _persist_postgres_state(
    connection,
    session_id: str,
    state: _SessionInitiativeState,
) -> None:
    active = state.active
    connection.execute(
        """
        UPDATE omnix_companion_initiative_sessions
           SET generation = %s,
               active_lease_id = %s,
               active_owner = %s,
               active_intent_id = %s,
               active_channel = %s,
               active_urgency = %s,
               active_interruptibility = %s,
               active_acquired_at = %s,
               active_expires_at = %s,
               last_delivered_at = %s,
               last_delivered_owner = %s,
               consecutive_deliveries_by_owner = %s,
               updated_at = CURRENT_TIMESTAMP
         WHERE session_id = %s
        """,
        (
            state.generation,
            active.lease_id if active else None,
            active.owner if active else None,
            active.intent_id if active else None,
            active.channel if active else None,
            active.urgency if active else None,
            active.interruptibility if active else None,
            active.acquired_at if active else None,
            active.expires_at if active else None,
            state.last_delivered_at,
            state.last_delivered_owner,
            state.consecutive_deliveries_by_owner,
            session_id,
        ),
    )


_default_authority: CompanionInitiativeAuthorityStore | None = None
_default_lock = threading.Lock()


def default_companion_initiative_authority() -> CompanionInitiativeAuthorityStore:
    global _default_authority
    if _default_authority is None:
        with _default_lock:
            if _default_authority is None:
                if (_env_str("OMNIX_DATABASE_URL") or "").strip():
                    _default_authority = PostgresCompanionInitiativeAuthority()
                else:
                    _default_authority = CompanionInitiativeAuthority()
    return _default_authority


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "CompanionInitiativeAuthority",
    "CompanionInitiativeAuthorityStore",
    "InitiativeAcquireRequest",
    "InitiativeChannel",
    "InitiativeDecision",
    "InitiativeInterruptibility",
    "InitiativeLease",
    "InitiativeSnapshot",
    "InitiativeUrgency",
    "PostgresCompanionInitiativeAuthority",
    "SCENE_TALK_TEXT_CHARS",
    "SceneTalkAttempt",
    "SceneTalkAttemptKind",
    "SceneTalkAttemptRequest",
    "SceneTalkOutcome",
    "default_companion_initiative_authority",
]
