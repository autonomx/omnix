from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_semantic_quality import (
    audit_topic_semantic_quality,
)


def _node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="contracts",
        title="Contracts",
        category="domain",
        metadata={
            "field_definitions": [
                {"field_id": "name", "value_type": "string", "required": True},
                {
                    "field_id": "giver_id",
                    "value_type": "entity_ref",
                    "allowed_target_domains": ["actors"],
                },
                {
                    "field_id": "location_id",
                    "value_type": "entity_ref",
                    "allowed_target_domains": ["places"],
                },
                {"field_id": "objective", "value_type": "string", "required": True},
                {"field_id": "dependency", "value_type": "string", "required": True},
                {"field_id": "next_action", "value_type": "string", "required": True},
                {
                    "field_id": "observable_evidence",
                    "value_type": "structured_object",
                    "required": True,
                },
            ]
        },
    )


def _entity(index: int, *, giver_id: str | None = None) -> dict:
    details = (
        (
            "Restore the salt-clogged intake valve beneath the western pier.",
            "Requires a ceramic seal held by the harbor machinists.",
            "At dawn the dock crew lowers a diver cage beside the intake tower.",
            {"sign": "Chalk depth marks and wet pressure suits line Pier Seven."},
        ),
        (
            "Recover the tribunal ledger from the flooded customs archive.",
            "Requires the retired clerk's brass cipher wheel.",
            "Before noon the archivist drains one basement corridor with hand pumps.",
            {"sign": "Blue archive tags float against the locked customs gate."},
        ),
        (
            "Escort the seed barge through the turbine-shadow channel.",
            "Depends on a current chart updated by the lighthouse cooperative.",
            "At the evening tide two pilots mark safe water with amber lamps.",
            {"sign": "Fresh amber buoys form a narrow route beyond the breakwater."},
        ),
        (
            "Expose the counterfeit ration stamps circulating in North Market.",
            "Requires ink samples from the municipal printworks furnace room.",
            "Tonight the inspector quietly records serial numbers at three food stalls.",
            {"sign": "Vendors hide violet-stained stamp pads beneath their scales."},
        ),
    )[index]
    objective, dependency, next_action, evidence = details
    return {
        "id": f"contract:{index}",
        "kind": "contract",
        "name": f"Harbor Contract {index}",
        "giver_id": giver_id or f"actor:{index}",
        "location_id": f"place:{index}",
        "objective": objective,
        "dependency": dependency,
        "next_action": next_action,
        "observable_evidence": evidence,
    }


def _topic(entities: list[dict]) -> GeneratedTopic:
    return GeneratedTopic(topic_id="contracts", entities=tuple(entities))


def test_distinct_operational_entities_pass() -> None:
    report = audit_topic_semantic_quality(
        _node(),
        _topic([_entity(index) for index in range(4)]),
    )
    assert report.passed, [issue.as_dict() for issue in report.issues]
    assert report.checks["operational_fields"] == 1
    assert report.checks["causal_fields"] == 1
    assert report.checks["observable_fields"] == 1


def test_generic_fallback_language_fails() -> None:
    entity = _entity(0)
    entity["objective"] = "A consequential contract tied to active world pressures."
    report = audit_topic_semantic_quality(_node(), _topic([entity]))
    assert any(issue.code == "generic_fallback_language" for issue in report.issues)
    assert report.passed is False


def test_duplicate_substantive_fields_fail_differentiation() -> None:
    first = _entity(0)
    second = _entity(1)
    second["objective"] = first["objective"]
    report = audit_topic_semantic_quality(_node(), _topic([first, second]))
    issue = next(
        issue
        for issue in report.issues
        if issue.code == "insufficient_entity_differentiation"
    )
    assert issue.fields == ("objective",)
    assert set(issue.entity_ids) == {"contract:0", "contract:1"}


def test_reference_concentration_requires_explicit_declaration() -> None:
    entities = [_entity(index, giver_id="actor:central_broker") for index in range(4)]
    report = audit_topic_semantic_quality(_node(), _topic(entities))
    assert any(
        issue.code == "suspicious_reference_concentration"
        and issue.fields == ("giver_id",)
        for issue in report.issues
    )


def test_declared_central_broker_is_allowed() -> None:
    entities = [_entity(index, giver_id="actor:central_broker") for index in range(4)]
    report = audit_topic_semantic_quality(
        _node(),
        _topic(entities),
        {
            "intentional_reference_clusters": [
                {
                    "topic_id": "contracts",
                    "field": "giver_id",
                    "entity_id": "actor:central_broker",
                    "reason": "All contracts are routed through the harbor broker.",
                }
            ]
        },
    )
    assert report.passed, [issue.as_dict() for issue in report.issues]


def test_declared_broker_and_hub_tuple_is_allowed() -> None:
    entities = [_entity(index, giver_id="actor:central_broker") for index in range(4)]
    for entity in entities:
        entity["location_id"] = "place:contract_hall"
    report = audit_topic_semantic_quality(
        _node(),
        _topic(entities),
        {
            "intentional_reference_clusters": [
                {
                    "topic_id": "contracts",
                    "field": "giver_id",
                    "entity_id": "actor:central_broker",
                    "reason": "All contracts are routed through one broker.",
                },
                {
                    "topic_id": "contracts",
                    "field": "location_id",
                    "entity_id": "place:contract_hall",
                    "reason": "All contracts are posted in the same hall.",
                },
            ]
        },
    )
    assert report.passed, [issue.as_dict() for issue in report.issues]


def test_weak_next_action_and_evidence_fail_operational_usefulness() -> None:
    entity = _entity(0)
    entity["next_action"] = "Wait."
    entity["observable_evidence"] = {"sign": "Nothing."}
    report = audit_topic_semantic_quality(_node(), _topic([entity]))
    codes = {issue.code for issue in report.issues}
    assert "weak_operational_state" in codes
    assert "weak_observable_evidence" in codes
