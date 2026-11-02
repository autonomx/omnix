"""Folding proposals in at a turn's load (evolution roadmap EV-11; production roadmap §4.1, step 1).

A turn reads the proposals still pending from earlier revisions (``omnix_rpg_proposals``), passes each through the
rule that owns its kind, and applies what the rule accepts with the reducer before the turn is planned, so the plan
sees it. A proposal no rule owns, or that its rule refuses, is dropped with the reason. The turn reports the set
(``turn_pipeline.proposals``); its commit settles each one while it is still pending and records the folded ones on
the turn row, and replay folds exactly that set in again (``fold_in``), whatever the store holds by then.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import importlib
import logging
from typing import Any, Callable, Iterable, Mapping

from pydantic import ValidationError

from app.apps.rpg.foundation.persistence.rpg_proposal_repository import record_proposals
from app.apps.rpg.foundation.safe_values import safe_dict as _d
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.changes import StateChange
from app.apps.rpg.foundation.state.proposals import Folded, Proposal
from app.apps.rpg.foundation.state.reducer import ChangeRejected, reduce

logger = logging.getLogger(__name__)

# Each kind of proposal and the rule that owns it ("module:function"): the function reads the campaign and the
# proposal's payload and answers ``Folded``. A kind not named here is dropped. The registry test checks each owner.
FOLD_IN_OWNERS: dict[str, str] = {
    "heard_of": "app.apps.rpg.rules.hero_knowledge:heard_of",
    # The game master's (EV-0): each kind accepted by the rule that owns what it changes.
    "gm_fact": "app.apps.rpg.rules.consequences:fold_fact",
    "gm_complication": "app.apps.rpg.rules.consequences:fold_complication",
    "gm_quest_offer": "app.apps.rpg.rules.quest.progress:fold_quest_offer",
    "gm_move_person": "app.apps.rpg.rules.routines:fold_move",
    "gm_encounter": "app.apps.rpg.rules.combat.encounters:fold_encounter",
    "gm_beat": "app.apps.rpg.rules.routines:fold_beat",  # a person's next beat brought forward (EV-4)
    "gm_rumour": "app.apps.rpg.rules.rumours:fold_rumour",
    "gm_invent": "app.apps.rpg.rules.inventions:fold_invention",  # part 2: what the story needs and the world lacks
    "gm_area": "app.apps.rpg.rules.inventions:fold_area_entry",  # an area's detail, filled in ahead (EV-10)
}
# A turn folds in at most this many of an area's entries, places first, then people, then the rest (EV-10); the
# others stay pending for the turns after.
AREA_ENTRIES_PER_TURN = 10
AREA_BYTES_PER_TURN = 24 * 1024
_AREA_ORDER = {"place": 0, "site": 1, "person": 2}


def _owner(kind: str) -> Callable[[Mapping[str, Any], Mapping[str, Any]], Folded] | None:
    named = FOLD_IN_OWNERS.get(kind)
    if not named:
        return None
    module, function = named.split(":")
    return getattr(importlib.import_module(module), function)


@dataclass(frozen=True)
class FoldRecord:
    """What a turn folded in at its load, and what it dropped."""

    folded: tuple[Proposal, ...] = ()
    dropped: tuple[tuple[Proposal, str], ...] = ()
    changes: tuple[StateChange, ...] = field(default=())
    replayed: bool = False  # folded from a turn row's recorded set, not from the store (``replay_folded``)

    def reported(self) -> dict[str, Any]:
        return {"folded": [proposal.recorded() for proposal in self.folded],
                "dropped": [{**proposal.recorded(), "drop_reason": reason} for proposal, reason in self.dropped],
                **({"replayed": True} if self.replayed else {})}

    def __bool__(self) -> bool:
        return bool(self.folded or self.dropped)


def fold_in(document: dict[str, Any], proposals: Iterable[Proposal]) -> tuple[dict[str, Any], FoldRecord]:
    """The document with each proposal its rule accepts applied, in order; pure. An area's entries come at most
    ``AREA_ENTRIES_PER_TURN`` (and ``AREA_BYTES_PER_TURN``) a turn, places first; the rest wait for later turns."""
    folded: list[Proposal] = []
    dropped: list[tuple[Proposal, str]] = []
    changes: list[StateChange] = []
    for proposal in _capped(list(proposals)):
        owner = _owner(proposal.kind)
        if owner is None:
            dropped.append((proposal, f"no rule owns proposals of the kind {proposal.kind!r}"))
            continue
        try:
            answer = owner(document, proposal.payload)
        except (ValidationError, ValueError, TypeError) as exc:  # a payload its rule cannot read
            dropped.append((proposal, f"unreadable: {type(exc).__name__}"))
            continue
        if answer.refused:
            dropped.append((proposal, answer.refused))
            continue
        try:
            document, _ = reduce(document, list(answer.changes))
        except ChangeRejected as exc:
            dropped.append((proposal, f"rejected: {exc}"))
            continue
        folded.append(proposal)
        changes.extend(answer.changes)
    return document, FoldRecord(folded=tuple(folded), dropped=tuple(dropped), changes=tuple(changes))


def _capped(proposals: list[Proposal]) -> list[Proposal]:
    import json

    area = sorted((proposal for proposal in proposals if proposal.kind == "gm_area"),
                  key=lambda proposal: _AREA_ORDER.get(str(_d(proposal.payload.get("entry")).get("kind") or ""), 3))
    taken: list[Any] = []
    size = 0
    for proposal in area[:AREA_ENTRIES_PER_TURN]:
        size += len(json.dumps(dict(proposal.payload), ensure_ascii=False))
        if taken and size > AREA_BYTES_PER_TURN:
            break
        taken.append(proposal)
    chosen = {id(proposal) for proposal in taken}
    return [proposal for proposal in proposals if proposal.kind != "gm_area"] + \
        [proposal for proposal in area if id(proposal) in chosen]


def pending_proposals(session_id: str, document: Mapping[str, Any]) -> list[Proposal]:
    """The proposals pending for the campaign from the revision it stands at or earlier, in folding order."""
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    revision = int(_d(_sections.runtime_state_of(document)).get("state_revision") or 0)
    with unit_of_work() as work:
        rows = work.rpg_proposals.pending(current_tenant(), session_id, through_revision=revision)
        work.rollback()
    proposals = []
    for row in rows:
        try:
            proposals.append(Proposal.model_validate({key: row[key] for key in Proposal.model_fields}))
        except ValidationError:  # a row the record cannot read is not folded in, and stays for review
            logger.warning("rpg_proposal_unreadable session=%s proposal=%s", session_id, row.get("proposal_id"))
    return proposals


_FOLDED: ContextVar[FoldRecord | None] = ContextVar("RPG_TURN_FOLDED", default=None)


_REPLAY: dict[str, list[Proposal]] = {}  # a campaign's next turn's recorded set, when it is being re-executed
# Whether the turn's own gate read found a proposal pending for its campaign (``note_pending``): a turn with none
# reads no proposals (F2). One recorded after the gate read is folded in by the next turn.
_PENDING: ContextVar[tuple[str, bool] | None] = ContextVar("rpg_proposals_pending", default=None)


def note_pending(session_id: str, pending: bool) -> None:
    """What the turn's gate read found: whether a proposal is pending for ``session_id``."""
    _PENDING.set((session_id, pending))


