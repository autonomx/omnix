"""Explicit compilation modes for World Forge drafts and certified releases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Sequence

from .contracts import WorldRevisionDocument
from .generation_actor_portfolio import actor_portfolio_report, require_valid_actor_portfolio
from .generation_audit_stages import two_stage_audit_report
from .generation_conflict_portfolio import conflict_portfolio_report, require_valid_conflict_portfolio
from .generation_cross_topic_duplicates import cross_topic_duplicate_field_report, require_no_cross_topic_duplicate_fields
from .generation_countervailing_powers import countervailing_power_report, require_valid_countervailing_powers
from .generation_economic_scale import economic_scale_report, require_valid_economic_scale
from .generation_entity_contamination import entity_identity_contamination_report, require_no_entity_identity_contamination
from .generation_finding_policy import finding_waiver_policy_report
from .generation_manifest_references import manifest_reference_report, require_manifest_reference_closure
from .generation_mission_portfolio import mission_portfolio_report, require_valid_mission_portfolio
from .generation_named_claims import objective_named_claim_report, require_resolved_objective_named_claims
from .generation_naming_portfolio import naming_portfolio_report, require_valid_naming_portfolio
from .generation_network_constraints import network_constraint_report, require_valid_network_constraints
from .generation_ordinary_life import ordinary_life_report, require_valid_ordinary_life
from .generation_profile_dossiers import profile_dossier_report, require_profile_dossier_quality
from .generation_profile_references import profile_reference_report, require_valid_profile_references
from .generation_publication import WorldGenerationPublication, compile_world_generation_publication
from .generation_resource_dependencies import require_valid_resource_dependencies, resource_dependency_report
from .generation_spatial_reachability import require_spatial_reachability, spatial_reachability_report
from .generation_strict_integrity import require_unique_canon_identifiers, strict_integrity_report

WorldGenerationCompilationMode = Literal["diagnostic_draft", "certified_release"]
Report = Mapping[str, Any]
ReportFn = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any] | None], dict[str, Any]]
RequireFn = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any] | None], Any]


@dataclass(frozen=True)
class WorldGenerationDiagnosticDraft:
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


def _review_rows(run: Mapping[str, Any], explicit: Sequence[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    if explicit is not None:
        return list(explicit)
    embedded = run.get("_review_results")
    if not isinstance(embedded, Sequence) or isinstance(embedded, (str, bytes)):
        return []
    return [row for row in embedded if isinstance(row, Mapping)]


def _graph_audits() -> tuple[tuple[str, ReportFn, RequireFn], ...]:
    """Resolve functions per call so tests can monkeypatch module-owned gates."""

    return (
        ("profile_reference_integrity", profile_reference_report, require_valid_profile_references),
        ("profile_dossier_quality", profile_dossier_report, require_profile_dossier_quality),
        ("manifest_reference_closure", manifest_reference_report, require_manifest_reference_closure),
        ("cross_topic_duplicate_fields", cross_topic_duplicate_field_report, require_no_cross_topic_duplicate_fields),
        ("mission_portfolio", mission_portfolio_report, require_valid_mission_portfolio),
        ("entity_identity_contamination", entity_identity_contamination_report, require_no_entity_identity_contamination),
        ("naming_portfolio", naming_portfolio_report, require_valid_naming_portfolio),
        ("conflict_portfolio", conflict_portfolio_report, require_valid_conflict_portfolio),
        ("actor_portfolio", actor_portfolio_report, require_valid_actor_portfolio),
        ("network_constraints", network_constraint_report, require_valid_network_constraints),
        ("spatial_reachability", spatial_reachability_report, require_spatial_reachability),
        ("resource_dependencies", resource_dependency_report, require_valid_resource_dependencies),
        ("economic_scale", economic_scale_report, require_valid_economic_scale),
        ("ordinary_life", ordinary_life_report, require_valid_ordinary_life),
        ("countervailing_powers", countervailing_power_report, require_valid_countervailing_powers),
    )


def _reports(topic_rows: list[Mapping[str, Any]], graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    values = {name: report(topic_rows, graph) for name, report, _require in _graph_audits()}
    values["strict_integrity"] = strict_integrity_report(topic_rows)
    values["objective_named_claims"] = objective_named_claim_report(topic_rows)
    return values


def _require_certified(topic_rows: list[Mapping[str, Any]], graph: Mapping[str, Any]) -> None:
    require_unique_canon_identifiers(topic_rows)
    for _name, _report, require in _graph_audits():
        require(topic_rows, graph)
    require_resolved_objective_named_claims(topic_rows)


def _certification(
    base: Mapping[str, Any],
    *,
    mode: WorldGenerationCompilationMode,
    reports: Mapping[str, Report],
    audit_stages: Report,
    finding_policy: Report,
) -> dict[str, Any]:
    payload = {
        **dict(base),
        "compilation_mode": mode,
        **{name: dict(report) for name, report in reports.items()},
        "audit_stages": dict(audit_stages),
        "finding_waiver_policy": dict(finding_policy),
    }
    missing = [str(value) for value in payload.get("missing_requirements") or () if str(value)]
    requirements = {**reports, "post_repair_audit": audit_stages, "finding_waiver_policy": finding_policy}
    for name, report in requirements.items():
        if not bool(report.get("passed")):
            payload["launch_ready"] = False
            missing.append(name)
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
    if mode not in {"diagnostic_draft", "certified_release"}:
        raise ValueError(f"unsupported_world_generation_compilation_mode:{mode}")
    graph = dict(run.get("graph") or {})
    reports = _reports(topic_rows, graph)
    finding_policy = finding_waiver_policy_report(_review_rows(run, review_results))
    if mode == "certified_release":
        _require_certified(topic_rows, graph)
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
    certification = _certification(
        publication.certification,
        mode=mode,
        reports=reports,
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


def compile_world_generation_diagnostic_draft(**kwargs: Any) -> WorldGenerationDiagnosticDraft:
    artifact = compile_world_generation_artifact(mode="diagnostic_draft", **kwargs)
    if not isinstance(artifact, WorldGenerationDiagnosticDraft):
        raise AssertionError("diagnostic_compilation_returned_release")
    return artifact


def compile_world_generation_certified_artifact(**kwargs: Any) -> WorldGenerationCertifiedArtifact:
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
