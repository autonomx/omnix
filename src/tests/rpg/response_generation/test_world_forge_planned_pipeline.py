from app.rpg.session.genesis.contract import CampaignGenesisContract
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_deterministic import DeterministicWorldForgeGenerator
from app.rpg.session.genesis.world_forge_pipeline import run_campaign_world_forge


def test_planned_pipeline_is_launch_ready_with_compact_diagnostics() -> None:
    contract = CampaignGenesisContract.model_validate(
        {
            "campaign_template": "summoned_heroes",
            "genre": "portal_fantasy",
            "tone": "fractured mythic fantasy",
            "world_options": {"starting_location": "vanta_gate", "seed": 17},
            "world_forge": {"depth": "quick"},
        }
    )
    result = run_campaign_world_forge(
        contract,
        campaign_id="campaign:planned-pipeline",
        generator=ReferenceSafeWorldForgeGenerator(DeterministicWorldForgeGenerator()),
    )

    diagnostics = {
        "failed_topics": result.generation.failed_topic_ids,
        "audit": [
            (issue.code, issue.item_id, issue.message)
            for issue in result.audit.issues
            if issue.severity == "error"
        ],
        "missing": result.compilation.missing_requirements,
        "checks": dict(result.audit.checks),
    }
    assert result.generation.passed, diagnostics
    assert result.audit.passed, diagnostics
    assert result.compilation.launch_ready, diagnostics
    assert result.runtime_bootstrap, diagnostics
    assert result.compilation.completeness["opening_location_ids"] == [
        "place:vanta_gate"
    ]
