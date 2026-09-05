from __future__ import annotations

import json

from app.providers.base import ChatResponse, ProviderConfig
from app.rpg.ai.action_intelligence import get_action_advisory
from app.rpg.ai.semantic_action_intelligence import get_semantic_action_advisory
from app.rpg.llm_app_gateway import AppLLMGateway


def _action_payload(*, stateful=True, action_type="observe") -> dict:
    return {
        "action_type": action_type,
        "difficulty": "normal",
        "skill_id": "",
        "intent_tags": ["inspect"],
        "narrative_goal": "inspect the room",
        "target_id": "",
        "target_name": "",
        "stateful": stateful,
        "needs_runtime_resolution": stateful,
        "visible_response": {
            "narration": "You study the room.",
            "npc": {"speaker": "", "line": ""},
        },
        "reason": "Observation intent.",
    }


def _semantic_payload(*, stateful=True, extra_nested: bool = False) -> dict:
    payload = {
        "action_intent": {
            "action_type": "observe",
            "target_id": "",
            "target_name": "",
            "service_kind": "",
            "offer_id": "",
            "confirmation": False,
            "duration_policy": "",
            "confidence": 0.9,
            "ambiguities": [],
            "stateful": stateful,
            "needs_runtime_resolution": stateful,
        },
        "semantic_advisory": {
            "semantic_family": "observation",
            "interaction_mode": "solo",
            "activity_label": "inspect_room",
            "utterance_mode": "action_request",
            "literal_action_requested": True,
            "state_mutation_requested": False,
            "risk_domain": "none",
            "intent_summary": "Inspect the room.",
            "evidence_spans": ["look around"],
        },
        "dialogue_gate": {
            "safe_to_display_now": False,
            "reason": "Runtime observation remains authoritative.",
            "risk_flags": [],
        },
        "final_narration_candidate": {
            "narration": "",
            "npc": {"speaker": "", "line": ""},
        },
        "reason": "Observation requires runtime grounding.",
    }
    if extra_nested:
        payload["action_intent"]["unexpected"] = "rejected"
    return payload


class _Provider:
    provider_name = "lmstudio"

    def __init__(self, payloads: list[dict], model: str) -> None:
        self.config = ProviderConfig(provider_type="lmstudio", model=model)
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    def chat_completion(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), **kwargs})
        return ChatResponse(
            content=json.dumps(self.payloads.pop(0)),
            model=self.config.model or "test-model",
            finish_reason="stop",
        )


def test_action_intelligence_regenerates_string_boolean() -> None:
    provider = _Provider(
        [
            _action_payload(stateful="false"),
            _action_payload(stateful=False),
        ],
        "typed-action-retry",
    )
    advisory = get_action_advisory(
        AppLLMGateway(provider),
        "look around",
        {},
        {},
        {"action_type": "observe"},
    )

    diagnostics = advisory["first_call_grounding_diagnostics"]
    assert advisory["stateful"] is False
    assert diagnostics["provider_parse_ok"] is True
    assert diagnostics["provider_fallback_used"] is False
    assert len(provider.calls) == 2
    assert provider.calls[0]["response_format"]["type"] == "json_schema"


def test_action_intelligence_marks_deterministic_fallback() -> None:
    provider = _Provider(
        [
            _action_payload(stateful="false", action_type="invalid"),
            _action_payload(stateful="false", action_type="invalid"),
        ],
        "typed-action-fallback",
    )
    advisory = get_action_advisory(
        AppLLMGateway(provider),
        "look around",
        {},
        {},
        {"action_type": "observe", "difficulty": "easy"},
    )

    diagnostics = advisory["first_call_grounding_diagnostics"]
    assert advisory["action_type"] == "observe"
    assert advisory["stateful"] is True
    assert advisory["reason"] == "deterministic_candidate_fallback"
    assert diagnostics["provider_status"] == "provider_error"
    assert diagnostics["provider_fallback_used"] is True


def test_semantic_packet_uses_strict_nested_contract() -> None:
    provider = _Provider([_semantic_payload()], "typed-semantic-packet")
    gateway = AppLLMGateway(provider)

    packet = gateway.complete_semantic_packet("classify", response_schema={})
    parsed = json.loads(packet["text"])

    assert parsed["action_intent"]["action_type"] == "observe"
    assert parsed["action_intent"]["stateful"] is True
    assert provider.calls[0]["response_format"]["type"] == "json_schema"
    assert gateway.last_structured_diagnostics is not None
    assert gateway.last_structured_diagnostics.contract_id == "rpg.semantic_action.packet"
    assert gateway.last_structured_diagnostics.contract_version == 3


def test_semantic_packet_regenerates_invalid_nested_boolean() -> None:
    provider = _Provider(
        [_semantic_payload(stateful="false"), _semantic_payload(stateful=False)],
        "typed-semantic-correction",
    )
    gateway = AppLLMGateway(provider)

    packet = gateway.complete_semantic_packet("classify", response_schema={})

    assert json.loads(packet["text"])["action_intent"]["stateful"] is False
    assert len(provider.calls) == 2

    messages = provider.calls[1]["messages"]
    correction_indexes = [
        index
        for index, message in enumerate(messages)
        if message.role == "system"
        and "STRUCTURED_OUTPUT_CORRECTION" in message.content
    ]
    assert len(correction_indexes) == 1

    last_user_index = max(
        index
        for index, message in enumerate(messages)
        if message.role == "user"
    )
    assert correction_indexes[0] < last_user_index
    assert messages[last_user_index].content == "classify"

    correction = messages[correction_indexes[0]].content
    assert "action_intent" in correction
    assert "stateful" in correction


def test_semantic_action_falls_back_when_nested_contract_stays_invalid() -> None:
    provider = _Provider(
        [_semantic_payload(extra_nested=True), _semantic_payload(extra_nested=True)],
        "typed-semantic-fallback",
    )

    advisory = get_semantic_action_advisory(
        AppLLMGateway(provider),
        "look around",
        {},
        {},
        {"action_type": "observe"},
    )

    diagnostics = advisory["first_call_grounding_diagnostics"]
    assert advisory["action_type"] == "observe"
    assert diagnostics["provider_status"] == "provider_error"
    assert diagnostics["provider_parse_ok"] is False
    assert "StructuredSchemaError" in diagnostics["provider_error"]
