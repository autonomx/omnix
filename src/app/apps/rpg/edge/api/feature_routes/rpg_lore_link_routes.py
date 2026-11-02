"""Names that open their lore (evolution roadmap EV-12): what a text may link, and what a link opens.

Both read the campaign as it was last committed and nothing else: no turn, no model call, no lock, no write. They go
as far as the hero knows: the entries they know, and one a response has just named; the entries kept from the hero
(a hidden place, a secret thing) are never there, and no view shows a secret field.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.apps.rpg.edge.api.web_contracts import RpgLoreEntryResponse, RpgLoreLinkablesResponse, documented

_ROUTE_SENTINEL = "_omnix_rpg_lore_link_routes_registered"


def _document(session_id: str) -> dict[str, Any]:
    from app.apps.rpg.session.persistence.session_records import load_session_from_postgres

    document = load_session_from_postgres(session_id)
    if document is None:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found"})
    return document


def _named_lately(session_id: str, entry_id: str) -> bool:
    """Whether a response named ``entry_id`` and the hero hears of it by the next turn (a pending ``heard_of``)."""
    from app.apps.rpg.session.persistence.session_records import _context, _database
    from app.persistence.unit_of_work import unit_of_work

    database = _database()
    with unit_of_work(database) as work:
        rows = work.rpg_proposals.pending(_context(database), session_id, through_revision=2**31 - 1)
        work.rollback()
    return any(row["kind"] == "heard_of" and dict(row.get("payload") or {}).get("entry_id") == entry_id for row in rows)


def register_rpg_lore_link_routes(router: APIRouter, state) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.get("/api/rpg/sessions/{session_id}/lore/linkable", tags=["rpg-session"],
                responses=documented(RpgLoreLinkablesResponse))
    def rpg_lore_linkable(session_id: str) -> dict[str, Any]:
        from app.apps.rpg.foundation.state import access as sections
        from app.apps.rpg.narration.lore_links import linkable

        from app.apps.rpg.rules.hero_knowledge import known_entries

        simulation = sections.simulation_state_of(_document(session_id)) or {}
        known = known_entries(simulation)  # what the page links by itself: what the hero knows (a response's own
        # links name what it tells of)
        return {"ok": True, "session_id": session_id,
                "entries": [{"entry_id": entry_id, "family": row["family"], "names": row["names"]}
                            for entry_id, row in sorted(linkable(simulation).items()) if entry_id in known]}

    @router.get("/api/rpg/sessions/{session_id}/lore/entries/{entry_id:path}", tags=["rpg-session"],
                responses=documented(RpgLoreEntryResponse))
    def rpg_lore_entry(session_id: str, entry_id: str) -> dict[str, Any]:
        from app.apps.rpg.foundation.state import access as sections
        from app.apps.rpg.narration.lore_links import entry_view
        from app.apps.rpg.rules.hero_knowledge import known_entries

        document = _document(session_id)
        entry = entry_view(document, entry_id)
        # An entry the hero knows, or one a response has just named (heard of by the next turn): as far as they know.
        known = known_entries(sections.simulation_state_of(document) or {})
        if entry is not None and entry_id not in known and not _named_lately(session_id, entry_id):
            entry = None
        if entry is None:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "lore_entry_not_found"})
        return {"ok": True, "session_id": session_id, "entry": entry}


__all__ = ["register_rpg_lore_link_routes"]
