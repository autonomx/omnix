from __future__ import annotations

import pytest

from app.rpg.interactive_cli_state_bundle import apply_interactive_cli_state_bundle_to_matrix_result
from app.rpg.interactive_cli_state_checkpoint import (
    INTERACTIVE_CLI_STATE_CHECKPOINT_PATCH,
    InteractiveCliStateCheckpointError,
    apply_interactive_cli_state_checkpoints_to_matrix_result,
    create_interactive_cli_state_checkpoint,
    interactive_cli_state_bundle_checksum,
    restore_interactive_cli_state_bundle_from_checkpoint,
)
from tests.rpg.test_ci_phase13_62_feature_state_regression import (
    _apply_all_feature_state_cleanups,
    _result_for,
    _state_matrix_result,
)


def test_phase13_66_checkpoint_restores_interactive_state_bundle() -> None:
    result = _apply_all_feature_state_cleanups(_state_matrix_result())
    apply_interactive_cli_state_bundle_to_matrix_result(result)

    turn = _result_for(result, "equipment_inventory_probe")["turns"][-1]
    bundle = turn["interactive_cli_state_bundle"]
    checkpoint = create_interactive_cli_state_checkpoint(bundle, checkpoint_id="equipment-final")

    assert checkpoint["patch"] == INTERACTIVE_CLI_STATE_CHECKPOINT_PATCH
    assert checkpoint["bundle_checksum"] == interactive_cli_state_bundle_checksum(bundle)
    restored = restore_interactive_cli_state_bundle_from_checkpoint(checkpoint)
    assert restored == bundle
    assert restored["states"]["equipment"]["readied_items"] == ["sword", "shield"]


def test_phase13_66_checkpoint_rejects_tampered_bundle() -> None:
    result = _apply_all_feature_state_cleanups(_state_matrix_result())
    apply_interactive_cli_state_bundle_to_matrix_result(result)
    bundle = _result_for(result, "npc_memory_recall_probe")["turns"][-1]["interactive_cli_state_bundle"]
    checkpoint = create_interactive_cli_state_checkpoint(bundle, checkpoint_id="memory-final")

    checkpoint["bundle"]["states"]["memory"]["facts"]["trail_name"] = "Wrong Name"

    with pytest.raises(InteractiveCliStateCheckpointError, match="checksum mismatch"):
        restore_interactive_cli_state_bundle_from_checkpoint(checkpoint)


def test_phase13_66_feature_matrix_turns_receive_checkpoints() -> None:
    result = _apply_all_feature_state_cleanups(_state_matrix_result())
    apply_interactive_cli_state_bundle_to_matrix_result(result)

    checkpoint_cleanup = apply_interactive_cli_state_checkpoints_to_matrix_result(result)

    assert checkpoint_cleanup["ok"] is True
    assert checkpoint_cleanup["patch"] == INTERACTIVE_CLI_STATE_CHECKPOINT_PATCH
    assert checkpoint_cleanup["changed_turns"] == 12
    assert result["summary"]["interactive_cli_state_checkpoint"]["changed_turns"] == 12

    turn = _result_for(result, "shop_sell_attempt")["turns"][-1]
    checkpoint = turn["interactive_cli_state_checkpoint"]
    raw_checkpoint = turn["raw_result"]["interactive_cli_state_checkpoint"]
    assert checkpoint == raw_checkpoint
    restored = restore_interactive_cli_state_bundle_from_checkpoint(checkpoint)
    assert len(restored["states"]["commerce"]["attempted_sells"]) == 3
    assert restored["states"]["commerce"]["inventory_mutated"] is False
