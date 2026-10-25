"""Context-local submission identity shared by the explicit RPG turn pipeline."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator


DIRECT_RPG_SUBMISSION_ID: ContextVar[str] = ContextVar(
    "omnix_direct_rpg_submission_id", default=""
)


@dataclass(frozen=True)
class ForegroundClaim:
    """The submission a turn executes under, with the claim that fences its commit (F2: no job behind it). The
    commit completes the claim in its own transaction and says so here (``mark_committed``)."""

    session_id: str
    submission_id: str
    claim_token: str = field(repr=False)
    _committed: list[bool] = field(default_factory=list, compare=False, repr=False)

    def mark_committed(self) -> None:
        self._committed.append(True)

    @property
    def committed(self) -> bool:
        return bool(self._committed)


_CLAIM: ContextVar[ForegroundClaim | None] = ContextVar("omnix_rpg_foreground_claim", default=None)


def current_foreground_claim() -> ForegroundClaim | None:
    return _CLAIM.get()


@contextmanager
def foreground_claim(claim: ForegroundClaim) -> Iterator[None]:
    if not all((claim.session_id, claim.submission_id, claim.claim_token)):
        raise ValueError("a foreground turn executes under its submission's claim")
    token = _CLAIM.set(claim)
    try:
        yield
    finally:
        _CLAIM.reset(token)
