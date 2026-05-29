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
from rpg.interactive_cli_quest_followup import (
    apply_quest_followup_repair,
    extract_quest_context,
    is_quest_inquiry,
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


def _empty_quest_turn(*, session_id, turn, turn_index, scenario_name, target_channel, **kwargs):
    player_input = turn.get("player") if isinstance(turn, dict) else str(turn)
    raw_result = {
        "ok": True,
        "narration": "The moment responds without producing a major new consequence.",
        "npc": {"speaker": "", "line": ""},
        "visible_interaction_reason": "no_supported_semantic_action_detected",
        "turn_contract": {
            "action": {"action_type": "observe", "metadata": {"intent_tags": ["quest_seeking"]}},
            "survival": {"hunger": 10, "thirst": 20, "fatigue": 5},
        },
        "companion_quest_summary": {"by_npc": {}, "by_quest": {}, "events": [], "source": "deterministic_companion_quest_runtime"},
        "companion_quest_progress_result": {
            "progressed": False,
            "reason": "no_backed_companion_quest_progress_signal",
            "source": "deterministic_companion_quest_runtime",
        },
    }
    return {
        "turn_index": turn_index,
        "player_input": player_input,
        "raw_result": raw_result,
        "raw_narration": raw_result["narration"],
        "raw_npc": raw_result["npc"],
        "llm_called": False,
        "scenario_warnings": [],
        "regression_warnings": [],
    }


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
    assert diagnostics["format_version"] == "interactive_cli_intent_diagnostics_v3"
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


def test_bundle_cb5_router_preserves_quest_and_rumor_intents_from_provider_json() -> None:
    provider = _FakeProvider("""```json
{
  "action_type": "service_inquiry",
  "service_kind": "paid_information",
  "target_npc": "Bran",
  "requested_terms": ["quests"],
  "confidence": 0.95
}
```""")

    diagnostics = classify_service_intent_with_fallback(
        player_input="well bran, do you have any quests I can do?",
        current_offer_context={},
        last_offer_context={},
        provider_factory=lambda: provider,
    )

    assert diagnostics["format_version"] == "interactive_cli_intent_diagnostics_v3"
    assert diagnostics["provider_called"] is True
    assert diagnostics["llm_classification"]["action_type"] == "quest_inquiry"
    assert diagnostics["llm_classification"]["service_kind"] == "quest"
    assert diagnostics["final_classification"]["requested_terms"] == ["quests"]


def test_bundle_cb5_quest_followup_repair_answers_no_backed_quest_instead_of_blank() -> None:
    provider = _FakeProvider(json.dumps({
        "action_type": "quest_inquiry",
        "service_kind": "quest",
        "target_npc": "Bran",
        "requested_terms": ["quests"],
        "confidence": 0.95,
    }))
    turn = _empty_quest_turn(
        session_id="s",
        turn={"player": "what do you say, bran? have any quests for me?"},
        turn_index=1,
        scenario_name="x",
        target_channel="x",
    )
    turn["interactive_cli_intent_diagnostics"] = classify_service_intent_with_fallback(
        player_input=turn["player_input"],
        current_offer_context={},
        last_offer_context={},
        provider_factory=lambda: provider,
    )

    repaired = apply_quest_followup_repair(turn, player_input=turn["player_input"])

    assert is_quest_inquiry(turn["player_input"], repaired) is True
    assert extract_quest_context(repaired["raw_result"])["has_backed_quest"] is False
    assert repaired["interactive_cli_quest_followup"]["applied"] is True
    assert repaired["raw_npc"]["speaker"] == "Bran"
    assert "do not have a confirmed job or quest" in repaired["raw_npc"]["line"]
    assert "no backed quest" in repaired["raw_narration"].lower()


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

    assert result["summary"]["format_version"] == "interactive_cli_campaign_v4"
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


def test_bundle_cb5_interactive_runner_repairs_bran_quest_request(monkeypatch, tmp_path) -> None:
    provider = _FakeProvider(json.dumps({
        "action_type": "quest_inquiry",
        "service_kind": "quest",
        "target_npc": "Bran",
        "requested_terms": ["quests"],
        "confidence": 0.95,
    }))
    monkeypatch.setattr(cli, "_run_one_manual_turn", _empty_quest_turn)
    monkeypatch.setattr(cli, "_ensure_manual_session", lambda session_id: {"session_id": session_id})
    monkeypatch.setattr(cli, "_reset_manual_session_artifacts", lambda session_id: None)

    result = cli.run_interactive_campaign(
        turns=2,
        session_id="interactive_quest_test_session",
        output_dir=tmp_path,
        scripted_commands=[
            "im looking for a quest",
            "what do you say, bran? have any quests for me?",
        ],
        console_llm=False,
        provider_factory=lambda: provider,
    )

    assert result["summary"]["provider_called_count"] == 2
    assert result["summary"]["quest_followup_repair_count"] == 2
    for turn in result["turns"]:
        assert turn["interactive_cli_quest_followup"]["applied"] is True
        assert turn["narration_source"] == "quest_repaired"
        assert "do not have a confirmed job or quest" in turn["raw_npc"]["line"]
    transcript = json.loads((tmp_path / "interactive-transcript.json").read_text(encoding="utf-8"))
    assert transcript["summary"]["quest_followup_repair_count"] == 2
    html = (tmp_path / "interactive-report.html").read_text(encoding="utf-8")
    assert "Quest inquiry" in html


def test_bundle_cb1_narration_source_helper_reports_repaired_provider_and_deterministic() -> None:
    assert narration_source_for_turn({"interactive_cli_commerce_followup": {"applied": True}}) == "repaired"
    assert narration_source_for_turn({"interactive_cli_quest_followup": {"applied": True}}) == "quest_repaired"
    assert narration_source_for_turn({"interactive_cli_intent_diagnostics": {"provider_called": True}}) == "provider_intent_classifier"
    assert narration_source_for_turn({"raw_result": {"narration": "hello"}}) == "deterministic_or_runtime"
