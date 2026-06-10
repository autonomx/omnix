from __future__ import annotations

from pathlib import Path

from rpg.interactive_cli_response_quality import (
    RESPONSE_QUALITY_SOURCE,
    apply_interactive_response_quality_cleanup,
    apply_response_quality_to_matrix_result,
)
from tests.rpg import interactive_intent_matrix_zip as zip_runner


def _turn(player_input: str, *, action_type: str, target: str = "", terms=None, narration: str = "The scene shifts with the movement, carrying the pressure of the current lead into the space ahead.", npc=None, narration_source: str = ""):
    npc = npc if npc is not None else {"speaker": "", "line": ""}
    return {
        "turn_index": 1,
        "player_input": player_input,
        "raw_narration": narration,
        "raw_npc": npc,
        "narration_source": narration_source,
        "raw_result": {"narration": narration, "npc": npc, "narration_source": narration_source},
        "extracted": {"narration": narration, "npc_speaker": npc.get("speaker", ""), "npc_line": npc.get("line", "")},
        "interactive_cli_intent_diagnostics": {
            "provider_called": True,
            "raw_text_excerpt": "provider text that may have been superseded",
            "final_classification": {
                "action_type": action_type,
                "target_npc": target,
                "requested_terms": terms or [],
                "service_kind": "unknown",
            },
        },
    }


def test_phase13_50_travel_cleanup_mentions_destination_and_direction():
    cleaned = apply_interactive_response_quality_cleanup(
        _turn("I travel north toward the old mill.", action_type="travel", target="old mill", terms=["old mill", "north"]),
        player_input="I travel north toward the old mill.",
    )

    assert cleaned["interactive_cli_response_quality"]["source"] == RESPONSE_QUALITY_SOURCE
    assert "old mill" in cleaned["raw_narration"]
    assert "north" in cleaned["raw_narration"]
    assert "scene shifts" not in cleaned["raw_narration"].lower()
    assert cleaned["interactive_cli_intent_diagnostics"]["first_call_visible_response_suppressed_by_response_quality"] is True


def test_phase13_50_combat_cleanup_replaces_generic_opening():
    cleaned = apply_interactive_response_quality_cleanup(
        _turn("I draw my sword and attack the road bandit.", action_type="combat", target="road bandit", terms=["attack", "road"]),
        player_input="I draw my sword and attack the road bandit.",
    )

    assert "road bandit" in cleaned["raw_narration"]
    assert "attack" in cleaned["raw_narration"].lower()
    assert cleaned["interactive_cli_response_quality"]["cleanup_source"] == "combat_opening_specificity"


def test_phase13_50_companion_cleanup_removes_meta_player_phrase():
    original = _turn(
        "Yes. Let's go, Bran; join my party.",
        action_type="talk",
        target="Bran",
        terms=["join my party"],
        narration="Bran joins your party and falls in beside you.",
        npc={"speaker": "Bran", "line": 'Bran nods. "Then I am with you. Help the player survive the road ahead."'},
    )
    cleaned = apply_interactive_response_quality_cleanup(original, player_input="Yes. Let's go, Bran; join my party.")

    assert cleaned["raw_npc"]["speaker"] == "Bran"
    assert "Help the player" not in cleaned["raw_npc"]["line"]
    assert "survive the road ahead" in cleaned["raw_npc"]["line"]


def test_phase13_50_dialogue_cleanup_keeps_bran_as_speaker():
    original = _turn(
        "What do you know about this place?",
        action_type="unknown",
        target="The Tavern",
        terms=["this place"],
        narration="The Tavern answers from what is already established about the scene.",
        npc={"speaker": "The Tavern", "line": "This place sits by the road."},
    )
    cleaned = apply_interactive_response_quality_cleanup(original, player_input="What do you know about this place?")

    assert cleaned["raw_npc"]["speaker"] == "Bran"
    assert cleaned["extracted"]["npc_speaker"] == "Bran"
    assert cleaned["raw_narration"].startswith("Bran answers")


