"""Whether this turn narrates after its commit (RQ-6.2; roadmap §4.1 steps 7-10).

A turn the play screen follows on its stream commits first, with no narration, and its outcome is sent at once;
the narrative writer then narrates it, and the response is inserted beside the campaign (no campaign save). A turn
whose words are already written (the game's own lines, a person's line) commits them with the turn as before, and so
does every turn submitted without the stream (Hermes, jobs, tools).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Mapping
from app.apps.rpg.foundation.state import access as _sections

_AFTER_COMMIT: ContextVar[bool] = ContextVar("RPG_NARRATE_AFTER_COMMIT", default=False)


@contextmanager
def narrating_after_commit(enabled: bool) -> Iterator[None]:
    token = _AFTER_COMMIT.set(bool(enabled))
    try:
        yield
    finally:
        _AFTER_COMMIT.reset(token)


def narrates_after_commit() -> bool:
    return _AFTER_COMMIT.get()


RECENT = 12  # the interactions the play screen shows of the story so far


def with_narrations(session: Mapping[str, Any]) -> Mapping[str, Any]:
    """``session`` with each recent turn narrated after its commit given its narration, from the response table:
    the campaign document keeps none (roadmap §4.1, "Narration is outside the campaign document")."""
    runtime = _sections.runtime_state_of(session) if isinstance(_sections.runtime_state_of(session), Mapping) else {}
    rows = raw_recent_interactions if isinstance(raw_recent_interactions := runtime.get("recent_interactions"), list) else []
    campaign_id = str((session.get("manifest") or {}).get("session_id") or "") if isinstance(session.get("manifest"), Mapping) else ""
    missing = [index for index, row in enumerate(rows) if index >= len(rows) - RECENT and isinstance(row, Mapping)
               and row.get("interaction_id") and not row.get("narrative_response_id")]
    if not campaign_id or not missing:
        return session
    from app.apps.rpg.narration.narrative_engine.projections import canonical_consumer_bundle
    from app.apps.rpg.narration.narrative_repository import build_production_narrative_repository

    repository = build_production_narrative_repository()
    filled = list(rows)
    for index in missing:
        response = repository.get_for_turn(campaign_id, str(rows[index]["interaction_id"]))
        if response is not None:
            bundle = canonical_consumer_bundle(response)
            filled[index] = {**rows[index], "narrative_response_id": response.response_id,
                             "visible_response": dict(bundle.get("visible_response") or {})}
    return {**session, "runtime_state": {**runtime, "recent_interactions": filled}}


__all__ = ["narrates_after_commit", "narrating_after_commit", "with_narrations"]
