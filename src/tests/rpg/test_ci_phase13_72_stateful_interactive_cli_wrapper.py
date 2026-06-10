from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from app.rpg.interactive_cli_state_checkpoint import create_interactive_cli_state_checkpoint, save_interactive_cli_state_checkpoint_file
from tests.rpg import interactive_cli_campaign_state as state_cli


def test_phase13_72_default_checkpoint_dir_is_under_output_dir(tmp_path: Path) -> None:
    assert state_cli.default_checkpoint_dir(tmp_path) == tmp_path / "interactive-state-checkpoints"


def test_phase13_72_manifest_is_deterministic(tmp_path: Path) -> None:
    checkpoint_dir = state_cli.default_checkpoint_dir(tmp_path)
    checkpoint_dir.mkdir(parents=True)
    first = checkpoint_dir / "turn-0001-interactive-cli-state-checkpoint.json"
    second = checkpoint_dir / "turn-0002-interactive-cli-state-checkpoint.json"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    manifest_path = state_cli.write_checkpoint_manifest(output_dir=tmp_path, checkpoint_paths=[first, second])

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload == {
        "format_version": state_cli.STATEFUL_INTERACTIVE_CLI_VERSION,
        "checkpoint_count": 2,
        "checkpoint_dir": str(checkpoint_dir),
        "checkpoints": [
            "turn-0001-interactive-cli-state-checkpoint.json",
            "turn-0002-interactive-cli-state-checkpoint.json",
        ],
    }


def _write_valid_checkpoint(path: Path, *, turn_index: int = 1) -> Path:
    bundle = {
        "format_version": "interactive_cli_state_bundle_v1",
        "turn_index": turn_index,
        "states": {"memory": {"facts": {"trail_name": "Ash Lantern"}}},
        "state_versions": {"memory": "test"},
    }
    checkpoint = create_interactive_cli_state_checkpoint(bundle, turn_index=turn_index)
    return save_interactive_cli_state_checkpoint_file(checkpoint, path)


def test_phase13_73_appends_state_checkpoint_artifacts_to_existing_zip(tmp_path: Path) -> None:
    checkpoint_dir = state_cli.default_checkpoint_dir(tmp_path)
    checkpoint_dir.mkdir(parents=True)
    checkpoint = _write_valid_checkpoint(checkpoint_dir / "turn-0001-interactive-cli-state-checkpoint.json")
    manifest_path = state_cli.write_checkpoint_manifest(output_dir=tmp_path, checkpoint_paths=[checkpoint])
    zip_path = tmp_path / "interactive-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("interactive-summary.json", "{}")

    written = state_cli.append_state_checkpoints_to_zip(
        zip_path=zip_path,
        manifest_path=manifest_path,
        checkpoint_paths=[checkpoint],
    )

    assert written == [
        state_cli.MANIFEST_FILENAME,
        f"{state_cli.ZIP_CHECKPOINT_DIRNAME}/turn-0001-interactive-cli-state-checkpoint.json",
    ]
    with zipfile.ZipFile(zip_path, "r") as archive:
        assert sorted(archive.namelist()) == sorted([
            "interactive-summary.json",
            state_cli.MANIFEST_FILENAME,
            f"{state_cli.ZIP_CHECKPOINT_DIRNAME}/turn-0001-interactive-cli-state-checkpoint.json",
        ])

    assert state_cli.append_state_checkpoints_to_zip(
        zip_path=zip_path,
        manifest_path=manifest_path,
        checkpoint_paths=[checkpoint],
    ) == []


def test_phase13_74_verifies_restorable_state_checkpoints_in_zip(tmp_path: Path) -> None:
    checkpoint_dir = state_cli.default_checkpoint_dir(tmp_path)
    checkpoint_dir.mkdir(parents=True)
    checkpoint = _write_valid_checkpoint(checkpoint_dir / "turn-0003-interactive-cli-state-checkpoint.json", turn_index=3)
    manifest_path = state_cli.write_checkpoint_manifest(output_dir=tmp_path, checkpoint_paths=[checkpoint])
    zip_path = tmp_path / "interactive-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("interactive-summary.json", "{}")
    state_cli.append_state_checkpoints_to_zip(zip_path=zip_path, manifest_path=manifest_path, checkpoint_paths=[checkpoint])

    verification = state_cli.verify_state_checkpoints_in_zip(zip_path)

    assert verification["ok"] is True
    assert verification["checkpoint_count"] == 1
    assert verification["checkpoint_entries"] == [
        f"{state_cli.ZIP_CHECKPOINT_DIRNAME}/turn-0003-interactive-cli-state-checkpoint.json"
    ]
    assert verification["restored_turns"] == [3]


