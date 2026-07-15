from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.rpg.session.genesis.canon_audit import CanonAuditReport
from app.rpg.session.genesis.compiler import compile_campaign_genesis
from app.rpg.session.genesis.contract import CampaignGenesisContract
from app.rpg.session.genesis.world_forge_commit import (
    certify_world_forge_commit,
)
from app.rpg.session.genesis.world_forge_default import (
    ReferenceSafeWorldForgeGenerator,
)
from app.rpg.session.genesis.world_forge_deterministic import (
    DeterministicWorldForgeGenerator,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_pipeline import run_campaign_world_forge
from app.rpg.session.genesis.world_forge_quality import (
    apply_world_forge_quality_audit,
)


ROOT = Path(__file__).resolve().parents[4]


def _contract(
    *,
    template: str = "classic_fantasy",
    depth: str = "quick",
) -> CampaignGenesisContract:
    return CampaignGenesisContract.model_validate(
        {
            "campaign_template": template,
            "genre": "fantasy",
            "tone": "grounded adventure",
            "world_options": {
                "starting_location": (
                    "vanta_gate"
                    if "summoned" in template
                    else "rusty_flagon_tavern"
                ),
                "difficulty": "normal",
                "world_activity": "living_world",
                "economy_pressure": "normal",
                "combat_lethality": "normal",
                "seed": 38,
            },
            "world_forge": {
                "depth": depth,
                "background_expansion": False,
                "require_consistency_audit": True,
                "require_opening_dossiers": True,
            },
        }
    )


def _run(contract: CampaignGenesisContract, generator=None):
    return run_campaign_world_forge(
        contract,
        campaign_id=f"campaign:phase38:{contract.campaign_template}",
        compiled_genesis=compile_campaign_genesis(contract),
        generator=generator or ReferenceSafeWorldForgeGenerator(),
    )


def test_all_supported_quick_templates_pass_rich_dossier_quality() -> None:
    for template in ("classic_fantasy", "summoned_hero_dark_fantasy"):
        result = _run(_contract(template=template))
        codes = {issue.code for issue in result.audit.issues}

        assert result.audit.passed is True, sorted(codes)
        assert result.audit.checks["quality_errors"] == 0
        assert result.audit.checks["npc_dossiers"] >= 4
        assert result.audit.checks["location_dossiers"] >= 5
        assert result.audit.checks["faction_dossiers"] >= 3
        assert result.audit.checks["quality_story_threads"] >= 2
        assert result.launch_ready is True
        assert certify_world_forge_commit(result).passed is True


class _BrokenNpcGenerator:
    def __init__(self) -> None:
        self.base = DeterministicWorldForgeGenerator()

    def generate(self, node, **kwargs):
        topic = self.base.generate(node, **kwargs)
        if node.category != "npcs" or not topic.entities:
            return topic
        rows = [dict(row) for row in topic.entities]
        rows[0]["backstory"] = ""
        rows[0]["dossier_status"] = "complete"
        return replace(topic, entities=tuple(rows))


def test_claiming_complete_cannot_hide_an_incomplete_npc_dossier() -> None:
    result = _run(
        _contract(),
        generator=ReferenceSafeWorldForgeGenerator(_BrokenNpcGenerator()),
    )
    codes = {issue.code for issue in result.audit.issues}

    assert "incomplete_npc_dossier" in codes
    assert result.audit.passed is False
    assert result.compilation.launch_ready is False
    assert certify_world_forge_commit(result).passed is False


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


def test_quality_audit_runs_before_compilation_and_commit_certification() -> None:
    pipeline = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "session"
        / "genesis"
        / "world_forge_pipeline.py"
    ).read_text(encoding="utf-8")
    commit_gate = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "session"
        / "genesis"
        / "world_forge_commit.py"
    ).read_text(encoding="utf-8")

    quality = pipeline.index("apply_world_forge_quality_audit(")
    assert quality < pipeline.index("compile_campaign_bible(")
    assert '"audit_passed"' in commit_gate
    assert '"aggregate_launch_ready"' in commit_gate
