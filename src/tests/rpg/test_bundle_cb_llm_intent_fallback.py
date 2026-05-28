from __future__ import annotations

import json
from dataclasses import dataclass

from app.providers.base import ChatMessage, ChatResponse
from rpg import interactive_cli_campaign as cli
from rpg.interactive_cli_commerce_followup import extract_service_offer_context
from rpg.interactive_cli_intent_fallback import (
    build_deterministic_intent_classification,
    call_llm_intent_classifier,
    classify_service_intent_with_fallback,
    narration_source_for_turn,
    validate_llm_intent_against_context,
)
from rpg.test_bundle_ca_interactive_cli_campaign import (  # type: ignore
    _drink_offer_result,
    _fake_turn,
    _service_offer_result,
)


@dataclass
class _FakeConfig:
    model: str = "fake-intent-model"
    base_url: str = "http://fake-provider"


class _FakeProvider:
    provider_name = "fake_provider"
    provider_display_name = "Fake Provider"

    def __init__(self, content: str | None = None):
        self.config = _FakeConfig()
        self.calls = []
        self.content = content or json.dumps({
            "action_type": "service_inquiry",
            "service_kind": "meal",
            "target_npc": "Bran",
            "requested_terms": ["bread", "food"],
            "confidence": 0.91,
        })

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        self.calls.append({"messages": messages, "model": model, "stream": stream, "kwargs": kwargs})
        assert all(isinstance(message, ChatMessage) for message in messages)
        return ChatResponse(content=self.content, model=self.config.model)


def test_bundle_cb_deterministic_classifier_still_records_mismatch_diagnostics() -> None:
    current = extract_service_offer_context(_drink_offer_result())
    last = extract_service_offer_context(_service_offer_result())

    deterministic = build_deterministic_intent_classification(
        player_input="do you have bread for sale?",
        current_offer_context=current,
        last_offer_context=last,
    )

    assert deterministic["commerce_question"] is True
    assert deterministic["requested_service_kind"] == "meal"
    assert deterministic["current_context_service_kind"] == "drink"
    assert deterministic["service_kind_mismatch"] is True


def test_bundle_cb3_always_on_router_calls_provider_even_for_clear_meal_context() -> None:
    provider = _FakeProvider()
    current = extract_service_offer_context(_service_offer_result())

    diagnostics = classify_service_intent_with_fallback(
        player_input="what food do you have for sale?",
        current_offer_context=current,
        last_offer_context={},
        provider_factory=lambda: provider,
    )

    assert len(provider.calls) == 1
    assert diagnostics["format_version"] == "interactive_cli_intent_diagnostics_v2"
    assert diagnostics["intent_router_mode"] == "always"
    assert diagnostics["provider_requested"] is True
    assert diagnostics["provider_called"] is True
    assert diagnostics["final_classification"]["service_kind"] == "meal"


def test_bundle_cb3_fallback_mode_can_skip_provider_for_clear_deterministic_case() -> None:
    provider = _FakeProvider()
    current = extract_service_offer_context(_service_offer_result())

    diagnostics = classify_service_intent_with_fallback(
        player_input="what food do you have for sale?",
        current_offer_context=current,
        last_offer_context={},
        provider_factory=lambda: provider,
        force_llm=False,
    )

    assert len(provider.calls) == 0
    assert diagnostics["intent_router_mode"] == "fallback"
    assert diagnostics["provider_called"] is False
    assert diagnostics["why_provider_not_called"] == "fallback_mode_deterministic_not_ambiguous"


def test_bundle_cb_llm_intent_classifier_calls_provider_and_parses_json() -> None:
    provider = _FakeProvider()
    result = call_llm_intent_classifier(
        player_input="how much for bread?",
        deterministic={"needs_llm": True, "service_kind": "unknown"},
        current_offer_context={},
        last_offer_context=extract_service_offer_context(_service_offer_result()),
        provider_factory=lambda: provider,
    )

    assert len(provider.calls) == 1
    assert result["intent"]["service_kind"] == "meal"
    assert result["intent"]["target_npc"] == "Bran"
    assert result["diagnostics"]["provider_called"] is True
    assert result["diagnostics"]["provider_name"] == "fake_provider"
    assert result["diagnostics"]["model"] == "fake-intent-model"


