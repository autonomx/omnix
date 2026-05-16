from tests.rpg.autoplay_llm_campaign import (
    _apply_direct_graph_display_quality_pass,
    _ensure_social_npc_line_coverage,
    _sync_selected_narration_npc_to_top_level,
)


def test_social_bran_action_gets_deterministic_npc_line_when_missing():
    row = _ensure_social_npc_line_coverage(
        {
            "player_action": "I ask Bran who saw the traveler near the side door.",
            "narration": "The conversation focuses on the immediate lead.",
        }
    )

    assert row["npc_line_fallback_applied"] is True
    assert row["npc_speaker"] == "Bran"
    assert row["npc_line"]


def test_existing_npc_line_is_preserved():
    row = _ensure_social_npc_line_coverage(
        {
            "player_action": "I ask Bran about the witness.",
            "npc_line": "I saw enough to worry me.",
        }
    )

    assert row["npc_line"] == "I saw enough to worry me."
    assert not row.get("npc_line_fallback_applied")


def test_direct_graph_report_action_gets_npc_line_after_quality_pass():
    row = _apply_direct_graph_display_quality_pass(
        {
            "player_action": "I report the ambush evidence to Bran.",
            "direct_graph_action_completion": {
                "action_id": "report_findings_to_bran",
                "mechanics": ["report", "faction_consequence", "npc_reaction"],
                "changed_parts": ["report", "faction_consequence"],
            },
            "narration": "The conversation focuses on the immediate lead.",
        }
    )

    assert row["npc_line_fallback_applied"] is True
    assert row["npc_speaker"] == "Bran"
    assert row["npc_line"]
    assert "proof" in row["npc_line"].lower() or "act" in row["npc_line"].lower()


def test_direct_graph_warn_garran_action_gets_npc_line_after_quality_pass():
    row = _apply_direct_graph_display_quality_pass(
        {
            "player_action": "I warn Garran about the ambush signs on the road.",
            "direct_graph_action_completion": {
                "action_id": "warn_garran",
                "mechanics": ["faction_consequence", "npc_reaction"],
                "changed_parts": ["npc_reaction"],
            },
            "narration": "The conversation focuses on the immediate lead.",
        }
    )

    assert row["npc_line_fallback_applied"] is True
    assert row["npc_speaker"] == "Garran"
    assert row["npc_line"]
    assert "trap" in row["npc_line"].lower() or "careful" in row["npc_line"].lower()


def test_direct_graph_magistrate_social_action_gets_npc_line_after_quality_pass():
    row = _apply_direct_graph_display_quality_pass(
        {
            "player_action": "I ask the magistrate to arrest Captain Voss.",
            "direct_graph_action_completion": {
                "action_id": "ask_magistrate_to_arrest_voss",
                "mechanics": ["faction_consequence", "npc_reaction"],
                "changed_parts": ["npc_reaction"],
            },
            "narration": "The conversation focuses on the immediate lead.",
        }
    )

    assert row["npc_line_fallback_applied"] is True
    assert row["npc_speaker"] == "Magistrate"
    assert row["npc_line"]


def test_selected_narration_npc_syncs_to_top_level_fields():
    row = _sync_selected_narration_npc_to_top_level(
        {
            "player_action": "I report the ambush evidence to Bran.",
            "npc": {},
            "npc_speaker": "",
            "npc_line": "",
            "selected_narration": {
                "narration": "The conversation focuses on the immediate lead.",
                "npc": {
                    "speaker": "Bran",
                    "line": "That is enough to stop guessing. Show me where the proof points next.",
                },
            },
        }
    )

    assert row["top_level_npc_sync_applied"] is True
    assert row["top_level_npc_sync_source"] == "selected_narration.npc"
    assert row["npc"] == {
        "speaker": "Bran",
        "line": "That is enough to stop guessing. Show me where the proof points next.",
    }
    assert row["npc_speaker"] == "Bran"
    assert row["npc_line"] == "That is enough to stop guessing. Show me where the proof points next."


def test_quality_pass_syncs_generated_social_npc_line_to_top_level():
    row = _apply_direct_graph_display_quality_pass(
        {
            "player_action": "I report the ambush evidence to Bran.",
            "direct_graph_action_completion": {
                "action_id": "report_findings_to_bran",
                "mechanics": ["report", "faction_consequence", "npc_reaction"],
                "changed_parts": ["report", "faction_consequence"],
            },
            "npc": {},
            "npc_speaker": "",
            "npc_line": "",
            "selected_narration": {
                "narration": "The conversation focuses on the immediate lead.",
            },
        }
    )

    assert row["npc_speaker"] == "Bran"
    assert row["npc_line"]
    assert row["selected_narration"]["npc"]["speaker"] == "Bran"
    assert row["selected_narration"]["npc"]["line"] == row["npc_line"]


def test_local_patron_social_action_gets_npc_line():
    row = _apply_direct_graph_display_quality_pass(
        {
            "player_action": "I ask a local patron about the mill bridge.",
            "direct_graph_action_completion": {
                "action_id": "ask_patron_bridge",
                "mechanics": ["npc_reaction"],
                "changed_parts": ["npc_reaction"],
            },
            "narration": "The conversation focuses on the immediate lead.",
        }
    )

    assert row["npc_line_fallback_applied"] is True
    assert row["npc_speaker"] == "Local Patron"
    assert row["npc_line"]
    assert "bridge" in row["npc_line"].lower()
