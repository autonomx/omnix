"""Trusted-authorship boundary for immutable world revisions and releases."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .contracts import WorldRevisionDocument, canonical_content_hash
from .generation_authorship_runtime import (
    attach_human_authorship,
    require_publishable_authorship,
)


def prepare_direct_world_revision(
    world: Mapping[str, Any],
    document: WorldRevisionDocument,
) -> WorldRevisionDocument:
    """Permit direct publication only for explicitly manual worlds.

    Provider-backed, hybrid, and imported worlds must publish through the durable
    generation pipeline so a client cannot submit arbitrary canon while claiming AI
    provenance. Direct manual canon is recorded as a server-created human event.
    """

    source_mode = str(world.get("source_mode") or "manual")
    if source_mode != "manual":
        raise ValueError(
            f"world_revision_requires_guarded_generation:{document.world_id}:{source_mode}"
        )
    event_id = (
        f"humanrevision:{document.world_id}:{document.revision}:"
        f"{datetime.now(timezone.utc).isoformat()}"
    )
    authored_canon = attach_human_authorship(
        document.canon,
        event_id=event_id,
        prior_candidate=None,
        edited_llm=False,
    )
    report = require_publishable_authorship(authored_canon)
    if int(report.get("lore_string_count") or 0) < 1:
        raise ValueError(f"world_revision_lore_required:{document.world_id}")
    payload = document.model_dump(mode="json")
    payload["canon"] = authored_canon
    payload["provenance"] = {
        **dict(document.provenance),
        "source": "manual_world_authoring",
        "human_authorship_event_id": event_id,
        "authorship_validation": report,
    }
    payload["content_hash"] = ""
    payload["content_hash"] = canonical_content_hash(payload)
    return WorldRevisionDocument.model_validate(payload)


def require_revision_authorship(document: WorldRevisionDocument) -> dict[str, Any]:
    """Reject immutable revisions not produced by a trusted server path."""

    provenance = dict(document.provenance)
    source = str(provenance.get("source") or "")
    if source == "durable_world_generation":
        run_id = str(provenance.get("generation_run_id") or "")
        topic_hashes = dict(provenance.get("topic_hashes") or {})
        receipt = dict(provenance.get("authorship_validation") or {})
        if not run_id or not topic_hashes or not bool(receipt.get("publishable")):
            raise ValueError(
                f"world_revision_generation_authorship_receipt_missing:{document.world_id}:{document.revision}"
            )
        return receipt
    if source == "manual_world_authoring":
        report = require_publishable_authorship(document.canon)
        if int(report.get("lore_string_count") or 0) < 1:
            raise ValueError(f"world_revision_lore_required:{document.world_id}")
        return report
    raise ValueError(
        f"world_revision_authorship_untrusted:{document.world_id}:{document.revision}:{source or 'unknown'}"
    )


__all__ = ["prepare_direct_world_revision", "require_revision_authorship"]
