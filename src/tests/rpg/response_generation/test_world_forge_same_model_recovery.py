from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.providers.base import (
    BaseProvider,
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderConfig,
)
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_review import result_status
from app.rpg.worlds.generation_recovering_provider import (
    RecoveringFirstPassWorldForgeTopicGenerator,
)
from app.rpg.worlds.generation_contract_bundle import build_topic_contract_bundle
from app.rpg.worlds.generation_first_pass_provider import _authored_contract
from app.rpg.worlds.generation_recovery_evidence import (
    EvidenceBackedRecoveringWorldForgeTopicGenerator,
)
from app.rpg.worlds.generation_structured_recovery import (
    apply_missing_field_patches,
    deterministic_repair,
    minimum_viability_candidate,
    missing_field_paths,
    missing_field_patch_contract,
)
from app.rpg_world_forge_provider import WorldForgeProviderConfig
from app.rpg_world_forge_single_pass_provider import SinglePassWorldForgeProviderError


class _Provider(BaseProvider):
    provider_name = "lmstudio"

    def __init__(self, responses: list[str]) -> None:
        super().__init__(ProviderConfig(provider_type="lmstudio", model="local-model"))
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ChatResponse:
        del stream
        self.calls.append({"messages": messages, "model": model, "kwargs": kwargs})
        return ChatResponse(
            content=self.responses.pop(0),
            model=model or "local-model",
        )

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


def _generator(provider: _Provider) -> RecoveringFirstPassWorldForgeTopicGenerator:
    return RecoveringFirstPassWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="local-model",
            max_retries=0,
            lmstudio_schema_fallback=False,
        ),
    )


def _history_node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="history_timeline",
        title="History Timeline",
        category="lore",
        dependencies=("setting_rules",),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="game_master_canon",
        target_count=1,
        metadata={
            "entity_kind": "historical_event",
            "field_definitions": [
                {
                    "field_id": "name",
                    "value_type": "string",
                    "required": True,
                    "description": "Event name.",
                },
                {
                    "field_id": "year",
                    "value_type": "integer",
                    "required": True,
                    "description": "Event year.",
                },
                {
                    "field_id": "event",
                    "value_type": "string",
                    "required": True,
                    "description": "What happened.",
                },
            ],
        },
    )


def _entity() -> dict[str, Any]:
    return {
        "id": "ent:history_timeline:001",
        "kind": "historical_event",
        "name": "The Blackout Accords",
        "year": 2088,
        "event": "City grids were divided among corporate utilities.",
        "short_summary": "The accords divided the city grid.",
        "dossier": {
            "sections": {
                "overview": {"paragraphs": ["The accords remade the city."]},
                "history": {"paragraphs": ["They followed the great blackout."]},
                "details": {"paragraphs": ["Utilities received bounded districts."]},
                "connections": {"paragraphs": ["Every district still bears the cost."]},
            }
        },
    }


def _topic_payload(topic_id: str = "history_timeline") -> str:
    return json.dumps(
        {
            "topic_id": topic_id,
            "documents": [],
            "entities": [_entity()],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
        }
    )


def _malformed_alias_payload() -> str:
    return json.dumps(
        {
            "topic_id": "history_timeline",
            "documents": [],
            "items": [
                {
                    "entity_id": "ent:history_timeline:001",
                    "type": "historical_event",
                    "title": "The Blackout Accords",
                    "year": 2088,
                    "description": "City grids were divided among corporate utilities.",
                }
            ],
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {},
        }
    )


def test_entity_id_in_root_is_fixed_without_another_model_call() -> None:
    provider = _Provider([_topic_payload("ent:history_timeline:001")])

    topic = _generator(provider).generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 1
    assert topic.topic_id == "history_timeline"
    assert topic.entities[0]["id"] == "ent:history_timeline:001"
    assert result_status(topic) == "needs_review"
    record = topic.provenance["structured_recovery"]["records"][0]
    assert record["method"] == "deterministic_normalisation"
    assert "root_topic_id_from_entity_id" in record["repair_codes"]


def test_deterministic_repair_adds_only_known_missing_dossier_titles() -> None:
    payload = json.loads(_topic_payload())
    payload["entities"][0].update(
        {
            "short_summary": "A decisive break in the corporate utility order.",
            "dossier": {
                "schema_version": "rpg_world_entity_dossier_v1",
                "sections": [
                    {"id": "overview", "paragraphs": ["The first blackout changed everything."]},
                    {"id": "custom", "paragraphs": ["This title is not authoritative."]},
                ],
            },
        }
    )

    repaired = deterministic_repair(
        payload,
        expected_topic_id="history_timeline",
        allocated_entity_ids=("ent:history_timeline:001",),
        expected_entity_kind="historical_event",
    )

    assert repaired.payload is not None
    sections = repaired.payload["entities"][0]["dossier"]["sections"]
    assert sections[0]["title"] == "Overview"
    assert "title" not in sections[1]
    assert "dossier_section_title_from_template" in repaired.codes


