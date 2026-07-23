from __future__ import annotations

import json
import threading
from dataclasses import replace

from app.providers.base import (
    BaseProvider,
    ChatMessage,
    ChatResponse,
    ConnectionError,
    ModelInfo,
    ProviderConfig,
)
from app.rpg.narrative_engine import (
    AuthorityClass,
    BeatKind,
    BeatPurpose,
    EvidenceBroker,
    EvidenceRecord,
    InMemoryEvidenceSource,
    NarrativeBeat,
    NarrativeEngineService,
    NarrativePlan,
    PresentationProfile,
    TurnPresentationRequest,
    VisibilityClass,
)
from app.rpg.narrative_engine.validation import write_validate_repair
from app.rpg.narrative_engine.writer import writer_payload
from app.rpg.narrative_provider import (
    NarrativeProviderConfig,
    ProductionStructuredNarrativeWriter,
    ProviderNarrativeGenerator,
    build_production_narrative_writer,
)


class _Provider(BaseProvider):
    provider_name = "phase28"

    def __init__(self, responses: list[str | Exception]) -> None:
        self.config = ProviderConfig(provider_type="phase28", model="phase28-model")
        self.responses = list(responses)
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        stream: bool = False,
        **kwargs,
    ):
        with self._lock:
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
            model=model or "phase28-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            finish_reason="stop",
        )

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


def _request() -> TurnPresentationRequest:
    return TurnPresentationRequest(
        request_id="request:phase28",
        turn_id="turn:phase28",
        campaign_id="campaign:phase28",
        player_input="Bran, how is the east road?",
        actor_ids=("npc:bran",),
        target_actor_id="npc:bran",
        presentation_profile=PresentationProfile.FAST,
        metadata={"response_mode": "dialogue"},
    )


def _plan() -> NarrativePlan:
    return NarrativePlan(
        request_id="request:phase28",
        mode="dialogue",
        profile=PresentationProfile.IMMERSIVE,
        word_budget=(1, 80),
        beats=(
            NarrativeBeat(
                beat_id="beat:answer",
                sequence=1,
                kind=BeatKind.DIALOGUE,
                purpose=BeatPurpose.DIRECT_ANSWER,
                speaker_id="npc:bran",
                evidence_refs=("evidence:road",),
                metadata={"evidence_scope": "speaker"},
            ),
        ),
        must_answer="Answer the road question.",
        metadata={},
    )


def _evidence() -> tuple[EvidenceRecord, ...]:
    return (
        EvidenceRecord(
            evidence_id="evidence:road",
            content="The east road is muddy but passable.",
            authority=AuthorityClass.OBJECTIVE_CANON,
            visibility=VisibilityClass.PUBLIC,
            entity_refs=("location:east_road", "npc:bran"),
        ),
    )


def _structured_payload(text: str = "The east road is muddy but passable.") -> str:
    return json.dumps(
        {
            "blocks": [
                {
                    "beat_id": "beat:answer",
                    "sequence": 1,
                    "kind": "dialogue",
                    "purpose": "direct_answer",
                    "speaker_id": "npc:bran",
                    "text": text,
                    "claims": [
                        {
                            "claim_id": "claim:road",
                            "text": "The east road is muddy but passable.",
                            "authority": "objective_canon",
                            "evidence_refs": ["evidence:road"],
                            "scope": "speaker",
                        }
                    ],
                }
            ]
        }
    )


def _service_payload() -> str:
    return json.dumps(
        {
            "blocks": [
                {
                    "beat_id": "beat:1:physical_reaction",
                    "sequence": 1,
                    "kind": "narration",
                    "purpose": "physical_reaction",
                    "text": "Bran pauses over the cup before answering.",
                    "claims": [],
                },
                {
                    "beat_id": "beat:2:direct_answer",
                    "sequence": 2,
                    "kind": "dialogue",
                    "purpose": "direct_answer",
                    "speaker_id": "npc:bran",
                    "text": "The east road is muddy but passable.",
                    "claims": [
                        {
                            "claim_id": "claim:road",
                            "text": "The east road is muddy but passable.",
                            "authority": "objective_canon",
                            "evidence_refs": ["evidence:road"],
                            "scope": "speaker",
                        }
                    ],
                },
            ]
        }
    )


