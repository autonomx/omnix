"""Phase 7.8 — Reveal Scheduler.

Maintains scheduled/held reveals with explicit timing labels.
No time-based randomness — timing is label-driven:
``"immediate"``, ``"soon"``, ``"later"``, ``"held"``.
"""

from __future__ import annotations

from .models import RevealDirectiveState


class RevealScheduler:
    """Manage scheduled and held reveals deterministically."""

    def list_reveals(
        self, state: dict[str, RevealDirectiveState]
    ) -> list[RevealDirectiveState]:
        """Return all registered reveals."""
        return list(state.values())

    def schedule(
        self, state: dict[str, RevealDirectiveState], reveal: RevealDirectiveState
    ) -> None:
        """Insert or replace a reveal in the schedule."""
        state[reveal.reveal_id] = reveal

    def hold(
        self,
        state: dict[str, RevealDirectiveState],
        reveal_id: str,
        reason: str,
    ) -> None:
        """Put a reveal on hold (timing → ``"held"``)."""
        reveal = state.get(reveal_id)
        if reveal is not None:
            reveal.timing = "held"
            reveal.status = "held"
            reveal.hold_reason = reason

    def release(
        self, state: dict[str, RevealDirectiveState], reveal_id: str
    ) -> None:
        """Release a held reveal back to ``"scheduled"`` / ``"soon"``."""
        reveal = state.get(reveal_id)
        if reveal is not None:
            reveal.timing = "soon"
            reveal.status = "scheduled"
            reveal.hold_reason = ""

    def due_reveals(
        self, state: dict[str, RevealDirectiveState]
    ) -> list[RevealDirectiveState]:
        """Return reveals whose timing is ``"immediate"`` or ``"soon"``."""
        return [
            r
            for r in state.values()
            if r.timing in ("immediate", "soon") and r.status == "scheduled"
        ]
