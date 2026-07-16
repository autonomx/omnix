from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.providers.base import (
    BaseProvider,
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderConfig,
)
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_default import (
    ReferenceSafeWorldForgeGenerator,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_provider import (
    FallbackWorldForgeTopicGenerator,
    ProviderWorldForgeTopicGenerator,
    UnavailableWorldForgeTopicGenerator,
    WorldForgeProviderConfig,
    build_production_world_forge_generator,
)


ROOT = Path(__file__).resolve().parents[4]


class _Provider(BaseProvider):
    provider_name = "phase36"

    def __init__(self, responses: list[str | Exception]) -> None:
        self.config = ProviderConfig(
            provider_type="phase36",
            model="phase36-model",
        )
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        stream: bool = False,
        **kwargs,
    ):
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "stream": stream,
                "kwargs": kwargs,
            }
        )
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return ChatResponse(
            content=value,
            model=model or "phase36-model",
            usage={"prompt_tokens": 20, "completion_tokens": 40},
            finish_reason="stop",
        )

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


def _node(
    topic_id: str = "realm",
    *,
    category: str = "lore",
) -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id=topic_id,
        title=topic_id.replace("_", " ").title(),
        category=category,
        dependencies=(),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="game_master_canon",
        target_count=1,
    )


def _payload(topic_id: str = "realm") -> str:
    return json.dumps(
        {
            "topic_id": topic_id,
            "documents": [
                {
                    "document_id": f"lore:{topic_id}",
                    "topic_id": topic_id,
                    "title": "The Realm",
                    "full_text": "A connected realm shaped by old alliances.",
                    "summary_500": "A connected realm shaped by old alliances.",
                    "summary_120": "A connected realm shaped by old alliances.",
                    "facts": [],
                    "entities": ["realm:test"],
                    "relationships": [],
                    "keywords": ["realm", "alliances"],
                    "visibility": "public",
                    "canon_revision": 0,
                }
            ],
            "entities": [
                {
                    "id": "realm:test",
                    "name": "Test Realm",
                    "kind": "realm",
                    "visibility": "public",
                }
            ],
            "facts": [
                {
                    "id": "fact:realm:test",
                    "content": "Test Realm is shaped by old alliances.",
                    "authority": "generated_proposal",
                    "approved_authority": "objective_canon",
                    "visibility": "public",
                    "entity_refs": ["realm:test"],
                }
            ],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {"research_style": "connected_history"},
        }
    )


def test_provider_config_uses_dedicated_override_and_bounds_settings() -> None:
    config = WorldForgeProviderConfig.from_environment(
        {
            "OMNIX_RPG_WORLD_FORGE_MODE": "live",
            "OMNIX_RPG_WORLD_FORGE_PROVIDER": "lmstudio",
            "OMNIX_RPG_WORLD_FORGE_MODEL": "qwen-world",
            "OMNIX_RPG_WORLD_FORGE_TIMEOUT_SECONDS": "9999",
            "OMNIX_RPG_WORLD_FORGE_MAX_RETRIES": "99",
            "OMNIX_RPG_WORLD_FORGE_TEMPERATURE": "4",
        }
    )
    assert config.live_enabled is True
    assert config.provider == "lmstudio"
    assert config.model == "qwen-world"
    assert config.timeout_seconds == 900
    assert config.max_retries == 5
    assert config.temperature == 2.0


def test_narrative_environment_does_not_override_world_forge_settings_route() -> None:
    config = WorldForgeProviderConfig.from_environment(
        {
            "OMNIX_RPG_NARRATIVE_PROVIDER": "cerebras",
            "OMNIX_RPG_NARRATIVE_MODEL": "stale-model",
            "OMNIX_LLM_PROVIDER": "cerebras",
        }
    )

    assert config.provider == ""
    assert config.model == ""


