"""The game master's panel (evolution roadmap EV-0, part 1): the player asks it about the campaign.

A question is not a turn: it changes nothing in the campaign. It counts, with turns, against the player's hourly model
budget (RQ-8.2). The answer shown, or that it was withheld, is kept in the panel log.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.edge.api.web_contracts import RpgGameMasterResponse, documented

_ROUTE_SENTINEL = "_omnix_rpg_game_master_routes_registered"


class RpgGameMasterQuestionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)


def _within_budget() -> None:
    from app.apps.rpg.session.persistence.session_records import _context, _database
    from app.apps.rpg.session.turn_budget import WINDOW_SECONDS, is_install_owner, turns_per_hour
    from app.persistence.unit_of_work import unit_of_work

    limit = turns_per_hour()
    if limit <= 0:
        return
    database = _database()
    context = _context(database)
    if is_install_owner(context):  # the install's owner is never limited (owner decision 2026-10-31)
        return
    with unit_of_work(database) as work:
        turns, _ = work.rpg.recent_turns_by_owner(context, window_seconds=WINDOW_SECONDS)
        asked = work.rpg_game_master_panel.asked_by_owner(context, window_seconds=WINDOW_SECONDS)
        work.rollback()
    if turns + asked >= limit:
        raise HTTPException(status_code=429, detail={
            "ok": False, "error": "rpg_model_budget_exceeded",
            "message": f"You have used this hour's {limit} turns and questions; ask again later."})


def register_rpg_game_master_routes(router: APIRouter, state) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.get("/api/rpg/sessions/{session_id}/game-master", tags=["rpg-session"],
                responses=documented(RpgGameMasterResponse))
    def rpg_game_master_log(session_id: str) -> dict[str, Any]:
        from app.apps.rpg.session.persistence.session_records import _context, _database
        from app.persistence.unit_of_work import unit_of_work

        database = _database()
        with unit_of_work(database) as work:
            entries = work.rpg_game_master_panel.recent(_context(database), session_id)
            work.rollback()
        return {"ok": True, "session_id": session_id, "entries": entries}

    @router.post("/api/rpg/sessions/{session_id}/game-master", tags=["rpg-session"],
                 responses=documented(RpgGameMasterResponse))
    def rpg_ask_game_master(session_id: str, request_body: RpgGameMasterQuestionBody) -> dict[str, Any]:
        from app.apps.rpg.narration.game_master.panel import ask
        from app.apps.rpg.session.persistence.session_records import (
            _context,
            _database,
            load_session_from_postgres,
            load_session_version_from_postgres,
        )
        from app.persistence.unit_of_work import unit_of_work

        document = load_session_from_postgres(session_id)
        if document is None:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found"})
        _within_budget()
        answered = ask(document, request_body.question)
        revision = int((load_session_version_from_postgres(session_id) or (0,))[0])
        database = _database()
        with unit_of_work(database) as work:
            entry_id = work.rpg_game_master_panel.append(
                _context(database), campaign_id=session_id, revision=revision, question=request_body.question,
                answer=answered["answer"], withheld=answered["withheld"], wish=answered["wish"])
            work.commit()
        return {"ok": True, "session_id": session_id,
                "entry": {"id": entry_id, "question": request_body.question, **answered}}


__all__ = ["register_rpg_game_master_routes"]
