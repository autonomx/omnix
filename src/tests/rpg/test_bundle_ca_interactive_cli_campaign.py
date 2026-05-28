from __future__ import annotations

import json
import zipfile
from pathlib import Path

from rpg import interactive_cli_campaign as cli
from rpg.interactive_cli_commerce_followup import (
    apply_commerce_followup_repair,
    extract_service_offer_context,
    infer_requested_service_kind,
    is_commerce_followup_question,
    is_purchase_confirmation,
)


def _service_offer_result():
    return {
        "ok": True,
        "narration": "Bran confirms he has provisions available.",
        "npc": {"speaker": "Bran", "line": "We have a hot stew ready, traveler."},
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
            "survival_pressure": {"hunger": "low", "thirst": "low", "fatigue": "low"},
        },
    }


def _drink_offer_result():
    return {
        "ok": True,
        "narration": "The NPC does not hand over any coin.",
        "npc": {"speaker": "NPC", "line": "No coin changes hands. I can't agree to that."},
        "turn_contract": {
            "action": {"action_type": "service_inquiry"},
            "service_result": {
                "kind": "service_inquiry",
                "status": "offers_available",
                "provider_id": "npc:Bran",
                "provider_name": "Bran",
                "service_kind": "drink",
                "offers": [
                    {
                        "offer_id": "bran_drink_ale",
                        "label": "Mug of ale",
                        "description": "A mug of local ale.",
                        "service_kind": "drink",
                        "provider_id": "npc:Bran",
                        "provider_name": "Bran",
                        "price": {"gold": 0, "silver": 0, "copper": 8},
                        "availability": "available",
                    }
                ],
            },
            "survival": {"hunger": 10, "thirst": 20, "fatigue": 5},
            "survival_pressure": {"hunger": "low", "thirst": "low", "fatigue": "low"},
        },
    }


def _fake_turn(*, session_id, turn, turn_index, scenario_name, target_channel, **kwargs):
    player_input = turn.get("player") if isinstance(turn, dict) else str(turn)
    lowered = player_input.lower()
    if "food for sale" in lowered:
        raw_result = _service_offer_result()
    elif "bread for sale" in lowered:
        raw_result = _drink_offer_result()
    else:
        thirst = max(0, 50 - turn_index)
        raw_result = {
            "ok": True,
            "narration": f"Result for {player_input}",
            "turn_contract": {
                "survival": {"hunger": 10, "thirst": thirst, "fatigue": 5},
                "survival_pressure": {"hunger": "low", "thirst": "low", "fatigue": "low"},
                "survival_tick_result": {"applied": True, "reason": "standard_turn", "turn_id": f"turn:{turn_index}"},
            },
            "session": {
                "simulation_state": {
                    "survival": {"hunger": 10, "thirst": thirst, "fatigue": 5, "events": []},
                }
            },
        }
    return {
        "turn_index": turn_index,
        "player_input": player_input,
        "raw_result": raw_result,
        "raw_narration": raw_result["narration"],
        "raw_npc": raw_result.get("npc", {}),
        "llm_called": False,
        "scenario_warnings": [],
        "regression_warnings": [],
    }


def test_bundle_ca_builds_interactive_summary_json_safe() -> None:
    summary = cli.build_interactive_campaign_summary(
        run_id="run1",
        session_id="session1",
        requested_turns=3,
        turns=[{"turn_index": 1, "llm_called": False}, {"turn_index": 2, "scenario_warnings": ["warn"]}],
        started_at=100.0,
        ended_at=103.25,
        stop_reason="turn_limit",
    )

    assert summary["format_version"] == "interactive_cli_campaign_v2"
    assert summary["completed_turns"] == 2
    assert summary["warning_count"] == 1
    assert summary["elapsed_seconds"] == 3.25
    assert summary["commerce_followup_repair_count"] == 0
    json.dumps(summary)


def test_bundle_ca_writes_interactive_artifacts_and_survival_zip(tmp_path) -> None:
    turns = [_fake_turn(session_id="s", turn={"player": "look"}, turn_index=1, scenario_name="x", target_channel="x")]
    summary = cli.build_interactive_campaign_summary(
        run_id="run1",
        session_id="session1",
        requested_turns=1,
        turns=turns,
        started_at=100.0,
        ended_at=101.0,
        stop_reason="turn_limit",
    )

    result = cli.write_interactive_campaign_artifacts(output_dir=tmp_path, summary=summary, turns=turns)

    assert result["ok"] is True
    assert (tmp_path / "interactive-summary.json").exists()
    assert (tmp_path / "interactive-transcript.json").exists()
    assert (tmp_path / "interactive-report.html").exists()
    assert (tmp_path / "survival" / "survival-index.html").exists()
    assert (tmp_path / "survival" / "survival-readiness.json").exists()
    with zipfile.ZipFile(tmp_path / "interactive-campaign-results.zip", "r") as zf:
        names = set(zf.namelist())
        assert "interactive-summary.json" in names
        assert "interactive-transcript.json" in names
        assert "interactive-report.html" in names
        assert "survival/survival-index.html" in names
        assert "survival/survival-readiness.json" in names