def test_phase13_50_dialogue_cleanup_handles_this_place_speaker_from_live_matrix():
    original = _turn(
        "What do you know about this place?",
        action_type="unknown",
        target="This place",
        terms=["this place"],
        narration="This place answers from what is already established about the scene.",
        npc={"speaker": "This place", "line": "This place sits by the road, with the tavern serving as the nearest shelter."},
    )
    cleaned = apply_interactive_response_quality_cleanup(original, player_input="What do you know about this place?")

    assert cleaned["raw_npc"]["speaker"] == "Bran"
    assert cleaned["extracted"]["npc_speaker"] == "Bran"
    assert cleaned["raw_narration"] == "Bran answers from what is already established about the scene."


def test_phase13_50_quest_fallback_cleanup_uses_bran_instead_of_environment_label():
    original = _turn(
        "I'm looking for a quest.",
        action_type="talk",
        target="Environment/Location (Tavern)",
        terms=["quest"],
        narration="Environment/Location (Tavern) checks what he can actually offer and has no backed quest available in the current state.",
        npc={"speaker": "Environment/Location (Tavern)", "line": "I do not have a confirmed job or quest for you right now."},
        narration_source="quest_repaired",
    )
    cleaned = apply_interactive_response_quality_cleanup(original, player_input="I'm looking for a quest.")

    assert cleaned["raw_npc"]["speaker"] == "Bran"
    assert cleaned["raw_narration"].startswith("Bran checks")
    assert cleaned["interactive_cli_response_quality"]["cleanup_source"] == "quest_fallback_speaker_stability"


def test_phase13_50_rumor_fallback_cleanup_uses_bran_instead_of_atmosphere_label():
    original = _turn(
        "Any rumors around here?",
        action_type="talk",
        target="The Town/Tavern Atmosphere",
        terms=["rumor"],
        narration="The Town/Tavern Atmosphere checks the confirmed rumors and news and finds nothing backed by the current state.",
        npc={"speaker": "The Town/Tavern Atmosphere", "line": "I do not have any confirmed rumors or news for you right now."},
        narration_source="rumor_repaired",
    )
    cleaned = apply_interactive_response_quality_cleanup(original, player_input="Any rumors around here?")

    assert cleaned["raw_npc"]["speaker"] == "Bran"
    assert cleaned["raw_narration"].startswith("Bran checks")
    assert cleaned["interactive_cli_response_quality"]["cleanup_source"] == "rumor_fallback_speaker_stability"


def test_phase13_50_matrix_cleanup_counts_changed_turns():
    scenario = type("Scenario", (), {"scenario_id": "travel_route_choice"})()
    result = {
        "results": [
            {
                "scenario": scenario,
                "result": {
                    "turns": [
                        _turn("I travel north toward the old mill.", action_type="travel", target="old mill", terms=["old mill", "north"])
                    ]
                },
            }
        ]
    }

    summary = apply_response_quality_to_matrix_result(result)

    assert summary["changed_turns"] == 1
    turn = result["results"][0]["result"]["turns"][0]
    assert turn["interactive_cli_response_quality"]["cleanup_source"] == "travel_location_specificity"


def test_phase13_50_zip_runner_rewrites_cleaned_artifacts(tmp_path: Path):
    scenario = type("Scenario", (), {"scenario_id": "travel_route_choice", "title": "Travel"})()
    scenario_dir = tmp_path / "travel_route_choice"
    scenario_dir.mkdir()
    item = {
        "scenario": scenario,
        "result": {
            "summary": {"format_version": "test", "completed_turns": 1},
            "turns": [_turn("I travel north toward the old mill.", action_type="travel", target="old mill", terms=["old mill", "north"])],
            "artifacts": {"output_dir": str(scenario_dir)},
        },
        "validation": {"ok": True, "failures": []},
    }

    zip_runner._rewrite_scenario_artifacts_after_cleanup(item)

    transcript = scenario_dir / "interactive-transcript.json"
    assert transcript.exists()
    assert "old mill" in transcript.read_text(encoding="utf-8")
