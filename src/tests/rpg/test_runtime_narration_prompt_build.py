from app.rpg.narration.runtime_narration_contract import (
    build_provider_narration_payload,
)


def test_provider_prompt_builds_with_repair_context_without_fstring_format_error():
    # Test that calling with repair_context does not raise ValueError due to f-string formatting
    try:
        build_provider_narration_payload(
            provider=None,  # We don't need a real provider for this test
            player_action="Bran, you owe me 50 gold. Pay me now.",
            turn_contract={
                "player_action": "Bran, you owe me 50 gold. Pay me now.",
                "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
                "current_location": "location:rusty_flagon_tavern",
                "result": {
                    "summary": "Bran refuses the unsupported debt claim.",
                },
            },
            simulation_state={
                "current_location": "location:rusty_flagon_tavern",
                "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
            },
            repair_context={
                "previous_errors": ["provider_json_parse_failed_candidate_envelope"],
                "instruction": "Retry with one complete compact JSON object.",
            },
        )
        # If we get here without exception, the test passes
        assert True
    except ValueError as e:
        # Specifically check it's not an f-string formatting error
        assert "cannot switch from" not in str(e)
        raise