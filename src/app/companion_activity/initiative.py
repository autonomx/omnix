"""Session-scoped initiative lease authority with TTL and interruption semantics."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import Field

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
]

_URGENCY_RANK: dict[InitiativeUrgency, int] = {
    "low": 0,
    "normal": 1,
    "high": 2,
    "critical": 3,
}


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


@dataclass(slots=True)
class _SessionInitiativeState:
    generation: str | None = None
    active: InitiativeLease | None = None
    last_delivered_at: datetime | None = None
    last_delivered_owner: str | None = None
    consecutive_deliveries_by_owner: int = 0


class CompanionInitiativeAuthority:
    """Authoritative lease store shared by all delivery channels for one server process."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, _SessionInitiativeState] = {}

    def register_generation(self, session_id: str, generation: str) -> InitiativeSnapshot:
        with self._lock:
            state = self._sessions.setdefault(session_id, _SessionInitiativeState())
            if state.generation != generation:
                state.generation = generation
                state.active = None
            return self._snapshot(session_id, state, _utcnow())

    def acquire(self, request: InitiativeAcquireRequest) -> InitiativeDecision:
        with self._lock:
            state = self._sessions.setdefault(request.session_id, _SessionInitiativeState())
            if state.generation is None:
                state.generation = request.generation
            if state.generation != request.generation:
                return InitiativeDecision(accepted=False, reason="stale_generation")

            self._expire_active(state, request.requested_at)
            if state.active is not None:
                if self._can_preempt(state.active, request):
                    lease = self._new_lease(request)
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

            spacing = self._effective_spacing_seconds(state, request)
            if state.last_delivered_at is not None and spacing > 0:
                elapsed = (request.requested_at - state.last_delivered_at).total_seconds()
                if elapsed < spacing:
                    return InitiativeDecision(
                        accepted=False,
                        reason="initiative_spacing",
                        eligible_in_ms=max(0, int((spacing - elapsed) * 1000)),
                    )

            lease = self._new_lease(request)
            state.active = lease
            return InitiativeDecision(
                accepted=True,
                reason="initiative_acquired",
                lease=lease,
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
            self._expire_active(state, finished_at)
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

    def snapshot(self, session_id: str, *, now: datetime | None = None) -> InitiativeSnapshot:
        with self._lock:
            state = self._sessions.setdefault(session_id, _SessionInitiativeState())
            current = now or _utcnow()
            self._expire_active(state, current)
            return self._snapshot(session_id, state, current)

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    @staticmethod
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

    @staticmethod
    def _expire_active(state: _SessionInitiativeState, now: datetime) -> None:
        if state.active is not None and state.active.expires_at <= now:
            state.active = None

    @staticmethod
    def _can_preempt(active: InitiativeLease, request: InitiativeAcquireRequest) -> bool:
        return (
            request.urgency == "critical"
            and request.interruptibility == "interrupt"
            and (
                _URGENCY_RANK[active.urgency] < _URGENCY_RANK[request.urgency]
                or active.interruptibility != "interrupt"
            )
        )

    @staticmethod
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

    @staticmethod
    def _snapshot(
        session_id: str,
        state: _SessionInitiativeState,
        _now: datetime,
    ) -> InitiativeSnapshot:
        return InitiativeSnapshot(
            session_id=session_id,
            generation=state.generation,
            active_lease=state.active,
            last_delivered_at=state.last_delivered_at,
            last_delivered_owner=state.last_delivered_owner,
            consecutive_deliveries_by_owner=state.consecutive_deliveries_by_owner,
        )


_default_authority: CompanionInitiativeAuthority | None = None
_default_lock = threading.Lock()


def default_companion_initiative_authority() -> CompanionInitiativeAuthority:
    global _default_authority
    if _default_authority is None:
        with _default_lock:
            if _default_authority is None:
                _default_authority = CompanionInitiativeAuthority()
    return _default_authority


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "CompanionInitiativeAuthority",
    "InitiativeAcquireRequest",
    "InitiativeChannel",
    "InitiativeDecision",
    "InitiativeInterruptibility",
    "InitiativeLease",
    "InitiativeSnapshot",
    "InitiativeUrgency",
    "default_companion_initiative_authority",
]
