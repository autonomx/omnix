"""Proposals: what work done off the turn asks a later turn to fold in (evolution roadmap EV-11).

Narration's side effects, the game master's direction and an area's filled-in detail are model output, so they are
proposals, never changes. Each is typed by its ``kind``, and the rule that owns that kind (``FOLD_IN_OWNERS`` in
``session/turn/proposals.py``) reads it against the campaign and answers with the changes it makes, or why it
refuses: ``Folded``. The reducer applies what a rule accepts, as it applies any turn's changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .changes import StateChange

ProposalSource = Literal["narration", "game_master", "area", "panel"]


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str = Field(min_length=1, max_length=300)
    kind: str = Field(min_length=1, max_length=80)
    source: ProposalSource
    after_revision: int = Field(ge=0)  # the revision of the turn it came after
    reason: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    def recorded(self) -> dict[str, Any]:
        """As a turn row records it: enough to fold it in again on replay."""
        return self.model_dump(mode="json")


@dataclass(frozen=True)
class Folded:
    """What an owning rule makes of a proposal: its changes, or why it refuses (then it is dropped)."""

    changes: list[StateChange] = field(default_factory=list)
    refused: str = ""


def refused(reason: str) -> Folded:
    return Folded(refused=reason)


__all__ = ["Folded", "Proposal", "ProposalSource", "refused"]
