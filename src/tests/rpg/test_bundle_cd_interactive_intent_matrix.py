from __future__ import annotations

import json
import re
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
        match = re.search(r'"player_input":\s*"([^"]+)"', messages[-1].content if messages else "")
        if match:
            text = match.group(1).lower()
        if "road bandit" in text or "attack" in text:
            payload = {"action_type": "combat", "service_kind": "unknown", "target_npc": "road bandit", "requested_terms": ["attack"], "confidence": 0.95}
        elif "old mill" in text or "travel north" in text:
            payload = {"action_type": "travel", "service_kind": "unknown", "target_npc": "", "requested_terms": ["old mill", "north", "road"], "confidence": 0.95}
        elif "join my party" in text or "companion" in text:
            payload = {"action_type": "talk", "service_kind": "unknown", "target_npc": "Bran", "requested_terms": ["join party", "companion"], "confidence": 0.95}
        elif "travelled with me" in text or "traveled with me" in text or "what role" in text:
            payload = {"action_type": "talk", "service_kind": "unknown", "target_npc": "Bran", "requested_terms": ["role", "travel"], "confidence": 0.91}
        elif "what do you know about this place" in text:
            payload = {"action_type": "rumor_inquiry", "service_kind": "rumor", "target_npc": "self", "requested_terms": ["this place"], "confidence": 0.91}
        elif "who are you" in text:
            payload = {"action_type": "talk", "service_kind": "unknown", "target_npc": "Bran", "requested_terms": ["who are you"], "confidence": 0.88}
        elif any(term in text for term in ("quest", "quests", "work", "job", "task")):
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
    pass


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
                    {"offer_id": "bran_meal_stew", "label": "Hot stew", "description": "A hot bowl of stew and bread.", "service_kind": "meal", "provider_id": "npc:Bran", "provider_name": "Bran", "price": {"gold": 0, "silver": 1, "copper": 5}, "availability": "available"}
                ],
            },
            "survival": {"hunger": 10, "thirst": 20, "fatigue": 5},
        },
    }


def _empty_quest_result() -> Dict[str, Any]:
    return {"ok": True, "narration": "The moment responds without producing a major new consequence.", "npc": {"speaker": "", "line": ""}, "visible_interaction_reason": "no_supported_semantic_action_detected", "turn_contract": {"action": {"action_type": "observe"}, "survival": {"hunger": 10, "thirst": 20, "fatigue": 5}}, "companion_quest_summary": {"by_npc": {}, "by_quest": {}, "events": []}}


def _generic_place_result() -> Dict[str, Any]:
    return {"ok": True, "narration": "You ask the general question about this place. The immediate environment offers no specific details, leaving you with a vague sense of where you are.", "npc": {"speaker": "", "line": ""}, "turn_contract": {"action": {"action_type": "observe"}, "survival": {"hunger": 10, "thirst": 20, "fatigue": 5}}}


def _survival_result(player_input: str, turn_index: int) -> Dict[str, Any]:
    lowered = player_input.lower()
    if "drink" in lowered or "water" in lowered:
        narration = "You drink water from your waterskin and your thirst eases."
        survival_action = {
            "action": "drink_waterskin",
            "applied": True,
            "before": {"hunger": 20, "thirst": 30, "fatigue": 5},
            "after": {"hunger": 20, "thirst": 5, "fatigue": 5},
            "need": "thirst",
            "inventory_consumed": [{"item_id": "waterskin", "name": "Waterskin", "quantity_before": 1, "quantity_after": 0}],
        }
    elif "ration" in lowered or "eat" in lowered:
        narration = "You eat a ration and your hunger eases."
        survival_action = {
            "action": "eat_trail_ration",
            "applied": True,
            "before": {"hunger": 20, "thirst": 30, "fatigue": 5},
            "after": {"hunger": 5, "thirst": 30, "fatigue": 5},
            "need": "hunger",
            "inventory_consumed": [{"item_id": "trail_ration", "name": "Trail Ration", "quantity_before": 1, "quantity_after": 0}],
        }
    else:
        narration = "Your survival state shows hunger and thirst are currently manageable."
        survival_action = {}
    survival = {"hunger": max(0, 20 - turn_index), "thirst": max(0, 30 - turn_index), "fatigue": 5}
    return {"ok": True, "narration": narration, "npc": {"speaker": "", "line": ""}, "turn_contract": {"action": {"action_type": "survival"}, "survival": survival, "survival_action": survival_action, "survival_pressure": {"hunger": "low", "thirst": "low", "fatigue": "low"}}, "survival_action": survival_action}


