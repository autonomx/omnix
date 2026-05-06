from tests.rpg.autoplay.parallel_pipeline import (
    build_combined_background_context_packet,
    compact_json_for_prompt,
    prompt_section_metrics,
)
from tests.rpg.autoplay_llm_campaign import (
    _summarize_background_prompt_budget,
    _summarize_combined_quality_shape,
)


def test_combined_context_packet_excludes_raw_large_state_and_keeps_quality_fields():
    simulation_state = {
        "scene": {"title": "Rusty Flagon", "description": "A busy tavern."},
        "present_npcs": ["bran"],
        "npcs": {
            "bran": {
                "name": "Bran",
                "role": "innkeeper",
                "mood": "wary",
                "huge_debug_blob": "x" * 10000,
            }
        },
        "recent_events": [{"summary": "A stranger entered."}],
        "debug_raw_session": "x" * 10000,
    }
    turn_contract = {
        "player_input": "I ask Bran about the mill.",
        "resolved_action": {"type": "ask", "target": "bran"},
        "resolved_result": {"summary": "Bran hears the question."},
        "semantic_action": {"semantic_action_type": "ask"},
    }

    packet = build_combined_background_context_packet(
        player_action="I ask Bran about the mill.",
        simulation_state=simulation_state,
        turn_contract=turn_contract,
        semantic_action_record={"semantic_action_type": "ask"},
    )

    text = compact_json_for_prompt(packet, max_chars=9000)

    assert packet["scene"]["scene_title"] == "Rusty Flagon"
    assert packet["present_npcs"][0]["name"] == "Bran"
    assert packet["turn_contract"]["resolved_action"]["type"] == "ask"
    assert "debug_raw_session" not in text
    assert "huge_debug_blob" not in text


def test_combined_context_packet_includes_loaded_npc_profiles():
    packet = build_combined_background_context_packet(
        player_action="I ask Bran about the mill.",
        simulation_state={
            "scene": {"title": "Tavern"},
            "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
        },
        runtime_state={
            "npc_evolution": {
                "loaded_profiles": {
                    "Bran": {
                        "profile": {
                            "npc_id": "Bran",
                            "arc_stage": "trusting",
                            "axes": {"trust": 4},
                            "memories": [{"summary": "Bran remembers the player."}],
                            "future_hooks": [{"summary": "Bran may offer a rumor."}],
                        }
                    }
                }
            }
        },
        turn_contract={"player_input": "I ask Bran about the mill."},
        semantic_action_record={"semantic_action_type": "ask"},
    )

    assert packet["loaded_npc_profiles"]["Bran"]["arc_stage"] == "trusting"
    assert packet["loaded_npc_profiles"]["Bran"]["axes"]["trust"] == 4
    assert packet["profile_context_summary"]["available"] is True
    assert packet["profile_context_summary"]["npc_ids"] == ["Bran"]
    assert packet["profile_context_summary"]["arc_stages"]["Bran"] == "trusting"


def test_combined_context_packet_profile_summary_empty_without_loaded_profiles():
    packet = build_combined_background_context_packet(
        player_action="I ask Bran about the mill.",
        simulation_state={
            "scene": {"title": "Tavern"},
            "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
        },
        runtime_state={},
        turn_contract={"player_input": "I ask Bran about the mill."},
        semantic_action_record={"semantic_action_type": "ask"},
    )

    assert packet["profile_context_summary"]["available"] is False
    assert packet["loaded_npc_profiles"] == {}


def test_prompt_section_metrics_counts_sections():
    metrics = prompt_section_metrics(
        {
            "system_contract": "abc",
            "context_packet": "x" * 100,
            "output_schema": "schema",
        }
    )

    assert metrics["total_chars"] == 109
    assert metrics["by_section"]["context_packet"]["chars"] == 100
    assert metrics["estimated_tokens"] > 0


def test_summarize_background_prompt_budget():
    transcript = [
        {
            "turn_index": 1,
            "combined_background_llm_result": {
                "source": "provider_combined_background_llm",
                "prompt_metrics": {
                    "total_chars": 1000,
                    "estimated_tokens": 250,
                    "by_section": {
                        "context_packet": {"chars": 800, "estimated_tokens": 200}
                    },
                },
            },
        }
    ]

    summary = _summarize_background_prompt_budget(transcript)

    assert summary["count"] == 1
    assert summary["avg_total_chars"] == 1000
    assert summary["by_section_avg_chars"]["context_packet"] == 800


def test_summarize_combined_quality_shape_counts_narration_and_candidates():
    transcript = [
        {
            "combined_background_llm_result": {
                "narration": "A rich scene unfolds around Bran.",
                "candidates": [
                    {"kind": "semantic_intent"},
                    {"kind": "memory"},
                ],
            }
        }
    ]

    summary = _summarize_combined_quality_shape(transcript)

    assert summary["combined_turns"] == 1
    assert summary["avg_candidate_count"] == 2
    assert summary["candidate_kinds"]["memory"] == 1