def test_deterministic_repair_nests_authored_sections_at_contract_path() -> None:
    payload = {
        "topic_id": "setting_rules",
        "entities": [
            {
                "id": "ent:setting_rules:001",
                "kind": "setting_rule",
                "dossier": {
                    "related_entity_ids": [
                        "ent:setting_rules:001",
                        "ent:regions:001",
                    ],
                    "overview": {"paragraphs": ["Overview prose."]},
                    "foundations": {"paragraphs": ["Foundation prose."]},
                    "lived_experience": {"paragraphs": ["Daily-life prose."]},
                    "boundaries": {"paragraphs": ["Boundary prose."]},
                    "consequences": {"paragraphs": ["Consequence prose."]},
                },
            }
        ],
        "provenance": {},
    }

    repaired = deterministic_repair(
        payload,
        expected_topic_id="setting_rules",
        allocated_entity_ids=("ent:setting_rules:001",),
        expected_entity_kind="setting_rule",
        include_provenance=False,
        allowed_reference_ids=frozenset({"ent:setting_rules:001"}),
        allowed_root_fields=frozenset(
            {
                "topic_id",
                "documents",
                "entities",
                "relationships",
                "knowledge_rules",
                "story_threads",
            }
        ),
    )

    assert repaired.payload is not None
    dossier = repaired.payload["entities"][0]["dossier"]
    assert set(dossier["sections"]) == {
        "overview",
        "foundations",
        "lived_experience",
        "boundaries",
        "consequences",
    }
    assert "overview" not in dossier
    assert dossier["related_entity_ids"] == ["ent:setting_rules:001"]
    assert "provenance" not in repaired.payload
    assert "nest_dossier_sections_under_sections" in repaired.codes
    assert "remove_unknown_related_entity_ids" in repaired.codes


def test_missing_field_patch_contract_repairs_only_requested_leaf() -> None:
    payload = {
        "relationships": [
            {
                "source_id": "ent:groups:001",
                "target_id": "ent:places:001",
                "relationship_type": "protects",
            }
        ],
    }
    error = ValidationError.from_exception_data(
        "Draft",
        [
            {
                "type": "missing",
                "loc": ("relationships", 0, "description"),
                "input": payload["relationships"][0],
            }
        ],
    )
    paths = missing_field_paths(error)
    assert paths == ("relationships.0.description",)
    contract = missing_field_patch_contract(paths)
    patch_response = contract.output_model.model_validate(
        {
            "patches": [
                {
                    "path": "relationships.0.description",
                    "value": "The wardens protect the district in return for access.",
                }
            ]
        }
    )
    contract.semantic_validator(patch_response)
    repaired = apply_missing_field_patches(payload, patch_response.patches)
    assert repaired == {
        "relationships": [
            {
                "source_id": "ent:groups:001",
                "target_id": "ent:places:001",
                "relationship_type": "protects",
                "description": "The wardens protect the district in return for access.",
            }
        ],
    }


def test_missing_field_patch_supports_non_string_authored_values() -> None:
    error = ValidationError.from_exception_data(
        "Draft",
        [{"type": "missing", "loc": ("entities", 0, "year"), "input": {}}],
    )
    paths = missing_field_paths(error)
    assert paths == ("entities.0.year",)
    contract = missing_field_patch_contract(paths)
    response = contract.output_model.model_validate(
        {"patches": [{"path": "entities.0.year", "value": 2088}]}
    )
    repaired = apply_missing_field_patches({"entities": [{}]}, response.patches)
    assert repaired == {"entities": [{"year": 2088}]}


def test_missing_field_patch_recovery_uses_one_narrow_followup() -> None:
    invalid = json.loads(_topic_payload())
    invalid["story_threads"] = [
        {
            "summary": "A grid takeover is imminent.",
            "status": "active",
            "actor_ids": ["ent:history_timeline:001"],
            "location_ids": [],
            "faction_ids": [],
        }
    ]
    patch = {
        "patches": [
            {
                "path": "story_threads.0.title",
                "value": "The Coming Grid Takeover",
            }
        ]
    }
    provider = _Provider([json.dumps(invalid), json.dumps(patch)])

    topic = _generator(provider).generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 2
    assert "narrow omission" in provider.calls[1]["messages"][0].content
    assert topic.story_threads[0]["title"] == "The Coming Grid Takeover"
    assert topic.provenance["structured_recovery"]["records"][0]["method"] == (
        "targeted_missing_field_patch"
    )


def test_same_configured_model_extracts_malformed_fields_into_schema() -> None:
    provider = _Provider([_malformed_alias_payload(), _topic_payload()])

    topic = _generator(provider).generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 2
    assert {call["model"] for call in provider.calls} == {"local-model"}
    assert "loss-minimising JSON recovery transformer" in (
        provider.calls[1]["messages"][0].content
    )
    recovery_request = provider.calls[1]["messages"][1].content
    assert "The Blackout Accords" in recovery_request
    assert "Do not invent, enrich, summarise, or regenerate lore" in recovery_request
    assert topic.entities[0]["name"] == "The Blackout Accords"
    assert result_status(topic) == "needs_review"
    record = topic.provenance["structured_recovery"]["records"][0]
    assert record["method"] == "same_model_extraction"
    assert topic.provenance["attempt_count"] == 2


