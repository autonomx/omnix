"""Explicit compilation modes for World Forge drafts and certified releases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from .contracts import WorldRevisionDocument
from .generation_audit_stages import two_stage_audit_report
from .generation_cross_topic_duplicates import (
    cross_topic_duplicate_field_report,
    require_no_cross_topic_duplicate_fields,
)
from .generation_entity_contamination import (
    entity_identity_contamination_report,
    require_no_entity_identity_contamination,
)
from .generation_finding_policy import finding_waiver_policy_report
from .generation_manifest_references import (
    manifest_reference_report,
    require_manifest_reference_closure,
)
from .generation_mission_portfolio import (
    mission_portfolio_report,
    require_valid_mission_portfolio,
)
from .generation_named_claims import (
    objective_named_claim_report,
    require_resolved_objective_named_claims,
)
from .generation_naming_portfolio import (
    naming_portfolio_report,
    require_valid_naming_portfolio,
)
from .generation_profile_dossiers import (
    profile_dossier_report,
    require_profile_dossier_quality,
)
from .generation_profile_references import (
    profile_reference_report,
    require_valid_profile_references,
)
from .generation_publication import (
    WorldGenerationPublication,
    compile_world_generation_publication,
)
from .generation_strict_integrity import (
    require_unique_canon_identifiers,
    strict_integrity_report,
)

WorldGenerationCompilationMode = Literal["diagnostic_draft", "certified_release"]


@dataclass(frozen=True)
class WorldGenerationDiagnosticDraft:
    """A non-release artifact suitable for review, export, and preview tooling."""

    world_revision: WorldRevisionDocument
    certification: Mapping[str, Any]
    artifact_stage: str
    runtime_seed: Mapping[str, Any]
    materialization: Mapping[str, Any]
    playtest_report: Mapping[str, Any]
    mode: Literal["diagnostic_draft"] = "diagnostic_draft"

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "world_revision": self.world_revision.model_dump(mode="json"),
            "certification": dict(self.certification),
            "artifact_stage": self.artifact_stage,
            "runtime_seed": dict(self.runtime_seed),
            "materialization": dict(self.materialization),
            "playtest_report": dict(self.playtest_report),
        }


@dataclass(frozen=True)
class WorldGenerationCertifiedArtifact:
    """A release-shaped artifact reserved for the certified publication path."""

    publication: WorldGenerationPublication
    mode: Literal["certified_release"] = "certified_release"

    @property
    def world_revision(self) -> WorldRevisionDocument:
        return self.publication.world_revision

    @property
    def certification(self) -> Mapping[str, Any]:
        return self.publication.certification

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, **self.publication.as_dict()}


def _review_rows(
    run: Mapping[str, Any],
    explicit: Sequence[Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]]:
    if explicit is not None:
        return list(explicit)
    embedded = run.get("_review_results")
    if not isinstance(embedded, Sequence) or isinstance(embedded, (str, bytes)):
        return []
    return [row for row in embedded if isinstance(row, Mapping)]


def _certification_with_integrity(
    certification: Mapping[str, Any],
    *,
    mode: WorldGenerationCompilationMode,
    integrity: Mapping[str, Any],
    profile_references: Mapping[str, Any],
    profile_dossiers: Mapping[str, Any],
    manifest_references: Mapping[str, Any],
    cross_topic_duplicates: Mapping[str, Any],
    mission_portfolio: Mapping[str, Any],
    objective_named_claims: Mapping[str, Any],
    entity_identity_contamination: Mapping[str, Any],
    naming_portfolio: Mapping[str, Any],
    audit_stages: Mapping[str, Any],
    finding_policy: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        **dict(certification),
        "compilation_mode": mode,
        "strict_integrity": dict(integrity),
        "profile_reference_integrity": dict(profile_references),
        "profile_dossier_quality": dict(profile_dossiers),
        "manifest_reference_closure": dict(manifest_references),
        "cross_topic_duplicate_fields": dict(cross_topic_duplicates),
        "mission_portfolio": dict(mission_portfolio),
        "objective_named_claims": dict(objective_named_claims),
        "entity_identity_contamination": dict(entity_identity_contamination),
        "naming_portfolio": dict(naming_portfolio),
        "audit_stages": dict(audit_stages),
        "finding_waiver_policy": dict(finding_policy),
    }
    missing = [
        str(value)
        for value in payload.get("missing_requirements") or ()
        if str(value)
    ]
    for passed, requirement in (
        (integrity.get("passed"), "strict_integrity"),
        (profile_references.get("passed"), "profile_reference_integrity"),
        (profile_dossiers.get("passed"), "profile_dossier_quality"),
        (manifest_references.get("passed"), "manifest_reference_closure"),
        (cross_topic_duplicates.get("passed"), "cross_topic_duplicate_fields"),
        (mission_portfolio.get("passed"), "mission_portfolio"),
        (objective_named_claims.get("passed"), "objective_named_claims"),
        (entity_identity_contamination.get("passed"), "entity_identity_contamination"),
        (naming_portfolio.get("passed"), "naming_portfolio"),
        (audit_stages.get("passed"), "post_repair_audit"),
        (finding_policy.get("passed"), "finding_waiver_policy"),
    ):
        if not bool(passed):
            payload["launch_ready"] = False
            missing.append(requirement)
    payload["missing_requirements"] = list(dict.fromkeys(missing))
    return payload


def compile_world_generation_artifact(
    *,
    mode: WorldGenerationCompilationMode,
    run: Mapping[str, Any],
    world: Mapping[str, Any],
    topic_rows: list[Mapping[str, Any]],
    revision: int,
    starting_location_override: str = "",
    asset_bindings: Mapping[str, Any] | None = None,
    review_results: Sequence[Mapping[str, Any]] | None = None,
) -> WorldGenerationDiagnosticDraft | WorldGenerationCertifiedArtifact:
    """Compile one immutable snapshot while exposing only mode-appropriate output."""

    if mode not in {"diagnostic_draft", "certified_release"}:
        raise ValueError(f"unsupported_world_generation_compilation_mode:{mode}")
    topic_graph = dict(run.get("graph") or {})
    integrity = strict_integrity_report(topic_rows)
    profile_references = profile_reference_report(topic_rows, topic_graph)
    profile_dossiers = profile_dossier_report(topic_rows, topic_graph)
    manifest_references = manifest_reference_report(topic_rows, topic_graph)
    cross_topic_duplicates = cross_topic_duplicate_field_report(
        topic_rows,
        topic_graph,
    )
    mission_portfolio = mission_portfolio_report(topic_rows, topic_graph)
    objective_named_claims = objective_named_claim_report(topic_rows)
    entity_identity_contamination = entity_identity_contamination_report(
        topic_rows,
        topic_graph,
    )
    naming_portfolio = naming_portfolio_report(topic_rows, topic_graph)
    finding_policy = finding_waiver_policy_report(_review_rows(run, review_results))
    if mode == "certified_release":
        require_unique_canon_identifiers(topic_rows)
        require_valid_profile_references(topic_rows, topic_graph)
        require_profile_dossier_quality(topic_rows, topic_graph)
        require_manifest_reference_closure(topic_rows, topic_graph)
        require_no_cross_topic_duplicate_fields(topic_rows, topic_graph)
        require_valid_mission_portfolio(topic_rows, topic_graph)
        require_resolved_objective_named_claims(topic_rows)
        require_no_entity_identity_contamination(topic_rows, topic_graph)
        require_valid_naming_portfolio(topic_rows, topic_graph)
    publication = compile_world_generation_publication(
        run=run,
        world=world,
        topic_rows=topic_rows,
        revision=revision,
        starting_location_override=starting_location_override,
        asset_bindings=asset_bindings,
    )
    consistency = publication.certification.get("consistency_report")
    audit_stages = two_stage_audit_report(
        topic_rows,
        dict(consistency) if isinstance(consistency, Mapping) else None,
        default_post_passed=bool(publication.certification.get("launch_ready")),
    )
    certification = _certification_with_integrity(
        publication.certification,
        mode=mode,
        integrity=integrity,
        profile_references=profile_references,
        profile_dossiers=profile_dossiers,
        manifest_references=manifest_references,
        cross_topic_duplicates=cross_topic_duplicates,
        mission_portfolio=mission_portfolio,
        objective_named_claims=objective_named_claims,
        entity_identity_contamination=entity_identity_contamination,
        naming_portfolio=naming_portfolio,
        audit_stages=audit_stages,
        finding_policy=finding_policy,
    )
    if mode == "certified_release":
        return WorldGenerationCertifiedArtifact(
            publication=WorldGenerationPublication(
                world_revision=publication.world_revision,
                world_release=publication.world_release,
                certification=certification,
            )
        )
    release = publication.world_release
    return WorldGenerationDiagnosticDraft(
        world_revision=publication.world_revision,
        certification=certification,
        artifact_stage=str(release.artifact_stage),
        runtime_seed=dict(release.runtime_seed),
        materialization=dict(release.materialization),
        playtest_report=dict(release.playtest_report),
    )


def compile_world_generation_diagnostic_draft(
    **kwargs: Any,
) -> WorldGenerationDiagnosticDraft:
    artifact = compile_world_generation_artifact(mode="diagnostic_draft", **kwargs)
    if not isinstance(artifact, WorldGenerationDiagnosticDraft):
        raise AssertionError("diagnostic_compilation_returned_release")
    return artifact


def compile_world_generation_certified_artifact(
    **kwargs: Any,
) -> WorldGenerationCertifiedArtifact:
    artifact = compile_world_generation_artifact(mode="certified_release", **kwargs)
    if not isinstance(artifact, WorldGenerationCertifiedArtifact):
        raise AssertionError("certified_compilation_returned_draft")
    return artifact


__all__ = [
    "WorldGenerationCertifiedArtifact",
    "WorldGenerationCompilationMode",
    "WorldGenerationDiagnosticDraft",
    "compile_world_generation_artifact",
    "compile_world_generation_certified_artifact",
    "compile_world_generation_diagnostic_draft",
]