def _dialogue_result(player_input: str) -> Dict[str, Any]:
    lowered = player_input.lower()
    if "who are you" in lowered:
        line = "I'm Bran, keeper of this tavern, and I keep an ear on the road."
    else:
        line = "This place sits where road dust, tavern talk, and passing trouble meet."
    return {"ok": True, "narration": f"Bran answers plainly. {line}", "npc": {"speaker": "Bran", "line": line}, "turn_contract": {"action": {"action_type": "talk"}, "survival": {"hunger": 10, "thirst": 20, "fatigue": 5}}}


def _combat_result(player_input: str, turn_index: int) -> Dict[str, Any]:
    damage = 0 if turn_index <= 1 else 1
    hp_before = None if turn_index <= 1 else max(1, 6 - turn_index)
    hp_after = None if hp_before is None else max(0, hp_before - damage)
    defeated = bool(hp_after == 0)
    combat_state = {
        "active": not defeated,
        "participants": {
            "player": {"actor_id": "player", "side": "party", "name": "You", "hp": 20, "max_hp": 20, "status": "active"},
            "enemy:bandit_1": {"actor_id": "enemy:bandit_1", "side": "enemy", "name": "Bandit", "hp": 4 if hp_after is None else hp_after, "max_hp": 4, "status": "defeated" if defeated else "active"},
        },
    }
    combat_result = {
        "reason": "combat_started" if turn_index == 1 else ("combat_defeat_resolved" if defeated else "combat_attack_resolved"),
        "actor_id": "player" if turn_index > 1 else "",
        "target_id": "enemy:bandit_1" if turn_index > 1 else "",
        "damage_applied": damage,
        "target_hp_before": hp_before,
        "target_hp_after": hp_after,
        "defeated": defeated,
        "combat_ended": defeated,
        "combat_state": combat_state,
    }
    narration = "You commit to the attack, keeping pressure on the road bandit."
    if defeated:
        narration = "You defeat the bandit and the combat ends."
    return {"ok": True, "narration": narration, "npc": {"speaker": "", "line": ""}, "combat_result": combat_result, "combat_state": combat_state, "turn_contract": {"action": {"action_type": "combat", "target": "road bandit"}, "survival": {"hunger": 10, "thirst": 20, "fatigue": 5}}}


def _travel_result(player_input: str) -> Dict[str, Any]:
    return {"ok": True, "narration": "You follow the road north toward the old mill.", "npc": {"speaker": "", "line": ""}, "turn_contract": {"action": {"action_type": "travel", "destination": "old mill"}, "survival": {"hunger": 12, "thirst": 23, "fatigue": 7}}}


def _party_result(player_input: str) -> Dict[str, Any]:
    lowered = player_input.lower()
    party_state = {"companions": [], "max_size": 3}
    acceptance = {}
    if "yes" in lowered or "let's go" in lowered or "join my party" in lowered and "yes" in lowered:
        line = "Bran nods. Then I am with you."
        narration = "Bran joins your party and falls in beside you."
        party_state = {
            "companions": [
                {
                    "npc_id": "npc:Bran",
                    "name": "Bran",
                    "role": "companion",
                    "follow_mode": "following_player",
                    "status": "active",
                }
            ],
            "max_size": 3,
        }
        acceptance = {"accepted": True, "reason": "player_accepted_companion_offer", "npc_id": "npc:Bran"}
    elif "stay close" in lowered or "companion" in lowered and "close" in lowered:
        line = "I am with you. I'll keep close."
        narration = "Bran remains with the party as your companion."
        party_state = {
            "companions": [
                {
                    "npc_id": "npc:Bran",
                    "name": "Bran",
                    "role": "companion",
                    "follow_mode": "following_player",
                    "status": "active",
                }
            ],
            "max_size": 3,
        }
    elif "role" in lowered:
        line = "If I travelled with you, I'd keep watch and talk us through trouble."
        narration = f"Bran weighs the companion request. {line}"
    else:
        line = "If you truly mean it, say the word and I will walk with you."
        narration = "Bran weighs the companion offer and says he is willing to join if you confirm it."
    return {
        "ok": True,
        "narration": narration,
        "npc": {"speaker": "Bran", "line": line},
        "party_state": party_state,
        "companion_acceptance_result": acceptance,
        "party_aware_turn_context": {"requested_companion": "Bran"},
        "simulation_state": {"player_state": {"party_state": party_state}},
        "turn_contract": {"action": {"action_type": "talk", "target": "Bran"}, "survival": {"hunger": 10, "thirst": 20, "fatigue": 5}},
    }


