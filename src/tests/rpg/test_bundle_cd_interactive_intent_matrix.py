from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from app.providers.base import ChatMessage, ChatResponse
from rpg import interactive_intent_matrix as matrix


@dataclass
class _FakeConfig:
    model: str = "fake-matrix-model"
    base_url: str = "http://fake-matrix-provider"


class _MatrixFakeProvider:
    provider_name = "fake_matrix_provider"
    provider_display_name = "Fake Matrix Provider"

    def __init__(self):
        self.config = _FakeConfig()
        self.calls = []

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        self.calls.append({"messages": messages, "model": model, "stream": stream, "kwargs": kwargs})
        assert all(isinstance(message, ChatMessage) for message in messages)
        text = "\n".join(message.content for message in messages).lower()
        if any(term in text for term in ("quest", "quests", "work", "job", "task")):
            payload = {"action_type": "quest_inquiry", "service_kind": "quest", "target_npc": "Bran", "requested_terms": ["quests"], "confidence": 0.95}
        elif any(term in text for term in ("rumor", "rumors", "news")):
            payload = {"action_type": "rumor_inquiry", "service_kind": "rumor", "target_npc": "Bran", "requested_terms": ["rumors"], "confidence": 0.94}
        elif any(term in text for term in ("buy", "purchase", "give me", "pay for")) and any(term in text for term in ("stew", "bread", "food")):
            payload = {"action_type": "service_purchase", "service_kind": "meal", "target_npc": "Bran", "requested_terms": ["hot stew"], "confidence": 0.96}
        elif any(term in text for term in ("food", "bread", "stew", "provisions", "how much")):
            payload = {"action_type": "service_inquiry", "service_kind": "meal", "target_npc": "Bran", "requested_terms": ["food", "bread"], "confidence": 0.93}
        elif any(term in text for term in ("drink water", "waterskin", "ration", "hungry", "thirsty")):
            payload = {"action_type": "observe", "service_kind": "unknown", "target_npc": "", "requested_terms": ["survival"], "confidence": 0.82}
        else:
            payload = {"action_type": "talk", "service_kind": "unknown", "target_npc": "Bran", "requested_terms": ["dialogue"], "confidence": 0.8}
        return ChatResponse(content=json.dumps(payload), model=self.config.model)


class _PlaceRumorFakeProvider(_MatrixFakeProvider):
    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        self.calls.append({"messages": messages, "model": model, "stream": stream, "kwargs": kwargs})
        text = "\n".join(message.content for message in messages).lower()
        if "what do you know about this place" in text:
            payload = {"action_type": "rumor_inquiry", "service_kind": "rumor", "target_npc": "self", "requested_terms": ["this place"], "confidence": 0.91}
        else:
            payload = {"action_type": "talk", "service_kind": "unknown", "target_npc": "Bran", "requested_terms": ["dialogue"], "confidence": 0.8}
        return ChatResponse(content=json.dumps(payload), model=self.config.model)


def _service_offer_result() -> Dict[str, Any]:
    return {
        "ok": True,
        "narration": "Bran checks his provisions.",
        "npc": {"speaker": "Bran", "line": "I've got something hot."},
        "turn_contract": {
            "action": {"action_type": "service_inquiry"},
            "service_result": {
                "kind": "service_inquiry",
                "status": "offers_available",
                "provider_id": "npc:Bran",
                "provider_name": "Bran",
                "service_kind": "meal",
                "offers": [
                    {
                        "offer_id": "bran_meal_stew",
                        "label": "Hot stew",
                        "description": "A hot bowl of stew and bread.",
                        "service_kind": "meal",
                        "provider_id": "npc:Bran",
                        "provider_name": "Bran",
                        "price": {"gold": 0, "silver": 1, "copper": 5},
                        "availability": "available",
                    }
                ],
            },
            "survival": {"hunger": 10, "thirst": 20, "fatigue": 5},
        },
    }


def _empty_quest_result() -> Dict[str, Any]:
    return {
        "ok": True,
        "narration": "The moment responds without producing a major new consequence.",
        "npc": {"speaker": "", "line": ""},
        "visible_interaction_reason": "no_supported_semantic_action_detected",
        "turn_contract": {"action": {"action_type": "observe"}, "survival": {"hunger": 10, "thirst": 20, "fatigue": 5}},
        "companion_quest_summary": {"by_npc": {}, "by_quest": {}, "events": []},
    }