def test_auto_mode_uses_settings_even_with_stale_dedicated_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.platform import effective_defaults

    monkeypatch.setattr(
        effective_defaults,
        "load_effective_profile",
        lambda: object(),
    )
    monkeypatch.setattr(
        effective_defaults,
        "effective_llm_route",
        lambda _profile, _module, _task: ("lmstudio", "local-world"),
    )
    captured: dict[str, object] = {}

    def factory(provider: str, provider_config: dict) -> _Provider:
        captured["provider"] = provider
        captured["config"] = provider_config
        return _Provider([_payload()])

    generator = build_production_world_forge_generator(
        WorldForgeProviderConfig(
            mode="auto",
            provider="cerebras",
            model="stale-model",
        ),
        provider_factory=factory,
    )

    assert isinstance(generator.generator, ProviderWorldForgeTopicGenerator)
    assert captured["provider"] == "lmstudio"
    assert captured["config"]["model"] == "local-world"


def test_structured_provider_retries_and_returns_one_native_topic() -> None:
    provider = _Provider([RuntimeError("temporary"), _payload()])
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="phase36",
            model="phase36-model",
            max_retries=1,
        ),
    )
    topic = generator.generate(
        _node(),
        seed=36,
        campaign_context={"campaign_id": "campaign:phase36"},
        dependency_topics={},
    )

    assert topic.topic_id == "realm"
    assert topic.entities[0]["id"] == "realm:test"
    assert topic.provenance["generator"] == "structured_world_forge_provider_v1"
    assert topic.provenance["attempt_count"] == 2
    assert topic.provenance["usage"]["completion_tokens"] == 40
    assert provider.calls[-1]["kwargs"]["response_format"] == {
        "type": "json_object"
    }
    system = provider.calls[-1]["messages"][0].content
    assert "strict JSON only" in system
    assert "NPC dossiers" in system


def test_lmstudio_uses_supported_json_schema_response_format() -> None:
    provider = _Provider([_payload()])
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            max_retries=0,
        ),
    )

    generator.generate(
        _node(),
        seed=36,
        campaign_context={},
        dependency_topics={},
    )

    response_format = provider.calls[-1]["kwargs"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "rpg_world_forge_topic"
    schema = response_format["json_schema"]["schema"]
    assert schema["properties"]["topic_id"] == {"type": "string"}
    assert set(schema["required"]) == {
        "topic_id",
        "documents",
        "entities",
        "facts",
        "relationships",
        "knowledge_rules",
        "story_threads",
        "provenance",
    }


def test_provider_topic_identity_mismatch_fails_closed() -> None:
    provider = _Provider([_payload("wrong")])
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="phase36",
            max_retries=0,
        ),
    )
    with pytest.raises(
        RuntimeError,
        match="failed for realm.*returned wrong for realm",
    ):
        generator.generate(
            _node(),
            seed=36,
            campaign_context={},
            dependency_topics={},
        )


def test_provider_fallback_sticks_to_first_healthy_generator() -> None:
    failed = _Provider([RuntimeError("quota exhausted")])
    healthy = _Provider([_payload(), _payload("history")])
    generator = FallbackWorldForgeTopicGenerator(
        (
            ProviderWorldForgeTopicGenerator(
                failed,
                WorldForgeProviderConfig(
                    mode="live",
                    provider="cerebras",
                    max_retries=0,
                ),
            ),
            ProviderWorldForgeTopicGenerator(
                healthy,
                WorldForgeProviderConfig(
                    mode="live",
                    provider="lmstudio",
                    max_retries=0,
                ),
            ),
        )
    )

    first = generator.generate(
        _node(),
        seed=36,
        campaign_context={},
        dependency_topics={},
    )
    second = generator.generate(
        _node("history"),
        seed=36,
        campaign_context={},
        dependency_topics={},
    )

    assert first.topic_id == "realm"
    assert second.topic_id == "history"
    assert len(failed.calls) == 1
    assert len(healthy.calls) == 2


