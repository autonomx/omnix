from __future__ import annotations

from typing import Any

from app.rpg.narrative_engine import (
    CampaignBibleSnapshot,
    WorldForgeProposal,
    apply_world_forge_proposal,
)

from .errors import EntityNotFound
from .tenant import TenantContext


def approve_world_forge_proposal(
    work: Any,
    context: TenantContext,
    *,
    proposal_id: str,
    expected_bible_revision: int,
    decision_note: str = "",
) -> dict[str, Any]:
    """Audit, approve, and apply a World Forge proposal in one transaction."""

    proposal_record = work.world_forge.get(context, proposal_id, for_update=True)
    if proposal_record is None:
        raise EntityNotFound(proposal_id)
    campaign_id = str(proposal_record["campaign_id"])
    bible_record = work.campaign_bibles.get(context, campaign_id, for_update=True)
    if bible_record is None:
        raise EntityNotFound(f"campaign bible:{campaign_id}")

    snapshot = CampaignBibleSnapshot.from_record(bible_record)
    proposal = WorldForgeProposal.from_dict(proposal_record["proposal"])
    document, audit = apply_world_forge_proposal(snapshot, proposal)
    report = audit.as_dict()
    if not audit.passed:
        decided = work.world_forge.decide(
            context,
            proposal_id=proposal_id,
            decision="rejected",
            consistency_report=report,
            decision_note=decision_note or "Rejected by deterministic contradiction audit.",
        )
        return {
            "approved": False,
            "proposal": decided,
            "campaign_bible": bible_record,
            "audit": report,
        }

    updated_bible = work.campaign_bibles.put(
        context,
        campaign_id=campaign_id,
        document=document,
        expected_revision=expected_bible_revision,
        provenance={
            "source": "world_forge_approval",
            "proposal_id": proposal_id,
            "proposal_hash": proposal.proposal_hash,
        },
        consistency_report=report,
        completeness=bible_record.get("completeness") or {},
    )
    decided = work.world_forge.decide(
        context,
        proposal_id=proposal_id,
        decision="approved",
        consistency_report=report,
        decision_note=decision_note,
    )
    return {
        "approved": True,
        "proposal": decided,
        "campaign_bible": updated_bible,
        "audit": report,
    }
