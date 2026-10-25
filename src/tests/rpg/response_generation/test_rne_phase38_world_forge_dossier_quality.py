"""World Forge's quality audit (still the library's publication gate): provider provenance, fact authority."""
from __future__ import annotations

from app.apps.rpg.genesis.forge.canon_audit import CanonAuditReport
from app.apps.rpg.genesis.forge.world_forge_generation import GeneratedTopic
from app.apps.rpg.genesis.forge.world_forge_quality import (
    apply_world_forge_quality_audit,
)


def test_live_topic_requires_provider_provenance() -> None:
    report = apply_world_forge_quality_audit(
        (
            GeneratedTopic(
                topic_id="realm",
                provenance={
                    "generator": "structured_world_forge_provider_v1",
                    "attempt_count": 1,
                },
            ),
        ),
        CanonAuditReport(passed=True),
    )
    codes = {issue.code for issue in report.issues}

    assert report.passed is False
    assert "incomplete_provider_provenance" in codes


def test_generated_facts_remain_proposals_until_canon_compilation() -> None:
    report = apply_world_forge_quality_audit(
        (
            GeneratedTopic(
                topic_id="realm",
                entities=(
                    {
                        "id": "realm:phase38",
                        "name": "Phase 38 Realm",
                        "kind": "realm",
                        "visibility": "public",
                    },
                ),
                facts=(
                    {
                        "id": "fact:phase38",
                        "content": "Phase 38 establishes a connected realm.",
                        "authority": "objective_canon",
                        "approved_authority": "objective_canon",
                        "visibility": "public",
                        "entity_refs": ["realm:phase38"],
                    },
                ),
                provenance={"generator": "phase38_fixture"},
            ),
        ),
        CanonAuditReport(passed=True),
    )
    codes = {issue.code for issue in report.issues}

    assert report.passed is False
    assert "invalid_generated_fact_authority" in codes
