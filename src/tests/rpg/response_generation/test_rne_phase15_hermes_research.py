from __future__ import annotations

from app.assist_core.hermes_rpg_narrative_research import (
    hermes_rpg_narrative_research_payload,
)
from app.rpg.narrative_engine import (
    AuthorityClass,
    HermesResearchPolicy,
    HermesResearchRequest,
    normalize_hermes_research,
)


def _request() -> HermesResearchRequest:
    return HermesResearchRequest(
        research_id="research:east-road",
        campaign_id="campaign:hermes",
        query="historical road conditions east of the tavern",
        entity_ids=("location:east_road",),
    )


def test_hermes_research_is_bounded_cited_and_never_mutates_canon() -> None:
    raw = {
        "provider": "hermes-test",
        "model": "provider-free-fixture",
        "sources": [
            {
                "source_id": "source:ledger",
                "title": "East Road Caravan Ledger",
                "citation": "archive:ledger:12",
                "excerpt": "Caravans report deep mud after summer rain.",
            },
            {
                "source_id": "source:chronicle",
                "title": "Local Chronicle",
                "citation": "archive:chronicle:7",
                "excerpt": "The old east bridge was rebuilt in 913.",
            },
        ],
        "findings": [
            {
                "finding_id": "finding:mud",
                "content": (
                    "Caravan records describe the East Road as muddy "
                    "after heavy rain."
                ),
                "source_refs": ["source:ledger"],
                "authority": "historical_record",
                "entity_refs": ["location:east_road"],
                "confidence": 0.9,
            },
            {
                "finding_id": "finding:canon",
                "content": "The old east bridge is established campaign canon.",
                "source_refs": ["source:chronicle"],
                "authority": "objective_canon",
            },
            {
                "finding_id": "finding:unsupported",
                "content": "No citation backs this item.",
                "source_refs": ["source:missing"],
                "authority": "public_knowledge",
            },
        ],
    }
    result = normalize_hermes_research(
        _request(),
        raw,
        policy=HermesResearchPolicy(
            max_sources=2,
            max_findings=3,
            max_total_chars=2_000,
        ),
    )
    assert [finding.finding_id for finding in result.findings] == [
        "finding:mud",
        "finding:canon",
    ]
    assert result.findings[0].authority is AuthorityClass.HISTORICAL_RECORD
    assert result.findings[1].authority is AuthorityClass.OBJECTIVE_CANON
    reasons = {item["reason"] for item in result.rejected_items}
    assert reasons == {"missing_or_unknown_source"}
    evidence = result.evidence()[0]
    assert evidence.authority is AuthorityClass.HISTORICAL_RECORD
    assert evidence.metadata["source_refs"] == ["source:ledger"]
    assert result.metadata["may_mutate_campaign_bible"] is False


def test_hermes_route_is_read_only_and_reports_missing_campaign_bible() -> None:
    unavailable = hermes_rpg_narrative_research_payload(
        {
            "research_id": "research:none",
            "campaign_id": "campaign:hermes",
            "query": "road history",
        }
    )
    assert unavailable["ok"] is False
    assert unavailable["error"] == "campaign_bible_not_available"
    assert unavailable["state_changed"] is False

    payload = hermes_rpg_narrative_research_payload(
        {
            "research_id": "research:bounded",
            "campaign_id": "campaign:hermes",
            "query": "road history",
            "policy": {
                "max_sources": 1,
                "max_findings": 1,
                "max_total_chars": 1_000,
            },
            "research_result": {
                "sources": [
                    {
                        "source_id": "source:1",
                        "title": "Road Ledger",
                        "citation": "ledger:1",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding:1",
                        "content": "The ledger records rain damage.",
                        "source_refs": ["source:1"],
                        "authority": "historical_record",
                    }
                ],
            },
        }
    )
    assert payload["ok"] is True
    assert payload["read_only"] is True
    assert payload["state_changed"] is False
    assert payload["campaign_bible_changed"] is False
    assert len(payload["evidence"]) == 1