def _matrix_fake_turn(*, session_id, turn, turn_index, scenario_name, target_channel, **kwargs):
    player_input = turn.get("player") if isinstance(turn, dict) else str(turn)
    lowered = player_input.lower()
    if "road bandit" in lowered or "attack" in lowered:
        raw_result = _combat_result(player_input, turn_index)
    elif "old mill" in lowered or "travel north" in lowered:
        raw_result = _travel_result(player_input)
    elif "join my party" in lowered or "companion" in lowered or "travelled with me" in lowered or "traveled with me" in lowered or "what role" in lowered:
        raw_result = _party_result(player_input)
    elif any(term in lowered for term in ("food", "bread", "stew", "how much", "buy")):
        raw_result = _service_offer_result()
    elif "what do you know about this place" in lowered:
        raw_result = _generic_place_result()
    elif any(term in lowered for term in ("quest", "quests", "rumor", "rumors", "news", "work", "job")):
        raw_result = _empty_quest_result()
    elif any(term in lowered for term in ("hungry", "thirsty", "drink", "water", "ration", "survival")):
        raw_result = _survival_result(player_input, turn_index)
    else:
        raw_result = _dialogue_result(player_input)
    return {"turn_index": turn_index, "player_input": player_input, "raw_result": raw_result, "raw_narration": raw_result.get("narration", ""), "raw_npc": raw_result.get("npc", {}), "llm_called": False, "scenario_warnings": [], "regression_warnings": []}


def _run_offline_matrix(tmp_path, scenarios=None, provider=None):
    provider = provider or _MatrixFakeProvider()
    result = matrix.run_intent_matrix(scenarios=scenarios, output_root=tmp_path, provider_factory=lambda: provider, turn_executor_patch=_matrix_fake_turn, ensure_session_patch=lambda session_id: {"session_id": session_id}, reset_session_patch=lambda session_id: None, live_provider=True, seed_live_survival=False)
    return provider, result


def test_bundle_cd_matrix_defines_realistic_multi_turn_scenarios() -> None:
    scenarios = matrix.default_intent_matrix_scenarios()
    ids = {scenario.scenario_id for scenario in scenarios}
    assert "commerce_food_purchase" in ids
    assert "quest_no_backed_state" in ids
    assert "rumor_news_no_backed_state" in ids
    assert "survival_food_and_water" in ids
    assert "npc_dialogue_persona" in ids
    assert "combat_basic_attack" in ids
    assert "travel_route_choice" in ids
    assert "party_companion_recruitment" in ids
    assert all(len(scenario.commands) >= 2 for scenario in scenarios)


def test_bundle_cd_offline_matrix_runs_all_scenarios_and_writes_artifacts(tmp_path) -> None:
    provider, result = _run_offline_matrix(tmp_path)
    summary = result["summary"]
    assert summary["format_version"] == "interactive_intent_matrix_v4"
    assert summary["scenario_count"] == 8
    assert summary["passed"] == 8
    assert summary["failed"] == []
    assert Path(summary["html_report_path"]).exists()
    assert len(provider.calls) == sum(len(scenario.commands) for scenario in matrix.default_intent_matrix_scenarios())
    assert (tmp_path / "interactive-intent-matrix-summary.json").exists()
    report_html = (tmp_path / "interactive-intent-matrix-report.html").read_text(encoding="utf-8")
    assert "combat_basic_attack" in report_html
    assert "combat_basic_attack/interactive-report.html" in report_html
    assert "Combat Progress" in report_html
    assert "Party Progress" in report_html
    assert "Final defeated" in report_html
    for scenario in matrix.default_intent_matrix_scenarios():
        assert (tmp_path / scenario.scenario_id / "interactive-report.html").exists()
        assert (tmp_path / scenario.scenario_id / "interactive-transcript.json").exists()
        assert (tmp_path / scenario.scenario_id / "interactive-campaign-results.zip").exists()


