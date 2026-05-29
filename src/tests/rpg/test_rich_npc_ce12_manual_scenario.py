from __future__ import annotations

from tests.rpg.manual.dialogue_m16_m18_checks import run_dialogue_m16_m18_check
from tests.rpg.manual.scenarios.registry import build_service_scenarios


def test_bran_rich_profile_manual_scenario_is_registered():
    scenarios = build_service_scenarios()
    scenario = scenarios.get("bran_opinion_sword_styles_uses_rich_profile")

    assert scenario is not None
    assert scenario["turns"][0]["player_input"] == "Bran, what do you think about sword combat styles?"
    assert scenario["checks"][0]["type"] == "dialogue_first_call_grounding"


def test_bran_rich_profile_scenario_seeds_profile_in_supported_setup_paths():
    scenario = build_service_scenarios()["bran_opinion_sword_styles_uses_rich_profile"]

    present_state = scenario["setup_present_npc_state"]
    profile = present_state["npc_index"]["npc:bran"]

    assert "guarded merchant caravans" in profile["biography"]["public"]
    assert profile["personality"]["speech_examples"]
    assert "npc:bran" in present_state["present_npc_ids"]
    assert scenario["setup_scene"]["present_npc_ids"] == ["npc:bran"]


def test_dialogue_first_call_grounding_check_accepts_bran_packet():
    scenario = build_service_scenarios()["bran_opinion_sword_styles_uses_rich_profile"]
    profile = scenario["setup_present_npc_state"]["npc_index"]["npc:bran"]
    result = {
        "stateful": False,
        "needs_runtime_resolution": False,
        "narration": "Bran taps the bar and answers plainly.",
        "npc": {"speaker": "Bran", "line": "Fancy forms are useful until your boots slide in mud."},
        "first_call_grounding_diagnostics": {
            "format_version": "first_call_grounding_diagnostics_v1",
            "turn_grounding_packet": {
                "format_version": "turn_grounding_packet_v1",
                "priority_context": {"addressed_npc_ids": ["npc:bran"]},
                "npc_context": {
                    "addressed_npcs": [
                        {
                            "id": "npc:bran",
                            "biography": profile["biography"],
                            "visible_profile": {"public_biography": profile["biography"]["public"]},
                            "personality_profile": {
                                "summary": profile["personality"]["summary"],
                                "speech_examples": profile["personality"]["speech_examples"],
                            },
                        }
                    ]
                },
            },
        },
    }

    check_result = run_dialogue_m16_m18_check(
        check=scenario["checks"][0],
        result=result,
        session={},
    )

    assert check_result["ok"] is True
    assert check_result["failures"] == []
    assert check_result["speech_example_count"] >= 1


def test_dialogue_first_call_grounding_check_rejects_private_leak():
    scenario = build_service_scenarios()["bran_opinion_sword_styles_uses_rich_profile"]
    profile = scenario["setup_present_npc_state"]["npc_index"]["npc:bran"]
    result = {
        "stateful": False,
        "needs_runtime_resolution": False,
        "npc": {
            "speaker": "Bran",
            "line": "I left a wounded caravan friend behind, and that is why I hate fancy sword styles.",
        },
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {
                "format_version": "turn_grounding_packet_v1",
                "priority_context": {"addressed_npc_ids": ["npc:bran"]},
                "npc_context": {
                    "addressed_npcs": [
                        {
                            "id": "npc:bran",
                            "biography": profile["biography"],
                            "visible_profile": {"public_biography": profile["biography"]["public"]},
                            "personality_profile": {
                                "summary": profile["personality"]["summary"],
                                "speech_examples": profile["personality"]["speech_examples"],
                            },
                        }
                    ]
                },
            }
        },
    }

    check_result = run_dialogue_m16_m18_check(
        check=scenario["checks"][0],
        result=result,
        session={},
    )

    assert check_result["ok"] is False
    assert any(str(f).startswith("private_term_leaked:") for f in check_result["failures"])