def _survival_result(player_input: str, turn_index: int) -> Dict[str, Any]:
    lowered = player_input.lower()
    if "drink" in lowered or "water" in lowered:
        narration = "You drink water from your waterskin and your thirst eases."
    elif "ration" in lowered or "eat" in lowered:
        narration = "You eat a ration and your hunger eases."
    else:
        narration = "Your survival state shows hunger and thirst are currently manageable."
    return {
        "ok": True,
        "narration": narration,
        "npc": {"speaker": "", "line": ""},
        "turn_contract": {
            "action": {"action_type": "survival"},
            "survival": {"hunger": max(0, 20 - turn_index), "thirst": max(0, 30 - turn_index), "fatigue": 5},
            "survival_pressure": {"hunger": "low", "thirst": "low", "fatigue": "low"},
        },
    }


def _dialogue_result(player_input: str) -> Dict[str, Any]:
    lowered = player_input.lower()
    if "who are you" in lowered:
        line = "I'm Bran, keeper of this tavern, and I keep an ear on the road."
    else:
        line = "This place sits where road dust, tavern talk, and passing trouble meet."
    return {
        "ok": True,
        "narration": f"Bran answers plainly. {line}",
        "npc": {"speaker": "Bran", "line": line},
        "turn_contract": {"action": {"action_type": "talk"}, "survival": {"hunger": 10, "thirst": 20, "fatigue": 5}},
    }


def _matrix_fake_turn(*, session_id, turn, turn_index, scenario_name, target_channel, **kwargs):
    player_input = turn.get("player") if isinstance(turn, dict) else str(turn)
    lowered = player_input.lower()
    if any(term in lowered for term in ("food", "bread", "stew", "how much", "buy")):
        raw_result = _service_offer_result()
    elif any(term in lowered for term in ("quest", "quests", "rumor", "rumors", "news", "work", "job")):
        raw_result = _empty_quest_result()
    elif any(term in lowered for term in ("hungry", "thirsty", "drink", "water", "ration", "survival")):
        raw_result = _survival_result(player_input, turn_index)
    else:
        raw_result = _dialogue_result(player_input)
    return {
        "turn_index": turn_index,
        "player_input": player_input,
        "raw_result": raw_result,
        "raw_narration": raw_result.get("narration", ""),
        "raw_npc": raw_result.get("npc", {}),
        "llm_called": False,
        "scenario_warnings": [],
        "regression_warnings": [],
    }


def _run_offline_matrix(tmp_path, scenarios=None, provider=None):
    provider = provider or _MatrixFakeProvider()
    result = matrix.run_intent_matrix(
        scenarios=scenarios,
        output_root=tmp_path,
        provider_factory=lambda: provider,
        turn_executor_patch=_matrix_fake_turn,
        ensure_session_patch=lambda session_id: {"session_id": session_id},
        reset_session_patch=lambda session_id: None,
        live_provider=True,
        seed_live_survival=False,
    )
    return provider, result


def test_bundle_cd_matrix_defines_realistic_multi_turn_scenarios() -> None:
    scenarios = matrix.default_intent_matrix_scenarios()
    ids = {scenario.scenario_id for scenario in scenarios}

    assert "commerce_food_purchase" in ids
    assert "quest_no_backed_state" in ids
    assert "rumor_news_no_backed_state" in ids
    assert "survival_food_and_water" in ids
    assert "npc_dialogue_persona" in ids
    assert all(len(scenario.commands) >= 2 for scenario in scenarios)


def test_bundle_cd_offline_matrix_runs_all_scenarios_and_writes_artifacts(tmp_path) -> None:
    provider, result = _run_offline_matrix(tmp_path)

    summary = result["summary"]
    assert summary["format_version"] == "interactive_intent_matrix_v1"
    assert summary["scenario_count"] == 5
    assert summary["passed"] == 5
    assert summary["failed"] == []
    assert len(provider.calls) == sum(len(scenario.commands) for scenario in matrix.default_intent_matrix_scenarios())
    assert (tmp_path / "interactive-intent-matrix-summary.json").exists()
    for scenario in matrix.default_intent_matrix_scenarios():
        assert (tmp_path / scenario.scenario_id / "interactive-report.html").exists()
        assert (tmp_path / scenario.scenario_id / "interactive-transcript.json").exists()
        assert (tmp_path / scenario.scenario_id / "interactive-campaign-results.zip").exists()