def test_provider_config_reads_bounded_rpg_specific_settings() -> None:
    config = NarrativeProviderConfig.from_environment(
        {
            "OMNIX_RPG_NARRATIVE_WRITER_MODE": "live",
            "OMNIX_RPG_NARRATIVE_PROVIDER": "lmstudio",
            "OMNIX_RPG_NARRATIVE_MODEL": "qwen-test",
            "OMNIX_RPG_NARRATIVE_BASE_URL": "http://127.0.0.1:1234/v1",
            "OMNIX_RPG_NARRATIVE_TIMEOUT_SECONDS": "900",
            "OMNIX_RPG_NARRATIVE_MAX_RETRIES": "99",
            "OMNIX_RPG_NARRATIVE_TEMPERATURE": "4",
        }
    )
    assert config.live_enabled is True
    assert config.provider == "lmstudio"
    assert config.model == "qwen-test"
    assert config.timeout_seconds == 600
    assert config.max_retries == 5
    assert config.temperature == 2.0


def test_live_provider_retries_transient_failure_then_returns_blocks() -> None:
    provider = _Provider([ConnectionError("temporary"), _structured_payload()])
    writer = ProductionStructuredNarrativeWriter(
        ProviderNarrativeGenerator(
            provider,
            NarrativeProviderConfig(
                mode="live",
                provider="phase28",
                model="phase28-model",
                max_retries=2,
            ),
        )
    )

    result = writer.write(_request(), _plan(), _evidence())

    assert result.source == "structured_provider"
    assert result.provider == "phase28"
    assert result.model == "phase28-model"
    assert result.attempt_count == 2
    assert result.blocks[0].claims[0].claim_id == "claim:road"
    assert provider.calls[-1]["kwargs"]["response_format"] == {"type": "json_object"}
    assert provider.calls[-1]["kwargs"]["request_timeout_seconds"] <= 90
    assert "strict JSON only" in provider.calls[-1]["messages"][0].content


def test_dialogue_contract_retries_provider_prose_instead_of_canned_repair() -> None:
    provider = _Provider(
        [
            _structured_payload(),
            _structured_payload("The old road is muddy, and the guards say it remains passable."),
        ]
    )
    writer = ProductionStructuredNarrativeWriter(
        ProviderNarrativeGenerator(
            provider,
            NarrativeProviderConfig(
                mode="live",
                provider="phase28",
                model="phase28-model",
                max_retries=1,
            ),
        )
    )
    request = replace(
        _request(),
        metadata={
            "response_mode": "dialogue",
            "dialogue_quality_context": {
                "llm_prose_required": True,
                "mode": "road_safety",
                "speaker_id": "npc:bran",
                "required_fragments": ["old road", "guards"],
            },
        },
    )

    result = writer.write(request, _plan(), _evidence())

    assert len(provider.calls) == 2
    assert result.raw_metadata["dialogue_quality_attempts"] == 2
    assert result.raw_metadata["dialogue_missing_fragments"] == []
    assert result.raw_metadata["provider_calls_remaining"] == 0
    assert "old road" in result.blocks[0].text.casefold()
    second_payload = json.loads(provider.calls[1]["messages"][1].content)
    assert second_payload["dialogue_revision_feedback"]["reason"] == "dialogue_contract_not_met"
    assert "Speaking plainly" in second_payload["dialogue_contract"]["requirements"][-1]


def test_dialogue_writer_payload_excludes_precomputed_fallback_prose() -> None:
    request = replace(
        _request(),
        authoritative_outcome={
            "stateful": False,
            "visible_response": {
                "npc": {"line": "Speaking plainly, repeat this canned response."},
            },
            "result": {
                "summary": "Speaking plainly, nested canned response.",
                "changed_domains": ["conversation"],
            },
        },
        metadata={
            "response_mode": "dialogue",
            "dialogue_quality_context": {
                "llm_prose_required": True,
                "mode": "business",
                "required_fragments": ["regulars"],
            },
        },
    )

    payload = writer_payload(request, _plan(), _evidence())
    rendered = json.dumps(payload)

    assert "repeat this canned response" not in rendered
    assert "nested canned response" not in rendered
    assert payload["authoritative_outcome"] == {"stateful": False}