def test_phase13_74_rejects_zip_missing_checkpoint_entry(tmp_path: Path) -> None:
    checkpoint_dir = state_cli.default_checkpoint_dir(tmp_path)
    checkpoint_dir.mkdir(parents=True)
    checkpoint = _write_valid_checkpoint(checkpoint_dir / "turn-0004-interactive-cli-state-checkpoint.json", turn_index=4)
    manifest_path = state_cli.write_checkpoint_manifest(output_dir=tmp_path, checkpoint_paths=[checkpoint])
    zip_path = tmp_path / "interactive-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(manifest_path, state_cli.MANIFEST_FILENAME)

    verification = state_cli.verify_state_checkpoints_in_zip(zip_path)

    assert verification["ok"] is False
    assert verification["error"] == "checkpoint_zip_entry_missing"
    assert verification["missing_entry"] == f"{state_cli.ZIP_CHECKPOINT_DIRNAME}/turn-0004-interactive-cli-state-checkpoint.json"


def test_phase13_72_stateful_wrapper_installs_hook_and_reports_checkpoints(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run_interactive_campaign(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = output_dir / "interactive-campaign-results.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("interactive-summary.json", "{}")
        turn_summary = {
            "turn_index": 1,
            "player_input": "Bran, remember this: my trail name is Ash Lantern.",
            "raw_result": {
                "narration": "Bran nods.",
                "npc": {"speaker": "Bran", "line": "Ash Lantern. Aye."},
            },
            "interactive_cli_intent_diagnostics": {
                "final_classification": {
                    "action_type": "dialogue",
                    "requested_terms": [],
                }
            },
        }
        kwargs["after_turn_hook"](
            session_id=kwargs["session_id"],
            turn_summary=turn_summary,
            turn_index=1,
            player_input=turn_summary["player_input"],
        )
        return {
            "summary": {"completed_turns": 1},
            "turns": [turn_summary],
            "artifacts": {"output_dir": str(output_dir), "zip_path": str(zip_path)},
        }

    monkeypatch.setattr(state_cli.cli, "run_interactive_campaign", fake_run_interactive_campaign)

    output_dir = tmp_path / "run"
    result = state_cli.run_stateful_interactive_campaign(
        turns=1,
        session_id="phase-13-72",
        output_dir=output_dir,
        scripted_commands=["Bran, remember this: my trail name is Ash Lantern."],
        console_llm=False,
    )

    assert callable(captured["after_turn_hook"])
    assert captured["output_dir"] == output_dir
    state_info = result["stateful_interactive_cli"]
    assert state_info["format_version"] == state_cli.STATEFUL_INTERACTIVE_CLI_VERSION
    assert state_info["checkpoint_count"] == 1
    assert Path(state_info["checkpoint_manifest_path"]).exists()
    assert len(result["interactive_cli_state_checkpoint_paths"]) == 1
    checkpoint_path = Path(result["interactive_cli_state_checkpoint_paths"][0])
    assert checkpoint_path.exists()

    checkpoint_payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint_payload["bundle"]["states"]["memory"]["facts"]["trail_name"] == "Ash Lantern"
    manifest = json.loads(Path(state_info["checkpoint_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["checkpoints"] == [checkpoint_path.name]
    assert state_info["checkpoint_zip_entries"] == [
        state_cli.MANIFEST_FILENAME,
        f"{state_cli.ZIP_CHECKPOINT_DIRNAME}/{checkpoint_path.name}",
    ]
    assert result["artifacts"]["state_checkpoint_zip_entries"] == state_info["checkpoint_zip_entries"]
    assert state_info["checkpoint_zip_verification"]["ok"] is True
    assert state_info["checkpoint_zip_verification"]["checkpoint_count"] == 1

    with zipfile.ZipFile(output_dir / "interactive-campaign-results.zip", "r") as archive:
        names = set(archive.namelist())
    assert state_cli.MANIFEST_FILENAME in names
    assert f"{state_cli.ZIP_CHECKPOINT_DIRNAME}/{checkpoint_path.name}" in names