def test_reference_safety_wraps_live_provider_output() -> None:
    class _LiveGenerator:
        def generate(self, node, **kwargs):
            return GeneratedTopic(
                topic_id=node.topic_id,
                entities=(
                    {
                        "id": "location:gate",
                        "kind": "location",
                        "region_id": "region:missing",
                    },
                ),
                facts=(
                    {
                        "id": "fact:gate",
                        "entity_refs": ["location:gate", "region:missing"],
                    },
                ),
            )

    dependencies = {
        "regions": GeneratedTopic(
            topic_id="regions",
            entities=(
                {"id": "region:known", "kind": "region"},
            ),
        )
    }
    topic = ReferenceSafeWorldForgeGenerator(_LiveGenerator()).generate(
        _node("locations", category="locations"),
        seed=36,
        campaign_context={},
        dependency_topics=dependencies,
    )
    assert topic.entities[0]["region_id"] == "region:known"
    assert topic.facts[0]["entity_refs"] == [
        "location:gate",
        "region:known",
    ]


def test_offline_mode_deliberately_uses_reference_safe_deterministic_generator() -> None:
    called = False

    def factory(name, config):
        nonlocal called
        called = True
        return _Provider([_payload()])

    generator = build_production_world_forge_generator(
        WorldForgeProviderConfig(mode="offline", provider="phase36"),
        provider_factory=factory,
    )
    assert isinstance(generator, ReferenceSafeWorldForgeGenerator)
    assert called is False


def test_auto_mode_reuses_settings_control_center_llm_route(monkeypatch) -> None:
    from app import shared
    from app.platform import effective_defaults

    provider = _Provider([_payload()])
    monkeypatch.setattr(effective_defaults, "load_effective_profile", lambda: object())
    monkeypatch.setattr(
        effective_defaults,
        "effective_llm_route",
        lambda profile, module, task: (
            "llm:lmstudio",
            "llm:lmstudio:qwen-world-settings",
        ),
    )
    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda provider_name=None: provider if provider_name == "lmstudio" else None,
    )

    generator = build_production_world_forge_generator(
        WorldForgeProviderConfig(mode="auto")
    )

    assert isinstance(generator, ReferenceSafeWorldForgeGenerator)
    assert isinstance(generator.generator, ProviderWorldForgeTopicGenerator)
    assert generator.generator.provider is provider
    assert generator.generator.config.provider == "lmstudio"
    assert generator.generator.config.model == "qwen-world-settings"


def test_production_factory_uses_settings_over_inherited_live_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import shared
    from app.platform import effective_defaults

    provider = _Provider([_payload()])
    monkeypatch.setenv("OMNIX_RPG_WORLD_FORGE_MODE", "live")
    monkeypatch.setenv("OMNIX_RPG_WORLD_FORGE_PROVIDER", "cerebras")
    monkeypatch.setattr(
        effective_defaults,
        "load_effective_profile",
        lambda: object(),
    )
    monkeypatch.setattr(
        effective_defaults,
        "effective_llm_route",
        lambda _profile, _module, _task: ("lmstudio", "local-world"),
    )
    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda provider_name=None: (
            provider if provider_name == "lmstudio" else None
        ),
    )

    generator = build_production_world_forge_generator()

    assert isinstance(generator.generator, ProviderWorldForgeTopicGenerator)
    assert generator.generator.provider is provider
    assert generator.generator.config.provider == "lmstudio"
    assert generator.generator.config.model == "local-world"


def test_configured_unavailable_provider_never_silently_publishes_placeholder_canon() -> None:
    generator = build_production_world_forge_generator(
        WorldForgeProviderConfig(mode="live", provider="missing"),
        provider_factory=lambda name, config: None,
    )
    assert isinstance(generator, UnavailableWorldForgeTopicGenerator)
    with pytest.raises(RuntimeError, match="unavailable"):
        generator.generate(
            _node(),
            seed=36,
            campaign_context={},
            dependency_topics={},
        )


def test_world_forge_pipeline_resolves_the_production_generator_factory() -> None:
    source = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "session"
        / "genesis"
        / "world_forge_pipeline.py"
    ).read_text(encoding="utf-8")
    assert "build_production_world_forge_generator" in source
    assert "ReferenceSafeWorldForgeGenerator()" not in source
