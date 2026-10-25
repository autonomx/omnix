"""Write a world author's play sections into each new publication (RQ-4.1).

The world editor keeps the author's sections with the world (``play_section_authoring``); a publication (a
generation run's, or a repair's from the world's topics) compiles canon from the lore and then writes them in, as it
does authored map blueprints. A draft whose references the world lacks stops the publication here, naming them,
rather than at launch.
"""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import WorldReleaseDocument, WorldRevisionDocument
from .generation_jobs import canonical_hash
from .semantic_validation import play_section_release_findings
from .service import compile_world_release, compile_world_revision
from .world_play_sections import PlaySectionsDraft, draft_findings, unknown_creatures, with_play_sections

PLAY_SECTIONS_KEY = "play_sections"  # the world's metadata entry holding the author's draft


def authored_play_sections(world: Mapping[str, Any]) -> PlaySectionsDraft | None:
    """The author's draft kept with the world, or None when they have saved none."""
    stored = dict(world.get("metadata") or {}).get(PLAY_SECTIONS_KEY)
    if not isinstance(stored, Mapping):
        return None
    draft, findings = draft_findings(stored.get("document"))
    if draft is None:
        raise ValueError("world_play_sections_invalid:" + ",".join(findings[:5]))
    return draft


def play_sections_hash(draft: PlaySectionsDraft | None) -> str:
    """What a publication records of the draft it wrote in (its revision's ``authored_play_sections``); "" for none."""
    return canonical_hash(draft.model_dump(mode="json", exclude_none=True)) if draft is not None else ""


def merge_authored_play_sections(
    world_revision: WorldRevisionDocument,
    world_release: WorldReleaseDocument,
    draft: PlaySectionsDraft | None,
) -> tuple[WorldRevisionDocument, WorldReleaseDocument]:
    if draft is None:
        return world_revision, world_release
    revision = compile_world_revision(
        world_id=world_revision.world_id,
        revision=world_revision.revision,
        title=world_revision.title,
        canon=with_play_sections(world_revision.canon, draft),
        entity_manifest=world_revision.entity_manifest,
        topology=world_revision.topology,
        adventure_seeds=world_revision.adventure_seeds,
        blueprint_requirements=world_revision.blueprint_requirements,
        provenance={**dict(world_revision.provenance), "authored_play_sections": play_sections_hash(draft)},
    )
    findings = (*unknown_creatures(world_revision.canon, draft), *play_section_release_findings(revision))
    if findings:
        raise ValueError("world_play_sections_invalid:" + ",".join(findings[:5]))
    release = compile_world_release(
        revision,
        release=world_release.release,
        map_bindings=world_release.map_bindings,
        indexes=world_release.indexes,
        asset_bindings=world_release.asset_bindings,
        compiler_provenance={**dict(world_release.compiler_provenance), "authored_play_sections": True},
        certification=dict(world_release.certification),
        artifact_stage=world_release.artifact_stage,
        runtime_seed=world_release.runtime_seed,
        materialization=world_release.materialization,
        playtest_report=world_release.playtest_report,
    )
    return revision, release


__all__ = ["PLAY_SECTIONS_KEY", "authored_play_sections", "merge_authored_play_sections", "play_sections_hash"]