def test_bundle_cd_commerce_visible_response_requires_offer_label_and_price(tmp_path) -> None:
    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "commerce_food_purchase"][0]
    provider, result = _run_offline_matrix(tmp_path, [scenario])

    validation = result["results"][0]["validation"]
    assert validation["ok"] is True
    turns = result["results"][0]["result"]["turns"]
    for turn in turns:
        blob = json.dumps(turn, ensure_ascii=False)
        assert "Hot stew" in blob
        assert "1 silver" in blob
        assert "5 copper" in blob
        assert turn["interactive_cli_intent_diagnostics"]["provider_called"] is True
    assert len(provider.calls) == 4


def test_bundle_cd_quest_visible_response_requires_grounded_no_backed_quest_answer(tmp_path) -> None:
    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "quest_no_backed_state"][0]
    _, result = _run_offline_matrix(tmp_path, [scenario])

    validation = result["results"][0]["validation"]
    assert validation["ok"] is True
    turns = result["results"][0]["result"]["turns"]
    for turn in turns:
        assert turn["interactive_cli_quest_followup"]["applied"] is True
        assert turn["narration_source"] == "quest_repaired"
        assert "confirmed job or quest" in json.dumps(turn, ensure_ascii=False)


def test_bundle_cd_validator_catches_missing_visible_offer_price() -> None:
    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "commerce_food_purchase"][0]
    bad_result = {
        "summary": {"completed_turns": len(scenario.commands)},
        "turns": [
            {
                "player_input": cmd,
                "raw_narration": "Bran says he has food.",
                "raw_npc": {"speaker": "Bran", "line": "Food, yes."},
                "interactive_cli_intent_diagnostics": {"provider_called": True, "final_classification": {"service_kind": "meal", "action_type": "service_inquiry"}},
                "narration_source": "deterministic_or_runtime",
            }
            for cmd in scenario.commands
        ],
    }

    validation = matrix.validate_matrix_run(scenario, bad_result)

    assert validation["ok"] is False
    assert any("Hot stew" in failure or "1 silver" in failure or "5 copper" in failure for failure in validation["failures"])


def test_bundle_ce1_validator_does_not_count_player_input_as_visible_response() -> None:
    scenario = matrix.IntentMatrixScenario(
        scenario_id="visible_only_probe",
        title="Visible only probe",
        commands=("What do you know about this place?",),
        expectations=(matrix.TurnExpectation(1, contains_any=("place",), provider_called=True),),
    )
    bad_result = {
        "summary": {"completed_turns": 1},
        "turns": [
            {
                "player_input": "What do you know about this place?",
                "raw_narration": "Bran says nothing useful.",
                "raw_npc": {"speaker": "Bran", "line": "Nothing useful."},
                "interactive_cli_intent_diagnostics": {"provider_called": True, "final_classification": {"action_type": "talk", "service_kind": "unknown"}},
                "narration_source": "provider_intent_classifier",
            }
        ],
    }

    validation = matrix.validate_matrix_run(scenario, bad_result)

    assert validation["ok"] is False
    assert any("expected visible" in failure for failure in validation["failures"])


def test_bundle_ce1_place_dialogue_is_not_swallowed_by_rumor_repair(tmp_path) -> None:
    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "npc_dialogue_persona"][0]
    provider = _PlaceRumorFakeProvider()
    _, result = _run_offline_matrix(tmp_path, [scenario], provider=provider)

    validation = result["results"][0]["validation"]
    assert validation["ok"] is True
    turns = result["results"][0]["result"]["turns"]
    assert turns[1]["interactive_cli_intent_diagnostics"]["final_classification"]["action_type"] == "rumor_inquiry"
    assert turns[1]["interactive_cli_intent_diagnostics"]["final_classification"]["target_npc"] == "self"
    assert "interactive_cli_quest_followup" not in turns[1] or not turns[1]["interactive_cli_quest_followup"].get("applied")
    assert turns[1]["narration_source"] == "provider_intent_classifier"
    assert "confirmed rumors" not in json.dumps(turns[1], ensure_ascii=False)
    assert '"speaker": "self"' not in json.dumps(turns[1].get("raw_npc", {}), ensure_ascii=False)


def test_bundle_cd_cli_requires_live_provider_flag(capsys) -> None:
    code = matrix.main([])
    captured = capsys.readouterr()

    assert code == 2
    assert "--live-provider" in captured.out


def test_bundle_cd_source_documents_live_provider_command() -> None:
    source = Path(matrix.__file__).read_text(encoding="utf-8")
    assert "--live-provider" in source
    assert "commerce_food_purchase" in source
    assert "quest_no_backed_state" in source