def test_bundle_cd_matrix_clears_previous_results_before_run(tmp_path) -> None:
    stale_file = tmp_path / "old-summary.json"
    stale_file.write_text("stale", encoding="utf-8")
    stale_dir = tmp_path / "old_scenario"
    stale_dir.mkdir()
    (stale_dir / "interactive-report.html").write_text("stale", encoding="utf-8")

    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "travel_route_choice"][0]
    _, result = _run_offline_matrix(tmp_path, [scenario])

    assert result["summary"]["passed"] == 1
    assert not stale_file.exists()
    assert not stale_dir.exists()
    assert (tmp_path / "travel_route_choice" / "interactive-report.html").exists()


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
    bad_result = {"summary": {"completed_turns": len(scenario.commands)}, "turns": [{"player_input": cmd, "raw_narration": "Bran says he has food.", "raw_npc": {"speaker": "Bran", "line": "Food, yes."}, "interactive_cli_intent_diagnostics": {"provider_called": True, "final_classification": {"service_kind": "meal", "action_type": "service_inquiry"}}, "narration_source": "deterministic_or_runtime"} for cmd in scenario.commands]}
    validation = matrix.validate_matrix_run(scenario, bad_result)
    assert validation["ok"] is False
    assert any("Hot stew" in failure or "1 silver" in failure or "5 copper" in failure for failure in validation["failures"])


def test_bundle_ce1_validator_does_not_count_player_input_as_visible_response() -> None:
    scenario = matrix.IntentMatrixScenario(scenario_id="visible_only_probe", title="Visible only probe", commands=("What do you know about this place?",), expectations=(matrix.TurnExpectation(1, contains_any=("place",), provider_called=True),))
    bad_result = {"summary": {"completed_turns": 1}, "turns": [{"player_input": "What do you know about this place?", "raw_narration": "Bran says nothing useful.", "raw_npc": {"speaker": "Bran", "line": "Nothing useful."}, "interactive_cli_intent_diagnostics": {"provider_called": True, "final_classification": {"action_type": "talk", "service_kind": "unknown"}}, "narration_source": "provider_intent_classifier"}]}
    validation = matrix.validate_matrix_run(scenario, bad_result)
    assert validation["ok"] is False
    assert any("expected visible" in failure for failure in validation["failures"])


def test_bundle_ce21_validator_requires_visible_npc_line() -> None:
    scenario = matrix.IntentMatrixScenario(scenario_id="npc_line_probe", title="NPC line probe", commands=("What do you know about this place?",), expectations=(matrix.TurnExpectation(1, contains_any=("place",), npc_line_contains_any=("place",), require_npc_line=True, provider_called=True),))
    bad_result = {"summary": {"completed_turns": 1}, "turns": [{"player_input": "What do you know about this place?", "raw_narration": "You ask about this place and get a vague feeling.", "raw_npc": {"speaker": "", "line": ""}, "interactive_cli_intent_diagnostics": {"provider_called": True, "final_classification": {"action_type": "rumor_inquiry", "service_kind": "rumor"}}, "narration_source": "provider_intent_classifier"}]}
    validation = matrix.validate_matrix_run(scenario, bad_result)
    assert validation["ok"] is False
    assert any("NPC line" in failure for failure in validation["failures"])


def test_bundle_ce21_place_dialogue_repairs_blank_npc_even_with_generic_narration(tmp_path) -> None:
    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "npc_dialogue_persona"][0]
    provider = _PlaceRumorFakeProvider()
    _, result = _run_offline_matrix(tmp_path, [scenario], provider=provider)
    validation = result["results"][0]["validation"]
    assert validation["ok"] is True
    turns = result["results"][0]["result"]["turns"]
    assert turns[1]["interactive_cli_intent_diagnostics"]["final_classification"]["action_type"] == "rumor_inquiry"
    assert turns[1]["interactive_cli_intent_diagnostics"]["final_classification"]["target_npc"] == "self"
    assert turns[1]["interactive_cli_quest_followup"]["applied"] is True
    assert turns[1]["interactive_cli_quest_followup"]["inquiry_kind"] == "dialogue"
    assert turns[1]["narration_source"] == "dialogue_repaired"
    npc_blob = json.dumps(turns[1].get("raw_npc", {}), ensure_ascii=False).lower()
    assert any(word in npc_blob for word in ("place", "tavern", "road", "town"))
    assert "confirmed rumors" not in json.dumps(turns[1], ensure_ascii=False)
    assert '"speaker": "self"' not in npc_blob


