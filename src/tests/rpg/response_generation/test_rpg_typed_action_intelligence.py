from __future__ import annotations

import json

from app.providers.base import ChatResponse, ProviderConfig
from app.rpg.ai.action_intelligence import get_action_advisory
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


def test_semantic_packet_uses_central_structured_negotiation() -> None:
    provider = _Provider(
        [
            {
                "action_intent": {"action_type": "observe"},
                "semantic_advisory": {"semantic_family": "observation"},
                "dialogue_gate": {"safe_to_display_now": False},
                "final_narration_candidate": {},
                "reason": "Observation requires runtime grounding.",
            }
        ],
        "typed-semantic-packet",
    )
    gateway = AppLLMGateway(provider)

    packet = gateway.complete_semantic_packet("classify", response_schema={})

    assert json.loads(packet["text"])["action_intent"]["action_type"] == "observe"
    assert provider.calls[0]["response_format"]["type"] == "json_schema"
    assert gateway.last_structured_diagnostics is not None
    assert gateway.last_structured_diagnostics.contract_id == "rpg.semantic_action.packet"
