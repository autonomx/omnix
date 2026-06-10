from __future__ import annotations

import json

import pytest

from app.rpg.interactive_cli_state_bundle import apply_interactive_cli_state_bundle_to_matrix_result
from app.rpg.interactive_cli_state_checkpoint import (
    InteractiveCliStateCheckpointError,
    create_interactive_cli_state_checkpoint,
    deserialize_interactive_cli_state_checkpoint,
    interactive_cli_state_bundle_checksum,
    load_interactive_cli_state_checkpoint_file,
    restore_interactive_cli_state_bundle_from_checkpoint_file,
    save_interactive_cli_state_checkpoint_file,
    serialize_interactive_cli_state_checkpoint,
)
from tests.rpg.test_ci_phase13_62_feature_state_regression import (
    _apply_all_feature_state_cleanups,
    _result_for,
    _state_matrix_result,
)


def _checkpoint_for_scenario(scenario_id: str) -> dict:
    result = _apply_all_feature_state_cleanups(_state_matrix_result())
    apply_interactive_cli_state_bundle_to_matrix_result(result)
    bundle = _result_for(result, scenario_id)["turns"][-1]["interactive_cli_state_bundle"]
    return create_interactive_cli_state_checkpoint(bundle, checkpoint_id=f"{scenario_id}-final")


def test_phase13_68_checkpoint_serializes_to_stable_json() -> None:
    checkpoint = _checkpoint_for_scenario("equipment_inventory_probe")

    serialized = serialize_interactive_cli_state_checkpoint(checkpoint)
    restored_checkpoint = deserialize_interactive_cli_state_checkpoint(serialized)

    assert serialized.endswith("\n")
    assert restored_checkpoint == checkpoint
    assert restored_checkpoint["bundle_checksum"] == interactive_cli_state_bundle_checksum(
        restored_checkpoint["bundle"]
    )
    assert restored_checkpoint["bundle"]["states"]["equipment"]["readied_items"] == ["sword", "shield"]


def test_phase13_68_checkpoint_saves_loads_and_restores_bundle(tmp_path) -> None:
    checkpoint = _checkpoint_for_scenario("npc_memory_recall_probe")
    save_path = tmp_path / "rpg_sessions" / "interactive-checkpoint.json"

    written_path = save_interactive_cli_state_checkpoint_file(checkpoint, save_path)
    loaded_checkpoint = load_interactive_cli_state_checkpoint_file(written_path)
    restored_bundle = restore_interactive_cli_state_bundle_from_checkpoint_file(written_path)

    assert written_path == save_path
    assert loaded_checkpoint == checkpoint
    assert restored_bundle == checkpoint["bundle"]
    assert restored_bundle["states"]["memory"]["facts"]["trail_name"] == "Ash Lantern"
    assert restored_bundle["states"]["memory"]["remembered_by"]["trail_name"] == "Bran"


def test_phase13_68_durable_checkpoint_rejects_tampered_file(tmp_path) -> None:
    checkpoint = _checkpoint_for_scenario("shop_sell_attempt")
    save_path = tmp_path / "interactive-checkpoint.json"
    save_interactive_cli_state_checkpoint_file(checkpoint, save_path)

    tampered = json.loads(save_path.read_text(encoding="utf-8"))
    tampered["bundle"]["states"]["commerce"]["inventory_mutated"] = True
    save_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")

    with pytest.raises(InteractiveCliStateCheckpointError, match="checksum mismatch"):
        load_interactive_cli_state_checkpoint_file(save_path)


def test_phase13_68_durable_checkpoint_rejects_invalid_json(tmp_path) -> None:
    save_path = tmp_path / "bad-checkpoint.json"
    save_path.write_text("not valid json", encoding="utf-8")

    with pytest.raises(InteractiveCliStateCheckpointError, match="invalid .* JSON"):
        load_interactive_cli_state_checkpoint_file(save_path)
