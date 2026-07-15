"""Final exact-head release certification for the Unified RPG Narrative Engine."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .authority import BeatKind, BeatPurpose, DeliveryMode
from .contracts import (
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    GenerationMetadata,
    NarrativeBlock,
    ValidationReport,
)
from .delivery import (
    InMemoryNarrativeDeliveryRepository,
    NarrativeDeliveryCoordinator,
)
from .legacy_retirement import audit_legacy_publisher_retirement
from .publisher_audit import audit_publisher_ownership


_REQUIRED_WORKFLOWS = (
    "RPG Phase 0 architecture compliance",
    "PostgreSQL persistence gates",
    "Live Chat hardening gates",
    "RPG deterministic PR gates",
)
_REQUIRED_MIGRATIONS = tuple(
    f"src/app/persistence/migrations/{number:04d}_{name}.sql"
    for number, name in (
        (17, "rpg_campaign_bible"),
        (18, "rpg_world_forge"),
        (19, "rpg_hermes_narrative_research"),
        (20, "rpg_narrative_responses"),
        (21, "rpg_campaign_genesis"),
        (22, "rpg_narrative_delivery"),
        (23, "rpg_narrative_retirement"),
    )
)
_REQUIRED_PRODUCTION_FILES = (
    "src/app/rpg/narrative_engine/service.py",
    "src/app/rpg/narrative_engine/production_path.py",
    "src/app/rpg/narrative_engine/legacy_retirement.py",
    "src/app/rpg/narrative_delivery.py",
    "src/app/rpg/narrative_retirement.py",
    "src/app/gateway/rpg_turn_pipeline.py",
    "src/app/gateway/rpg_narrative_delivery_routes.py",
    "src/app/rpg/session/genesis/async_coordinator.py",
    "src/app/rpg/session/genesis/world_forge_provider.py",
)
_REQUIRED_PHASE_TESTS = tuple(
    f"src/tests/rpg/response_generation/test_rne_phase{phase}_{suffix}.py"
    for phase, suffix in (
        (25, "canonical_semantics"),
        (26, "knowledge_grants"),
        (27, "semantic_claims"),
        (28, "production_writer"),
        (29, "direct_dialogue_replacement"),
        (30, "single_orchestration"),
        (31, "postgres_repository"),
        (32, "turn_idempotency"),
        (33, "atomic_turn_persistence"),
        (34, "runtime_repository_authority"),
        (35, "durable_submission_replay"),
        (36, "production_world_forge"),
        (37, "world_forge_commit_gate"),
        (38, "world_forge_dossier_quality"),
        (39, "async_campaign_genesis"),
        (40, "deferred_delivery"),
        (41, "legacy_retirement"),
    )
)
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class FinalNarrativeReleaseBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class FinalNarrativeReleaseEvidence:
    expected_head_sha: str
    observed_head_sha: str
    workflow_conclusions: Mapping[str, str]
    retirement_snapshot: Mapping[str, Any]
    provider_free_ci: bool = True
    live_provider_execution_claimed: bool = False
    evidence_origin: str = "github_actions_and_postgresql_integration"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "FinalNarrativeReleaseEvidence":
        return cls(
            expected_head_sha=str(value.get("expected_head_sha") or "").strip(),
            observed_head_sha=str(value.get("observed_head_sha") or "").strip(),
            workflow_conclusions={
                str(name): str(conclusion).casefold()
                for name, conclusion in dict(
                    value.get("workflow_conclusions") or {}
                ).items()
            },
            retirement_snapshot=dict(value.get("retirement_snapshot") or {}),
            provider_free_ci=bool(value.get("provider_free_ci", True)),
            live_provider_execution_claimed=bool(
                value.get("live_provider_execution_claimed", False)
            ),
            evidence_origin=str(
                value.get("evidence_origin")
                or "github_actions_and_postgresql_integration"
            ),
            metadata=dict(value.get("metadata") or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected_head_sha": self.expected_head_sha,
            "observed_head_sha": self.observed_head_sha,
            "workflow_conclusions": dict(self.workflow_conclusions),
            "retirement_snapshot": dict(self.retirement_snapshot),
            "provider_free_ci": self.provider_free_ci,
            "live_provider_execution_claimed": self.live_provider_execution_claimed,
            "evidence_origin": self.evidence_origin,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FinalNarrativeReleaseCertification:
    passed: bool
    head_sha: str
    checks: Mapping[str, bool]
    violations: tuple[str, ...]
    diagnostics: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "head_sha": self.head_sha,
            "checks": dict(self.checks),
            "violations": list(self.violations),
            "diagnostics": dict(self.diagnostics),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _all_files_present(root: Path, paths: tuple[str, ...]) -> tuple[bool, list[str]]:
    missing = [relative for relative in paths if not (root / relative).is_file()]
    return not missing, missing


def _deferred_delivery_certified() -> tuple[bool, dict[str, Any]]:
    response = CanonicalNarrativeResponse(
        response_id="release:delivery",
        request_id="release:delivery:request",
        turn_id="release:delivery:turn",
        campaign_id="release:campaign",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id="release:block:1",
                beat_id="release:beat:1",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.PHYSICAL_REACTION,
                text="The first canonical block remains first.",
            ),
            NarrativeBlock(
                block_id="release:block:2",
                beat_id="release:beat:2",
                sequence=2,
                kind=BeatKind.DIALOGUE,
                purpose=BeatPurpose.DIRECT_ANSWER,
                text="Delivery changes timing, not meaning.",
                speaker_id="npc:release",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="release-certification"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()
    repository = InMemoryNarrativeDeliveryRepository()
    coordinator = NarrativeDeliveryCoordinator()
    pending = coordinator.open(response, DeliveryMode.DEFERRED, repository)
    first, event = coordinator.publish_next(
        response,
        repository,
        expected_semantic_hash=response.semantic_hash,
    )
    replay = coordinator.resume(
        response,
        repository,
        expected_semantic_hash=response.semantic_hash,
        after_index=-1,
    )
    completed, second_event = coordinator.publish_next(
        response,
        repository,
        expected_semantic_hash=response.semantic_hash,
    )
    checks = {
        "pending_deferred": pending.delivery.status == "pending",
        "first_block_ordered": (
            event is not None and event.block.block_id == response.blocks[0].block_id
        ),
        "resume_replays_first": (
            len(replay) == 1 and replay[0].block.block_id == response.blocks[0].block_id
        ),
        "second_block_ordered": (
            second_event is not None
            and second_event.block.block_id == response.blocks[1].block_id
        ),
        "completed": completed.delivery.status == "complete",
        "semantic_hash_stable": (
            pending.semantic_hash
            == first.semantic_hash
            == completed.semantic_hash
            == response.semantic_hash
        ),
    }
    return all(checks.values()), checks


def certify_final_narrative_release(
    repository_root: Path,
    evidence: FinalNarrativeReleaseEvidence,
) -> FinalNarrativeReleaseCertification:
    root = repository_root.resolve()
    publisher_audit = audit_publisher_ownership(root)
    deletion_audit = audit_legacy_publisher_retirement(root)
    migrations_present, missing_migrations = _all_files_present(
        root,
        _REQUIRED_MIGRATIONS,
    )
    production_files_present, missing_production_files = _all_files_present(
        root,
        _REQUIRED_PRODUCTION_FILES,
    )
    phase_tests_present, missing_phase_tests = _all_files_present(
        root,
        _REQUIRED_PHASE_TESTS,
    )
    delivery_passed, delivery_checks = _deferred_delivery_certified()
    conclusions = dict(evidence.workflow_conclusions)
    required_workflows_present = all(
        name in conclusions for name in _REQUIRED_WORKFLOWS
    )
    required_workflows_success = all(
        conclusions.get(name) == "success" for name in _REQUIRED_WORKFLOWS
    )
    retirement = dict(evidence.retirement_snapshot)
    checks = {
        "head_sha_is_full_commit": bool(
            _SHA_PATTERN.fullmatch(evidence.observed_head_sha)
        ),
        "exact_head_matches": (
            evidence.expected_head_sha == evidence.observed_head_sha
            and bool(_SHA_PATTERN.fullmatch(evidence.expected_head_sha))
        ),
        "required_workflows_present": required_workflows_present,
        "required_workflows_success": required_workflows_success,
        "provider_free_ci_declared": evidence.provider_free_ci,
        "live_provider_execution_not_fabricated": (
            not evidence.live_provider_execution_claimed
        ),
        "publisher_ownership_audit_passed": publisher_audit.passed,
        "legacy_deletion_audit_passed": deletion_audit.passed,
        "required_migrations_present": migrations_present,
        "required_production_files_present": production_files_present,
        "required_phase_tests_present": phase_tests_present,
        "deferred_delivery_resume_certified": delivery_passed,
        "retirement_records_present": int(retirement.get("record_count") or 0) > 0,
        "retirement_zero_alternate_publishers": (
            retirement.get("zero_alternate_publishers") is True
            and int(retirement.get("alternate_publish_count") or 0) == 0
        ),
        "retirement_deletion_certified": (
            retirement.get("legacy_publisher_deletion_certified") is True
            and int(retirement.get("violation_count") or 0) == 0
        ),
    }
    violations = tuple(name for name, passed in checks.items() if not passed)
    return FinalNarrativeReleaseCertification(
        passed=not violations,
        head_sha=evidence.observed_head_sha,
        checks=checks,
        violations=violations,
        diagnostics={
            "required_workflows": list(_REQUIRED_WORKFLOWS),
            "workflow_conclusions": conclusions,
            "publisher_audit": publisher_audit.as_dict(),
            "legacy_deletion_audit": deletion_audit.as_dict(),
            "delivery_checks": delivery_checks,
            "retirement_snapshot": retirement,
            "missing_migrations": missing_migrations,
            "missing_production_files": missing_production_files,
            "missing_phase_tests": missing_phase_tests,
            "evidence_origin": evidence.evidence_origin,
            "provider_boundary": (
                "hosted_ci_provider_free; live-provider quality remains local evidence"
            ),
            "metadata": dict(evidence.metadata),
        },
    )


def require_final_narrative_release(
    repository_root: Path,
    evidence: FinalNarrativeReleaseEvidence,
) -> FinalNarrativeReleaseCertification:
    certification = certify_final_narrative_release(repository_root, evidence)
    if not certification.passed:
        raise FinalNarrativeReleaseBlocked(
            "Unified RPG Narrative Engine release certification failed: "
            + ", ".join(certification.violations)
        )
    return certification
