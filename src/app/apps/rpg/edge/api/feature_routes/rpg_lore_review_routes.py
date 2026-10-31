"""The world's lore review queue (evolution roadmap EV-0, part 2): the game master's drafts, for the world's author.

Only the world's owner reads or decides its queue. The consistency check's findings are theirs alone (question 14).
An approved draft joins the world at its next publication; the screen in the world editor comes with EV-6.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.edge.api.web_contracts import RpgLoreReviewResponse, documented

_ROUTE_SENTINEL = "_omnix_rpg_lore_review_routes_registered"


class RpgLoreReviewDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject", "link", "withdraw"]
    row: dict[str, Any] | None = None  # the author's edit of the entry, when approving
    play: dict[str, Any] | None = None  # and of its play data
    link_to: int | None = Field(default=None, ge=1)


def _owned(work: Any, context: Any, world_id: str) -> dict[str, Any]:
    from app.apps.rpg.genesis.worlds.lifecycle_service import require_world_writable

    try:
        return require_world_writable(work, context, world_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "world_not_found"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"ok": False, "error": "world_archived"}) from exc


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _groups(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for draft in drafts:
        groups.setdefault(draft["group_key"], []).append(draft)
    return [{"group_key": key, "drafts": rows} for key, rows in groups.items()]


def register_rpg_lore_review_routes(router: APIRouter, state) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.get("/api/rpg/worlds/{world_id}/lore-review", tags=["rpg-world"], responses=documented(RpgLoreReviewResponse))
    def rpg_lore_review_queue(world_id: str, status: str = "") -> dict[str, Any]:
        from app.persistence.unit_of_work import unit_of_work
        from app.runtime.tenant_context import current_tenant

        context = current_tenant()
        with unit_of_work() as work:
            if work.world_scenarios.get_world(context, world_id) is None:  # a read takes no lock
                work.rollback()
                raise HTTPException(status_code=404, detail={"ok": False, "error": "world_not_found"})
            drafts = work.rpg_lore_review.queue(context, world_id, status=status)
            work.rollback()
        return {"ok": True, "world_id": world_id, "groups": _groups(drafts)}

    @router.post("/api/rpg/worlds/{world_id}/lore-review/{draft_id}/check", tags=["rpg-world"],
                 responses=documented(RpgLoreReviewResponse))
    def rpg_lore_review_check(world_id: str, draft_id: int) -> dict[str, Any]:
        from app.apps.rpg.session.lore_review import consistency_check
        from app.persistence.unit_of_work import unit_of_work
        from app.runtime.tenant_context import current_tenant

        context = current_tenant()
        with unit_of_work() as work:
            _owned(work, context, world_id)
            draft = work.rpg_lore_review.get(context, draft_id)
            latest = work.world_scenarios.latest_world_revision(context, world_id)
            work.rollback()
        if draft is None or draft["world_id"] != world_id:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "lore_draft_not_found"})
        canon = dict((latest or {}).get("document", {}).get("canon") or {}) if isinstance(latest, dict) else {}
        findings = consistency_check(draft, canon)
        with unit_of_work() as work:
            work.rpg_lore_review.record_findings(context, draft_id, findings)
            draft = work.rpg_lore_review.get(context, draft_id)
            work.commit()
        return {"ok": True, "world_id": world_id, "draft": draft}

    @router.post("/api/rpg/worlds/{world_id}/lore-review/{draft_id}/decision", tags=["rpg-world"],
                 responses=documented(RpgLoreReviewResponse))
    def rpg_lore_review_decide(world_id: str, draft_id: int, request_body: RpgLoreReviewDecisionBody) -> dict[str, Any]:
        from app.apps.rpg.session.lore_review import APPROVED_KEY, approved_inventions, canon_id
        from app.persistence.unit_of_work import unit_of_work
        from app.runtime.tenant_context import current_tenant

        context = current_tenant()
        with unit_of_work() as work:
            world = _owned(work, context, world_id)
            draft = work.rpg_lore_review.get(context, draft_id)
            if draft is None or draft["world_id"] != world_id:
                work.rollback()
                raise HTTPException(status_code=404, detail={"ok": False, "error": "lore_draft_not_found"})
            if request_body.decision == "withdraw":  # an approval taken back before the world publishes it
                if draft["status"] != "approved":
                    work.rollback()
                    raise HTTPException(status_code=409, detail={"ok": False, "error": "lore_draft_not_approved"})
                approved = approved_inventions(world)
                approved.pop(draft["canon_id"], None)
                work.world_scenarios.replace_world_metadata(
                    context, world_id, {**dict(world.get("metadata") or {}), APPROVED_KEY: approved})
                work.rpg_lore_review.reopen(context, draft_id)
                draft = work.rpg_lore_review.get(context, draft_id)
                work.commit()
                return {"ok": True, "world_id": world_id, "draft": draft}
            if draft["status"] != "pending":
                work.rollback()
                raise HTTPException(status_code=409, detail={"ok": False, "error": "lore_draft_decided"})
            if request_body.decision == "reject":
                work.rpg_lore_review.decide(context, draft_id, status="rejected")
            elif request_body.decision == "link":
                target = work.rpg_lore_review.get(context, int(request_body.link_to or 0))
                if (target is None or target["status"] != "approved" or target["group_key"] != draft["group_key"]
                        or target["world_id"] != world_id):
                    work.rollback()
                    raise HTTPException(status_code=422, detail={"ok": False, "error": "link_needs_an_approved_draft"})
                work.rpg_lore_review.decide(context, draft_id, status="linked", canon_id=target["canon_id"],
                                            linked_to=target["id"])
            else:
                entry = {"row": request_body.row if request_body.row is not None else draft["entry"].get("row", {}),
                         "play": request_body.play if request_body.play is not None else draft["entry"].get("play", {})}
                latest = work.world_scenarios.latest_world_revision(context, world_id)
                canon = dict((latest or {}).get("document", {}).get("canon") or {}) if isinstance(latest, dict) else {}
                approved = approved_inventions(world)
                # It may name another campaign invention only once that one is approved: the world's next
                # publication must find everything it names.
                own = draft["entry_id"]
                named = {text for text in _strings(entry) if text.startswith("gm:") and text != own
                         and not text.startswith(f"{own}:")}
                missing = sorted(named - {str(row.get("entry_id") or "") for row in approved.values()})
                if missing:
                    work.rollback()
                    raise HTTPException(status_code=422, detail={"ok": False, "error": "approve_what_it_names_first",
                                                                 "names": missing})
                taken = {str(dict(row).get("id") or "") for row in canon.get("entities") or () if isinstance(row, dict)}
                key = canon_id(draft["family"], draft["name"], taken | set(approved))
                approved[key] = {"entry_id": draft["entry_id"], "family": draft["family"], "name": draft["name"],
                                 "draft_id": draft_id, **entry}
                work.world_scenarios.replace_world_metadata(
                    context, world_id, {**dict(world.get("metadata") or {}), APPROVED_KEY: approved})
                work.rpg_lore_review.decide(context, draft_id, status="approved", entry=entry, canon_id=key)
            draft = work.rpg_lore_review.get(context, draft_id)
            work.commit()
        return {"ok": True, "world_id": world_id, "draft": draft}


__all__ = ["register_rpg_lore_review_routes"]