def test_semantic_correction_repairs_repeated_long_prose_after_recovery() -> None:
    duplicate = json.loads(_topic_payload())
    repeated = (
        "Corporate utilities rationed power across the city after the blackout, "
        "turning every district connection into a paid and closely monitored service "
        "and binding residents to contracts enforced through the central grid."
    )
    duplicate["entities"][0]["event"] = repeated
    duplicate["entities"][0]["dossier"]["sections"]["details"]["paragraphs"] = [
        repeated
    ]
    corrected = json.loads(_topic_payload())
    corrected["entities"][0]["event"] = repeated
    corrected["entities"][0]["dossier"]["sections"]["details"]["paragraphs"] = [
        "Utilities received bounded districts, each with its own contracted maintenance crews."
    ]
    provider = _Provider(
        [_malformed_alias_payload(), json.dumps(duplicate), json.dumps(corrected)]
    )

    topic = _generator(provider).generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 3
    assert "minimal semantic correction" in provider.calls[2]["messages"][0].content
    assert "authored_draft_repeated_long_prose" in provider.calls[2]["messages"][1].content
    assert topic.entities[0]["event"] == repeated
    assert topic.provenance["structured_recovery"]["records"][0]["method"] == (
        "same_model_semantic_correction"
    )


def test_repeated_long_prose_is_retained_as_minimum_viability_candidate() -> None:
    duplicate = json.loads(_topic_payload())
    repeated = (
        "Corporate utilities rationed power across the city after the blackout, "
        "turning every district connection into a paid and closely monitored service "
        "and binding residents to contracts enforced through the central grid."
    )
    duplicate["entities"][0]["event"] = repeated
    duplicate["entities"][0]["dossier"]["sections"]["details"]["paragraphs"] = [
        repeated
    ]
    provider = _Provider(
        [_malformed_alias_payload(), json.dumps(duplicate), json.dumps(duplicate)]
    )

    topic = _generator(provider).generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 3
    assert result_status(topic) == "needs_review"
    record = topic.provenance["structured_recovery"]["records"][0]
    assert record["method"] == "minimum_viability_quarantine"
    assert record["minimum_viability"]["allows_dependency_generation"] is True
    assert record["minimum_viability"]["blocking_publication"] is True
    assert "authored_draft_repeated_long_prose" in topic.provenance[
        "generation_review"
    ]["reason_codes"]


def test_minimum_viability_rejects_non_allowlisted_semantic_error() -> None:
    node = _history_node()
    ids = ("ent:history_timeline:001",)
    contract = _authored_contract(
        build_topic_contract_bundle(
            node,
            allocated_entity_ids=ids,
            dependencies={},
        )
    )
    value, report = minimum_viability_candidate(
        contract,
        json.loads(_topic_payload()),
        ValueError("authored_draft_unknown_reference:/entities/0/group_id"),
    )

    assert value is None
    assert report is None


def test_evidence_backed_recovery_accepts_profile_field_definitions() -> None:
    provider = _Provider([_malformed_alias_payload(), _topic_payload()])
    generator = EvidenceBackedRecoveringWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="local-model",
            max_retries=0,
            lmstudio_schema_fallback=False,
        ),
    )

    topic = generator.generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 2
    assert topic.entities[0]["name"] == "The Blackout Accords"
    assert topic.provenance["structured_recovery"]["records"][0]["method"] == (
        "same_model_extraction"
    )


def test_failed_extraction_yields_failure_artifact_and_no_candidate() -> None:
    provider = _Provider([_malformed_alias_payload(), "not valid json"])

    with pytest.raises(SinglePassWorldForgeProviderError) as captured:
        _generator(provider).generate(
            _history_node(),
            seed=8,
            campaign_context={},
            dependency_topics={},
        )

    assert len(provider.calls) == 2
    artifact = captured.value.diagnostics["failure_artifact"]
    assert artifact["stage"] == "recovery_exhausted"
    assert artifact["correction_attempted"] is True
    assert artifact["canonical_contract_hash"]


def test_registry_uses_same_model_extraction_without_alternate_setup() -> None:
    node = CampaignTopicNode(
        topic_id="groups",
        title="Groups",
        category="lore",
        target_count=2,
        metadata={},
    )
    valid_registry = {
        "topic_id": "groups",
        "entities": [
            {
                "id": "ent:groups:001",
                "name": "Neon Wardens",
                "role": "security cooperative",
                "distinction": "citizen-owned surveillance",
            },
            {
                "id": "ent:groups:002",
                "name": "Ash Cartel",
                "role": "salvage syndicate",
                "distinction": "controls dead-grid hardware",
            },
        ],
    }
    malformed_registry = {
        "topic_id": "groups",
        "items": valid_registry["entities"],
    }
    provider = _Provider(
        [json.dumps(malformed_registry), json.dumps(valid_registry)]
    )

    registry, diagnostics, _, _ = _generator(provider)._generate_entity_registry(
        node,
        seed=10,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 2
    assert {call["model"] for call in provider.calls} == {"local-model"}
    assert registry.topic_id == "groups"
    assert diagnostics["structured_recovery"]["method"] == "same_model_extraction"
