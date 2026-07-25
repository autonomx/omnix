from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.persistence.database import (
    DatabaseUnavailableError,
    PostgresConstraintError,
    PostgresLockTimeoutError,
    PostgresRetryableTransactionError,
    PostgresStatementTimeoutError,
    _classified_postgres_error,
)
from app.providers.base import BaseProvider, ChatMessage, ChatResponse, ModelInfo, ProviderConfig
from app.rpg.session.genesis.world_forge_contract import CampaignTopicGraph, CampaignTopicNode
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    StructuredFactIssue,
    StructuredFactValidationError,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_review import mark_needs_review, review_report
from app.rpg.worlds.generation_candidate_spool import (
    delete_candidate_spool,
    read_candidate_spool,
    write_candidate_spool,
)
from app.rpg.worlds.generation_jobs import generation_progress
from app.rpg_world_forge_provider import WorldForgeProviderConfig
from app.rpg_world_forge_single_pass_provider import (
    SinglePassProviderWorldForgeTopicGenerator,
    SinglePassWorldForgeProviderError,
)


class _Provider(BaseProvider):
    provider_name = "lmstudio"

    def __init__(self, responses: list[str]) -> None:
        self.config = ProviderConfig(provider_type="lmstudio", model="local-model")
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        stream: bool = False,
        **kwargs,
    ) -> ChatResponse:
        del stream
        self.calls.append({"messages": messages, "model": model, "kwargs": kwargs})
        return ChatResponse(content=self.responses.pop(0), model=model or "local-model")

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


def _setting_rules_node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="setting_rules",
        title="Setting Rules",
        category="lore",
        dependencies=(),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="game_master_canon",
        target_count=1,
        metadata={
            "entity_kind": "setting_rule",
            "field_definitions": [
                {
                    "field_id": "name",
                    "value_type": "string",
                    "required": True,
                    "description": "Rule name.",
                },
                {
                    "field_id": "rule",
                    "value_type": "string",
                    "required": True,
                    "description": "The binding setting rule.",
                },
                {
                    "field_id": "observable_consequences",
                    "value_type": "structured_object",
                    "required": True,
                    "description": "Observable consequences.",
                },
            ],
        },
    )


def _topic_payload(entity: dict) -> str:
    return json.dumps(
        {
            "topic_id": "setting_rules",
            "documents": [],
            "entities": [entity],
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {},
        }
    )


def _generator(provider: _Provider) -> SinglePassProviderWorldForgeTopicGenerator:
    return SinglePassProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="local-model",
            max_retries=5,
            lmstudio_schema_fallback=True,
        ),
    )


def test_setting_rules_schema_requires_profile_fields_and_calls_provider_once() -> None:
    provider = _Provider(
        [
            _topic_payload(
                {
                    "id": "ent:setting_rules:001",
                    "kind": "setting_rule",
                    "name": "Corporate sovereignty",
                    "rule": "Megacorporations exercise sovereign authority.",
                }
            ),
            _topic_payload(
                {
                    "id": "ent:setting_rules:001",
                    "kind": "setting_rule",
                    "name": "Unused retry",
                    "rule": "This response must never be requested.",
                    "observable_consequences": {"streets": ["checkpoints"]},
                }
            ),
        ]
    )

    with pytest.raises(SinglePassWorldForgeProviderError):
        _generator(provider).generate(
            _setting_rules_node(),
            seed=7,
            campaign_context={},
            dependency_topics={},
        )

    assert len(provider.calls) == 1
    response_format = provider.calls[0]["kwargs"]["response_format"]
    schema = response_format["json_schema"]["schema"]
    entity_schema = schema["properties"]["entities"]["items"]
    assert set(entity_schema["required"]) >= {
        "id",
        "kind",
        "name",
        "rule",
        "observable_consequences",
    }
    assert entity_schema["properties"]["kind"]["const"] == "setting_rule"
    assert entity_schema["additionalProperties"] is False