def test_bundle_cb_classify_with_router_records_provider_diagnostics_for_purchase_attempt() -> None:
    provider = _FakeProvider(json.dumps({
        "action_type": "service_purchase",
        "service_kind": "meal",
        "target_npc": "Bran",
        "requested_terms": ["hot stew"],
        "confidence": 0.94,
    }))
    last = extract_service_offer_context(_service_offer_result())

    diagnostics = classify_service_intent_with_fallback(
        player_input="I'll buy a hot stew",
        current_offer_context={},
        last_offer_context=last,
        provider_factory=lambda: provider,
    )

    assert diagnostics["provider_requested"] is True
    assert diagnostics["provider_called"] is True
    assert diagnostics["provider_parse_ok"] is True
    assert diagnostics["llm_classification"]["action_type"] == "service_purchase"
    assert diagnostics["final_classification"]["service_kind"] == "meal"


def test_bundle_cb_validate_llm_intent_is_advisory_not_authoritative_inventory() -> None:
    validation = validate_llm_intent_against_context(
        {"action_type": "service_inquiry", "service_kind": "meal", "confidence": 0.9},
        extract_service_offer_context(_service_offer_result()),
    )

    assert validation["ok"] is True
    assert validation["reason"] == "accepted"

    bad = validate_llm_intent_against_context({"action_type": "unknown", "service_kind": "meal"}, {})
    assert bad["ok"] is False


def test_bundle_cb1_interactive_runner_embeds_provider_diagnostics_every_turn(monkeypatch, tmp_path) -> None:
    provider = _FakeProvider()
    monkeypatch.setattr(cli, "_run_one_manual_turn", _fake_turn)
    monkeypatch.setattr(cli, "_ensure_manual_session", lambda session_id: {"session_id": session_id})
    monkeypatch.setattr(cli, "_reset_manual_session_artifacts", lambda session_id: None)

    result = cli.run_interactive_campaign(
        turns=3,
        session_id="interactive_cb_test_session",
        output_dir=tmp_path,
        scripted_commands=[
            "I look around",
            "I ask bran if he has any food for sale",
            "do you have bread for sale?",
        ],
        console_llm=False,
        provider_factory=lambda: provider,
    )

    assert result["summary"]["format_version"] == "interactive_cli_campaign_v2"
    assert result["summary"]["provider_requested_count"] == 3
    assert result["summary"]["provider_called_count"] == 3
    assert len(provider.calls) == 3
    assert result["turns"][0]["interactive_cli_intent_diagnostics"]["provider_called"] is True
    assert result["turns"][1]["interactive_cli_intent_diagnostics"]["provider_called"] is True
    assert result["turns"][2]["interactive_cli_intent_diagnostics"]["final_classification"]["service_kind"] == "meal"
    transcript = json.loads((tmp_path / "interactive-transcript.json").read_text(encoding="utf-8"))
    assert transcript["summary"]["provider_called_count"] == 3
    assert "interactive_cli_intent_diagnostics" in json.dumps(transcript)
    html = (tmp_path / "interactive-report.html").read_text(encoding="utf-8")
    assert "Provider / intent diagnostics" in html
    assert "provider called" in html


def test_bundle_cb1_narration_source_helper_reports_repaired_provider_and_deterministic() -> None:
    assert narration_source_for_turn({"interactive_cli_commerce_followup": {"applied": True}}) == "repaired"
    assert narration_source_for_turn({"interactive_cli_intent_diagnostics": {"provider_called": True}}) == "provider_intent_classifier"
    assert narration_source_for_turn({"raw_result": {"narration": "hello"}}) == "deterministic_or_runtime"