def test_bundle_ca_scripted_runner_uses_fixed_turn_count_and_writes_report(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_run_one_manual_turn", _fake_turn)
    monkeypatch.setattr(cli, "_ensure_manual_session", lambda session_id: {"session_id": session_id})
    monkeypatch.setattr(cli, "_reset_manual_session_artifacts", lambda session_id: None)

    result = cli.run_interactive_campaign(
        turns=2,
        session_id="interactive_test_session",
        output_dir=tmp_path,
        scripted_commands=["look around", "drink water"],
        console_llm=False,
    )

    assert result["summary"]["completed_turns"] == 2
    assert result["summary"]["requested_turns"] == 2
    assert result["summary"]["stop_reason"] == "turn_limit"
    assert [turn["player_input"] for turn in result["turns"]] == ["look around", "drink water"]
    assert Path(result["artifacts"]["html_path"]).exists()
    assert Path(result["artifacts"]["zip_path"]).exists()


def test_bundle_ca_scripted_runner_honors_stop_command(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_run_one_manual_turn", _fake_turn)
    monkeypatch.setattr(cli, "_ensure_manual_session", lambda session_id: {"session_id": session_id})
    monkeypatch.setattr(cli, "_reset_manual_session_artifacts", lambda session_id: None)

    result = cli.run_interactive_campaign(
        turns=5,
        session_id="interactive_test_session",
        output_dir=tmp_path,
        scripted_commands=["look", "/quit", "ignored"],
        console_llm=False,
    )

    assert result["summary"]["completed_turns"] == 1
    assert result["summary"]["stop_reason"] == "user_stop_command"


def test_bundle_ca1_extracts_service_offer_context_from_authoritative_turn_result() -> None:
    context = extract_service_offer_context(_service_offer_result())

    assert context["provider_name"] == "Bran"
    assert context["service_kind"] == "meal"
    assert context["offers"][0]["label"] == "Hot stew"
    assert context["offers"][0]["price"] == {"gold": 0, "silver": 1, "copper": 5}


def test_bundle_ca1_commerce_followup_question_detection_covers_vague_provisions() -> None:
    assert is_commerce_followup_question("i ask: what kind of provisions do you have available?")
    assert is_commerce_followup_question("i ask: well? what do you have?")
    assert is_commerce_followup_question("do you serve food?")
    assert is_commerce_followup_question("how much for bread?")
    assert is_commerce_followup_question("ok, let me know how much does bread cost")
    assert is_commerce_followup_question("do you have bread for sale?")
    assert infer_requested_service_kind("how much for bread?") == "meal"
    assert not is_commerce_followup_question("I look around the tavern")


def test_bundle_ca3_purchase_confirmation_detection_covers_tendered_coin() -> None:
    assert is_purchase_confirmation("here you go, 1 silver, 5 copper. confirming the purchase")
    assert is_purchase_confirmation("purchase confirmed")
    assert is_commerce_followup_question("confirmed. Here you go, 1 silver, 5 copper")
    assert not is_purchase_confirmation("ill buy a hot stew")


def test_bundle_ca1_commerce_followup_repair_answers_from_last_authoritative_service_offer() -> None:
    context = extract_service_offer_context(_service_offer_result())
    turn = _fake_turn(
        session_id="s",
        turn={"player": "i ask: what kind of provisions do you have available?"},
        turn_index=2,
        scenario_name="x",
        target_channel="x",
    )

    repaired = apply_commerce_followup_repair(
        turn,
        player_input="i ask: what kind of provisions do you have available?",
        last_offer_context=context,
    )

    blob = json.dumps(repaired, ensure_ascii=False)
    assert repaired["interactive_cli_commerce_followup"]["applied"] is True
    assert "Hot stew" in blob
    assert "1 silver" in blob
    assert "5 copper" in blob
    assert repaired["raw_npc"]["speaker"] == "Bran"
    assert "hot bowl of stew and bread" in repaired["raw_npc"]["line"].lower()


def test_bundle_ca2_repair_overrides_vague_current_service_answer_to_include_prices() -> None:
    turn = _fake_turn(
        session_id="s",
        turn={"player": "I ask bran if he has any food for sale"},
        turn_index=1,
        scenario_name="x",
        target_channel="x",
    )
    repaired = apply_commerce_followup_repair(
        turn,
        player_input="I ask bran if he has any food for sale",
        last_offer_context={},
    )

    assert repaired["interactive_cli_commerce_followup"]["applied"] is True
    assert "Hot stew" in repaired["raw_narration"]
    assert "1 silver" in repaired["raw_npc"]["line"]
    assert "5 copper" in repaired["raw_npc"]["line"]


def test_bundle_ca2_repair_prefers_last_meal_offer_when_current_result_mismatches_bread_to_ale() -> None:
    meal_context = extract_service_offer_context(_service_offer_result())
    turn = _fake_turn(
        session_id="s",
        turn={"player": "do you have bread for sale?"},
        turn_index=5,
        scenario_name="x",
        target_channel="x",
    )
    repaired = apply_commerce_followup_repair(
        turn,
        player_input="do you have bread for sale?",
        last_offer_context=meal_context,
    )

    blob = json.dumps(repaired, ensure_ascii=False)
    assert repaired["interactive_cli_commerce_followup"]["applied"] is True
    assert repaired["interactive_cli_commerce_followup"]["requested_service_kind"] == "meal"
    assert repaired["interactive_cli_commerce_followup"]["current_context_service_kind"] == "drink"
    assert "Hot stew" in blob
    assert "Mug of ale" not in repaired["raw_npc"]["line"]
    assert "1 silver" in repaired["raw_npc"]["line"]
    assert "5 copper" in repaired["raw_npc"]["line"]


def test_bundle_ca3_purchase_confirmation_applies_last_authoritative_meal_offer() -> None:
    meal_context = extract_service_offer_context(_service_offer_result())
    turn = _fake_turn(
        session_id="s",
        turn={"player": "here you go, 1 silver, 5 copper. confirming the purchase"},
        turn_index=2,
        scenario_name="x",
        target_channel="x",
    )
    turn["raw_result"]["session"] = {
        "simulation_state": {
            "player_state": {
                "resources": {"hunger": 70, "thirst": 20, "fatigue": 20},
                "inventory_state": {
                    "currency": {"gold": 0, "silver": 2, "copper": 0},
                    "items": [],
                },
            },
            "climate_survival": {
                "survival": {"hunger": 70, "thirst": 20, "fatigue": 20},
            },
        }
    }

    repaired = apply_commerce_followup_repair(
        turn,
        player_input="confirmed. Here you go, 1 silver, 5 copper",
        last_offer_context=meal_context,
    )

    service_result = repaired["raw_result"]["service_result"]
    survival_action = repaired["raw_result"]["survival_action"]
    simulation_state = repaired["raw_result"]["session"]["simulation_state"]
    assert repaired["interactive_cli_commerce_followup"]["purchase_confirmation"] is True
    assert service_result["selected_offer_id"] == "bran_meal_stew"
    assert service_result["purchase"]["applied"] is True
    assert survival_action["action_kind"] == "buy_meal"
    assert simulation_state["player_state"]["resources"]["hunger"] == 35
    assert simulation_state["player_state"]["inventory_state"]["currency"] == {
        "gold": 0,
        "silver": 0,
        "copper": 5,
    }


def test_bundle_ca1_scripted_runner_carries_food_offer_into_followup(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_run_one_manual_turn", _fake_turn)
    monkeypatch.setattr(cli, "_ensure_manual_session", lambda session_id: {"session_id": session_id})
    monkeypatch.setattr(cli, "_reset_manual_session_artifacts", lambda session_id: None)

    result = cli.run_interactive_campaign(
        turns=5,
        session_id="interactive_food_test_session",
        output_dir=tmp_path,
        scripted_commands=[
            "I ask bran if he has any food for sale",
            "i say: bran, what food do you have for sale?",
            "how much for bread?",
            "ok, let me know how much does bread cost",
            "do you have bread for sale?",
        ],
        console_llm=False,
    )

    assert result["summary"]["commerce_followup_repair_count"] == 5
    for turn in result["turns"]:
        assert "Hot stew" in turn["raw_narration"]
        assert "1 silver" in turn["raw_npc"]["line"]
        assert "5 copper" in turn["raw_npc"]["line"]
    transcript = json.loads((tmp_path / "interactive-transcript.json").read_text(encoding="utf-8"))
    assert transcript["summary"]["commerce_followup_repair_count"] == 5
    assert "Hot stew" in json.dumps(transcript, ensure_ascii=False)
    assert "Mug of ale" not in result["turns"][-1]["raw_npc"]["line"]


def test_bundle_ca_cli_source_has_usage_and_main_guard() -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")
    assert "--turns" in source
    assert "--script-file" in source
    assert "if __name__ == \"__main__\"" in source
    assert "interactive-campaign-results.zip" in source
    assert "interactive_cli_commerce_followup" in source
