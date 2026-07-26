"""Trusted-authorship boundary for immutable world revisions and releases."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .contracts import (
    WorldReleaseDocument,
    WorldRevisionDocument,
    canonical_content_hash,
)
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
        if not run_id or not topic_hashes:
            raise ValueError(
                f"world_revision_generation_authorship_receipt_missing:{document.world_id}:{document.revision}"
            )
        # This provenance is emitted only by compile_world_generation_publication,
        # after generation_publication_guard has recursively validated every topic.
        return {
            "schema_version": "rpg_world_revision_authorship_receipt_v1",
            "publishable": True,
            "source": source,
            "generation_run_id": run_id,
            "topic_hashes": topic_hashes,
        }
    if source == "manual_world_authoring":
        report = require_publishable_authorship(document.canon)
        if int(report.get("lore_string_count") or 0) < 1:
            raise ValueError(f"world_revision_lore_required:{document.world_id}")
        return report
    raise ValueError(
        f"world_revision_authorship_untrusted:{document.world_id}:{document.revision}:{source or 'unknown'}"
    )


def require_release_authorship(
    revision: WorldRevisionDocument,
    release: WorldReleaseDocument,
) -> dict[str, Any]:
    """Require either explicit certification or the guarded generation compiler chain."""

    receipt = require_revision_authorship(revision)
    certification = dict(release.certification)
    if bool(certification.get("authorship_validated")):
        return {
            **receipt,
            "release_authorship_validated": True,
            "release_authorship_source": str(
                certification.get("authorship_source") or receipt.get("source") or ""
            ),
        }

    revision_provenance = dict(revision.provenance)
    compiler = dict(release.compiler_provenance)
    revision_run_id = str(revision_provenance.get("generation_run_id") or "")
    release_run_id = str(compiler.get("generation_run_id") or "")
    if (
        str(revision_provenance.get("source") or "") == "durable_world_generation"
        and str(compiler.get("compiler") or "")
        == "rpg_world_generation_publication_v2"
        and revision_run_id
        and release_run_id == revision_run_id
    ):
        return {
            **receipt,
            "release_authorship_validated": True,
            "release_authorship_source": "guarded_generation_compiler",
        }
    raise ValueError(
        f"world_release_authorship_uncertified:{revision.world_id}:"
        f"{revision.revision}:{release.release}"
    )


__all__ = [
    "prepare_direct_world_revision",
    "require_release_authorship",
    "require_revision_authorship",
]