def replay_folded(session_id: str, recorded: list[Mapping[str, Any]]) -> None:
    """Re-execute the campaign's next turn with ``recorded`` (a turn row's ``folded_proposals_jsonb`` ``folded``) as
    what its load folds in, in place of the store's pending proposals (D1's re-executing replay)."""
    _REPLAY[session_id] = [Proposal.model_validate({key: row[key] for key in Proposal.model_fields if key in row})
                           for row in recorded]


def fold_at_load(session_id: str, document: dict[str, Any]) -> dict[str, Any]:
    """Step 1's fold-in: the turn-start campaign with its pending proposals folded in (or, re-executed, the set its
    turn row recorded); the record is kept for the turn to report (``take_folded``)."""
    replayed = _REPLAY.pop(session_id, None) if session_id else None
    hint, _ = _PENDING.get(), _PENDING.set(None)  # once a gate read: a later load reads the store again
    none_pending = hint is not None and hint == (session_id, False)
    proposals = (replayed if replayed is not None else [] if none_pending
                 else pending_proposals(session_id, document) if session_id else [])
    document, record = fold_in(document, proposals) if proposals else (document, FoldRecord())
    if replayed is not None:
        record = FoldRecord(folded=record.folded, dropped=record.dropped, changes=record.changes, replayed=True)
    _FOLDED.set(record)
    return document


def take_folded() -> FoldRecord:
    """What this turn's load folded in, once: a second turn in the same context starts from nothing."""
    record = _FOLDED.get() or FoldRecord()
    _FOLDED.set(None)
    return record


def settle_folded(work: Any, context: Any, *, campaign_id: str, turn_id: str, revision: int,
                  reported: Mapping[str, Any]) -> dict[str, Any] | None:
    """At commit: mark each proposal the turn folded in or dropped, while still pending (else the commit fails);
    what the turn row records of it, or None when the turn folded nothing in."""
    folded = [row for row in reported.get("folded") or () if isinstance(row, Mapping)]
    dropped = [row for row in reported.get("dropped") or () if isinstance(row, Mapping)]
    if not folded and not dropped:
        return None
    if reported.get("replayed") is True:  # re-executed from the recorded set: nothing in the store to settle
        return {"folded": folded, "dropped": [str(row["proposal_id"]) for row in dropped]}
    work.rpg_proposals.settle(context, campaign_id=campaign_id, turn_id=turn_id, revision=revision,
                              folded=[str(row["proposal_id"]) for row in folded],
                              dropped=[(str(row["proposal_id"]), str(row.get("drop_reason") or "")) for row in dropped])
    return {"folded": folded, "dropped": [str(row["proposal_id"]) for row in dropped]}


__all__ = ["FOLD_IN_OWNERS", "FoldRecord", "fold_at_load", "fold_in", "note_pending", "pending_proposals",
           "record_proposals", "replay_folded",
           "settle_folded", "take_folded"]
