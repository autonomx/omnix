from app.rpg.session.genesis.canon_audit import CanonAuditReport
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_historical_planning import (
    build_geography_resource_plan,
    resolve_planning_family,
)
from app.rpg.session.genesis.world_forge_plan_audit import (
    attach_plan_reconciliation,
    audit_plan_to_canon,
)
from app.rpg.session.genesis.world_forge_plan_projection import (
    project_planning_into_topic,
)


def _registry():
    return {
        "registry_hash": "sha256:registry",
        "anchors": [
            {"id": "ent:region:001", "domain_id": "regions"},
            {"id": "ent:places:001", "domain_id": "places"},
            {"id": "ent:groups:001", "domain_id": "groups"},
            {"id": "ent:cultures:001", "domain_id": "cultures"},
            {"id": "ent:history_timeline:001", "domain_id": "history_timeline"},
        ],
    }


def test_planning_family_and_vocabulary_follow_world_brief() -> None:
    cyberpunk = {
        "genre": "cyberpunk",
        "world_brief": {"description": "A corporate neon megacity ruled by data monopolies."},
    }
    fantasy = {"genre": "high fantasy"}

    assert resolve_planning_family(cyberpunk) == "cyberpunk"
    assert resolve_planning_family(fantasy) == "fantasy"
    plan = build_geography_resource_plan(_registry(), seed=3, world_context=cyberpunk)
    assert plan["planning_family"] == "cyberpunk"
    assert plan["regions"][0]["terrain"] in {
        "megacity_core",
        "industrial_belt",
        "flooded_arcology",
        "network_zone",
        "peripheral_wastes",
    }
    assert plan["regions"][0]["primary_resource"] in {
        "compute",
        "energy",
        "data",
        "biotech",
        "clean_water",
    }


def test_plan_projection_makes_place_assignment_authoritative() -> None:
    node = CampaignTopicNode(
        topic_id="places",
        title="Places",
        category="places",
        target_count=1,
        metadata={
            "entity_kind": "place",
            "authoritative_entity_ids": ["ent:places:001"],
            "field_definitions": [
                {"field_id": "name", "value_type": "string", "required": True},
                {
                    "field_id": "region_id",
                    "value_type": "entity_ref",
                    "required": True,
                    "allowed_target_domains": ["regions"],
                },
                {
                    "field_id": "founding_event_ids",
                    "value_type": "entity_ref_list",
                    "required": False,
                    "allowed_target_domains": ["history_timeline"],
                },
                {"field_id": "founding_purpose", "value_type": "string", "required": True},
            ],
        },
    )
    topic = GeneratedTopic(
        "places",
        entities=(
            {
                "id": "ent:places:001",
                "kind": "place",
                "name": "Neon Junction",
                "region_id": "ent:region:999",
                "founding_purpose": "unplanned",
            },
        ),
    )
    dependencies = {
        "regions": GeneratedTopic("regions", entities=({"id": "ent:region:001"},)),
        "history_timeline": GeneratedTopic(
            "history_timeline", entities=({"id": "ent:history_timeline:001"},)
        ),
    }
    planning_slice = {
        "settlement_origin_plan": {
            "settlements": [
                {
                    "place_id": "ent:places:001",
                    "region_id": "ent:region:001",
                    "founding_event_id": "ent:history_timeline:001",
                    "founding_purpose": "data_exchange",
                }
            ]
        }
    }

    projected = project_planning_into_topic(
        node,
        topic,
        campaign_context={"planning_slice": planning_slice},
        dependency_topics=dependencies,
    )
    entity = projected.entities[0]
    assert entity["region_id"] == "ent:region:001"
    assert entity["founding_event_ids"] == ["ent:history_timeline:001"]
    assert entity["founding_purpose"] == "data_exchange"
    facts = {row["field_id"]: row for row in projected.facts}
    assert facts["region_id"]["object"] == "ent:region:001"
    assert facts["founding_event_ids"]["object"] == ["ent:history_timeline:001"]


def test_plan_audit_blocks_identity_and_assignment_drift() -> None:
    planning = {
        "anchor_registry": _registry(),
        "settlement_origin_plan": {
            "settlements": [
                {
                    "place_id": "ent:places:001",
                    "region_id": "ent:region:001",
                    "founding_event_id": "ent:history_timeline:001",
                    "founding_purpose": "data_exchange",
                }
            ]
        },
        "culture_lineage_plan": {"lineages": []},
        "political_claim_graph": {"claims": []},
    }
    topics = (
        GeneratedTopic("regions", entities=({"id": "ent:region:001"},)),
        GeneratedTopic("groups", entities=({"id": "ent:groups:001"},)),
        GeneratedTopic("cultures", entities=({"id": "ent:cultures:001"},)),
        GeneratedTopic("history_timeline", entities=({"id": "ent:history_timeline:001"},)),
        GeneratedTopic(
            "places",
            entities=(
                {
                    "id": "ent:places:001",
                    "region_id": "ent:region:999",
                    "founding_event_ids": [],
                    "founding_purpose": "wrong",
                },
            ),
        ),
    )

    findings = audit_plan_to_canon(topics, planning)
    codes = {finding.code for finding in findings}
    assert "planned_settlement_region_mismatch" in codes
    assert "planned_settlement_founding_event_mismatch" in codes
    assert "planned_settlement_purpose_mismatch" in codes
    attached = attach_plan_reconciliation(
        topics,
        planning,
        CanonAuditReport(passed=True),
    )
    assert attached.passed is False
    assert attached.checks["plan_reconciliation_errors"] == 3