def test_bundle_cf2_survival_visible_repair_uses_authoritative_relief(tmp_path) -> None:
    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "survival_food_and_water"][0]
    _, result = _run_offline_matrix(tmp_path, [scenario])
    validation = result["results"][0]["validation"]
    assert validation["ok"] is True
    turns = result["results"][0]["result"]["turns"]
    assert turns[0]["narration_source"] == "survival_repaired"
    assert turns[1]["narration_source"] == "survival_repaired"
    assert turns[2]["narration_source"] == "survival_repaired"
    assert "hunger" in turns[0]["raw_narration"].lower()
    assert "thirst" in turns[0]["raw_narration"].lower()
    assert "fatigue" in turns[0]["raw_narration"].lower()
    assert "thirst improves" in turns[1]["raw_narration"].lower()
    assert "waterskin" in turns[1]["raw_narration"].lower()
    assert "hunger improves" in turns[2]["raw_narration"].lower()
    assert "ration" in turns[2]["raw_narration"].lower()


def test_bundle_cd_combat_scenario_requires_combat_intent_and_target(tmp_path) -> None:
    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "combat_basic_attack"][0]
    _, result = _run_offline_matrix(tmp_path, [scenario])
    validation = result["results"][0]["validation"]
    assert validation["ok"] is True
    for turn in result["results"][0]["result"]["turns"]:
        final = turn["interactive_cli_intent_diagnostics"]["final_classification"]
        assert final["action_type"] == "combat"
        assert "bandit" in final["target_npc"]
        assert "attack" in " ".join(final["requested_terms"])
    combat = result["summary"]["details"]["scenarios"]["combat_basic_attack"]["combat_progress"]
    assert combat["damage_turn_count"] == 4
    assert combat["total_damage"] == 4
    assert combat["hp_after_values"] == [3, 2, 1, 0]
    assert combat["final_defeated"] is True
    assert combat["final_combat_ended"] is True
    assert combat["final_enemy_hp"] == 0


def test_bundle_cd_travel_scenario_requires_destination_terms(tmp_path) -> None:
    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "travel_route_choice"][0]
    _, result = _run_offline_matrix(tmp_path, [scenario])
    validation = result["results"][0]["validation"]
    assert validation["ok"] is True
    for turn in result["results"][0]["result"]["turns"]:
        final = turn["interactive_cli_intent_diagnostics"]["final_classification"]
        assert final["action_type"] == "travel"
        assert "old mill" in " ".join(final["requested_terms"])


def test_bundle_cd_party_scenario_stays_dialogue_not_quest_or_commerce(tmp_path) -> None:
    scenario = [s for s in matrix.default_intent_matrix_scenarios() if s.scenario_id == "party_companion_recruitment"][0]
    _, result = _run_offline_matrix(tmp_path, [scenario])
    validation = result["results"][0]["validation"]
    assert validation["ok"] is True
    turns = result["results"][0]["result"]["turns"]
    assert turns[0]["interactive_cli_intent_diagnostics"]["final_classification"]["action_type"] == "talk"
    assert turns[0]["interactive_cli_intent_diagnostics"]["final_classification"]["service_kind"] == "unknown"
    assert "confirmed job or quest" not in json.dumps(turns, ensure_ascii=False)
    assert "Hot stew" not in json.dumps(turns, ensure_ascii=False)
    party = result["summary"]["details"]["scenarios"]["party_companion_recruitment"]["party_progress"]
    assert party["accepted_turns"] == [2]
    assert party["final_bran_present"] is True
    assert party["final_bran_role"] == "companion"
    assert party["final_bran_follow_mode"] == "following_player"


def test_bundle_cd_validator_catches_missing_final_requested_terms() -> None:
    scenario = matrix.IntentMatrixScenario(
        scenario_id="requested_terms_probe",
        title="Requested terms probe",
        commands=("I travel north toward the old mill.",),
        expectations=(matrix.TurnExpectation(1, contains_any=("old mill",), final_action_type="travel", final_requested_terms_contains_any=("old mill",), provider_called=True),),
    )
    bad_result = {
        "summary": {"completed_turns": 1},
        "turns": [
            {
                "raw_narration": "You travel toward the old mill.",
                "raw_npc": {"speaker": "", "line": ""},
                "interactive_cli_intent_diagnostics": {"provider_called": True, "final_classification": {"action_type": "travel", "service_kind": "unknown", "requested_terms": []}},
                "narration_source": "provider_intent_classifier",
            }
        ],
    }
    validation = matrix.validate_matrix_run(scenario, bad_result)
    assert validation["ok"] is False
    assert any("requested_terms" in failure for failure in validation["failures"])


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
    assert "combat_basic_attack" in source
    assert "travel_route_choice" in source
    assert "party_companion_recruitment" in source