def test_lmstudio_uses_supported_json_schema_response_format() -> None:
    provider = _Provider([_structured_payload()])
    writer = ProductionStructuredNarrativeWriter(
        ProviderNarrativeGenerator(
            provider,
            NarrativeProviderConfig(
                mode="live",
                provider="lmstudio",
                model="phase28-model",
            ),
        )
    )

    result = writer.write(_request(), _plan(), _evidence())

    assert result.source == "structured_provider"
    response_format = provider.calls[-1]["kwargs"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "rpg_narrative_blocks"
    schema = response_format["json_schema"]["schema"]
    assert schema["required"] == ["blocks"]
    assert schema["properties"]["blocks"]["type"] == "array"


def test_configured_provider_failure_uses_validated_canonical_fallback() -> None:
    provider = _Provider([ConnectionError("down"), ConnectionError("still down")])
    writer = build_production_narrative_writer(
        NarrativeProviderConfig(
            mode="live",
            provider="phase28",
            model="phase28-model",
            max_retries=1,
        ),
        provider_factory=lambda name, config: provider,
    )

    validated = write_validate_repair(
        _request(),
        _plan(),
        _evidence(),
        writer,
    )

    assert validated.validation.passed is True
    assert validated.fallback_used is True
    assert validated.writer_result.source == "deterministic_writer"
    assert validated.writer_result.raw_metadata == {
        "provider_fallback_reason": "writer_exception:RuntimeError"
    }
    assert len(provider.calls) == 2


def test_provider_claim_metadata_is_rebuilt_without_unsupported_prose() -> None:
    payload = json.loads(_structured_payload())
    payload["blocks"][0]["claims"][0]["text"] = "The moon is made of cheese."
    provider = _Provider([json.dumps(payload)])
    writer = ProductionStructuredNarrativeWriter(
        ProviderNarrativeGenerator(
            provider,
            NarrativeProviderConfig(
                mode="live",
                provider="phase28",
                model="phase28-model",
            ),
        )
    )

    validated = write_validate_repair(
        _request(),
        _plan(),
        _evidence(),
        writer,
    )

    assert validated.validation.passed is True
    assert validated.fallback_used is False
    assert validated.validation.repair_history == ("repaired_provider_claims",)
    assert validated.writer_result.blocks[0].claims[0].text == (
        "The east road is muddy but passable."
    )
    assert validated.writer_result.blocks[0].claims[0].metadata["claim_source"] == (
        "provider_repaired"
    )


def test_offline_mode_deliberately_uses_deterministic_writer() -> None:
    called = False

    def factory(name, config):
        nonlocal called
        called = True
        return _Provider([_structured_payload()])

    writer = build_production_narrative_writer(
        NarrativeProviderConfig(mode="offline", provider="phase28"),
        provider_factory=factory,
    )
    assert writer.__class__.__name__ == "DeterministicNarrativeWriter"
    assert called is False


def test_service_default_resolves_production_writer_factory(monkeypatch) -> None:
    provider = _Provider([_service_payload()])
    writer = ProductionStructuredNarrativeWriter(
        ProviderNarrativeGenerator(
            provider,
            NarrativeProviderConfig(
                mode="live",
                provider="phase28",
                model="phase28-model",
            ),
        )
    )
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: writer,
    )
    service = NarrativeEngineService(
        evidence_broker=EvidenceBroker(
            [InMemoryEvidenceSource(_evidence(), source_id="phase28")]
        )
    )

    generated = service.generate(_request())

    assert generated.response.generation.source == "structured_provider"
    assert generated.response.generation.provider == "phase28"
    assert generated.response.generation.metadata["fallback_used"] is False
    assert generated.response.validation.metadata["grounding_passed"] is True