def test_valid_profile_candidate_is_returned_without_retry() -> None:
    provider = _Provider(
        [
            _topic_payload(
                {
                    "id": "ent:setting_rules:001",
                    "kind": "setting_rule",
                    "name": "Corporate sovereignty",
                    "rule": "Megacorporations exercise sovereign authority.",
                    "observable_consequences": {
                        "streets": ["private checkpoints"],
                        "courts": ["contract arbitration"],
                    },
                }
            )
        ]
    )

    topic = _generator(provider).generate(
        _setting_rules_node(),
        seed=7,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 1
    assert topic.entities[0]["kind"] == "setting_rule"
    assert topic.entities[0]["observable_consequences"]["streets"] == [
        "private checkpoints"
    ]


def test_validation_failure_retains_candidate_and_machine_readable_report() -> None:
    node = _setting_rules_node()
    candidate = GeneratedTopic(
        topic_id=node.topic_id,
        entities=(
            {
                "id": "ent:setting_rules:001",
                "kind": "setting_rule",
                "name": "Corporate sovereignty",
                "rule": "Megacorporations exercise sovereign authority.",
                "observable_consequences": "checkpoints",
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v3"},
    )
    error = StructuredFactValidationError(
        (
            StructuredFactIssue(
                code="invalid_structured_field_type",
                topic_id=node.topic_id,
                entity_id="ent:setting_rules:001",
                field_id="observable_consequences",
                message="Expected structured_object.",
                supplied_value="checkpoints",
            ),
        )
    )

    retained = mark_needs_review(node, candidate, error)
    report = review_report(retained)

    assert retained.entities == candidate.entities
    assert report["status"] == "needs_review"
    assert report["reason_codes"] == ["invalid_structured_field_type"]
    assert report["issues"][0]["entity_id"] == "ent:setting_rules:001"
    assert report["issues"][0]["field_id"] == "observable_consequences"
    assert report["issues"][0]["expected"] == "structured_object"


def test_progress_counts_flagged_failed_and_blocked_as_terminal() -> None:
    graph = CampaignTopicGraph(
        graph_version="test",
        campaign_template="test",
        depth="quick",
        nodes=(
            CampaignTopicNode("a", "A", "lore"),
            CampaignTopicNode("b", "B", "lore"),
            CampaignTopicNode("c", "C", "lore"),
            CampaignTopicNode("d", "D", "lore"),
        ),
    )

    progress = generation_progress(
        graph,
        accepted_topic_ids=("a",),
        flagged_topic_ids=("b",),
        failed_topic_ids=("c",),
        blocked_topic_ids=("d",),
        active_topic_ids=(),
    )

    assert progress["completed_topics"] == 4
    assert progress["percent"] == 100
    assert progress["generation_complete"] is True
    assert progress["publication_blocked"] is True
    assert progress["flagged_topic_ids"] == ["b"]


def test_candidate_spool_round_trip_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_RPG_WORLD_GENERATION_SPOOL_DIR", str(tmp_path))
    payload = {
        "run_id": "run:1",
        "topic_id": "setting_rules",
        "candidate": {"topic_id": "setting_rules"},
    }

    target = write_candidate_spool("job:1", payload)

    assert target.exists()
    assert read_candidate_spool("job:1") == payload
    assert list(tmp_path.glob("*.tmp")) == []
    delete_candidate_spool("job:1")
    assert read_candidate_spool("job:1") is None


class _PostgresError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate
        self.diag = None


def test_postgres_errors_are_classified_by_sqlstate() -> None:
    assert isinstance(_classified_postgres_error(_PostgresError("08006")), DatabaseUnavailableError)
    assert isinstance(
        _classified_postgres_error(_PostgresError("40001")),
        PostgresRetryableTransactionError,
    )
    assert isinstance(
        _classified_postgres_error(_PostgresError("55P03")),
        PostgresLockTimeoutError,
    )
    assert isinstance(
        _classified_postgres_error(_PostgresError("57014")),
        PostgresStatementTimeoutError,
    )
    assert isinstance(
        _classified_postgres_error(_PostgresError("23505")),
        PostgresConstraintError,
    )
