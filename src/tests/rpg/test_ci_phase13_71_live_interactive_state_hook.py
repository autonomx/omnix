from __future__ import annotations

import json
from pathlib import Path

from app.rpg.interactive_cli_live_state import (
    LIVE_INTERACTIVE_STATE_PATCH,
    enrich_live_interactive_turn_with_state,
    make_live_interactive_state_hook,
)
from app.rpg.interactive_cli_state_checkpoint import restore_interactive_cli_state_bundle_from_checkpoint_file


def _turn(command: str, index: int) -> dict:
    return {
        "turn_index": index,
        "player_input": command,
        "raw_result": {
            "narration": "The moment continues.",
            "npc": {"speaker": "Bran", "line": "Aye."},
        },
        "interactive_cli_intent_diagnostics": {
            "final_classification": {
                "action_type": "observe",
                "requested_terms": [],
            }
        },
    }


def test_phase13_71_live_turn_enrichment_carries_bundle_state_across_turns() -> None:
    first = enrich_live_interactive_turn_with_state(
        _turn("Bran, remember this: my trail name is Ash Lantern.", 1),
        player_input="Bran, remember this: my trail name is Ash Lantern.",
        turn_index=1,
    )
    second = enrich_live_interactive_turn_with_state(
        _turn("I ready my sword and shield.", 2),
        player_input="I ready my sword and shield.",
        turn_index=2,
        previous_bundle=first["interactive_cli_state_bundle"],
    )
    third = enrich_live_interactive_turn_with_state(
        _turn("I leave the tavern and take the road north.", 3),
        player_input="I leave the tavern and take the road north.",
        turn_index=3,
        previous_bundle=second["interactive_cli_state_bundle"],
    )

    bundle = third["interactive_cli_state_bundle"]
    assert third["interactive_cli_live_state"]["patch"] == LIVE_INTERACTIVE_STATE_PATCH
    assert bundle["states"]["memory"]["facts"]["trail_name"] == "Ash Lantern"
    assert bundle["states"]["equipment"]["readied_items"] == ["sword", "shield"]
    assert bundle["states"]["travel"]["current_location_id"] == "location:road-north"
    assert third["interactive_cli_state_checkpoint"]["bundle"] == bundle


def test_phase13_71_live_state_hook_mutates_turn_and_saves_checkpoints(tmp_path: Path) -> None:
    hook = make_live_interactive_state_hook(checkpoint_dir=tmp_path / "checkpoints")

    first = _turn("Bran, remember this: my trail name is Ash Lantern.", 1)
    hook(turn_summary=first, turn_index=1, player_input=first["player_input"], session_id="test-session")
    second = _turn("I sell one ration to Bran for copper.", 2)
    hook(turn_summary=second, turn_index=2, player_input=second["player_input"], session_id="test-session")

    assert first["interactive_cli_state_bundle"]["states"]["memory"]["facts"]["trail_name"] == "Ash Lantern"
    bundle = second["interactive_cli_state_bundle"]
    assert bundle["states"]["memory"]["facts"]["trail_name"] == "Ash Lantern"
    assert len(bundle["states"]["commerce"]["attempted_sells"]) == 1
    assert bundle["states"]["commerce"]["inventory_mutated"] is False

    checkpoint_files = sorted((tmp_path / "checkpoints").glob("*.json"))
    assert [path.name for path in checkpoint_files] == [
        "turn-0001-interactive-cli-state-checkpoint.json",
        "turn-0002-interactive-cli-state-checkpoint.json",
    ]
    restored = restore_interactive_cli_state_bundle_from_checkpoint_file(checkpoint_files[-1])
    assert restored == bundle

    raw_payload = json.loads(checkpoint_files[-1].read_text(encoding="utf-8"))
    assert raw_payload["bundle_checksum"] == second["interactive_cli_state_checkpoint"]["bundle_checksum"]
