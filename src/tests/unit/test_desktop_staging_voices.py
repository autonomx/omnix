"""The installer's voice library: the default reference voice and the designed voices it ships, nothing else."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def stage():
    spec = importlib.util.spec_from_file_location("desktop_stage", REPO / "desktop" / "staging" / "stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_installer_ships_only_the_default_reference_and_the_designed_voices(stage, tmp_path: Path) -> None:
    clones = tmp_path / "resources" / "voice_clones"
    clones.mkdir(parents=True)
    (clones / "voice_clones.json").write_text(json.dumps({
        "default_ref": {"voice_clone_id": "default_ref"}, "Maya": {"voice_clone_id": "Maya", "gender": "neutral"},
        "Someone": {"voice_clone_id": "Someone"},
    }), encoding="utf-8")
    designed = tmp_path / "resources" / "assistant"
    designed.mkdir()
    (designed / "Maya.wav").write_bytes(b"designed")
    (designed / "Maya.json").write_text('{"voice_id": "Maya"}', encoding="utf-8")

    stage.stage_voice_library(tmp_path / "app", root=tmp_path)

    staged = tmp_path / "app" / "resources" / "voice_clones"
    index = json.loads((staged / "voice_clones.json").read_text(encoding="utf-8"))
    assert sorted(index) == ["Maya", "default_ref"] and index["Maya"]["gender"] == "female"
    assert (staged / "Maya.wav").read_bytes() == b"designed"
    assert stage._not_distributed("resources/voice_clones/Maya.wav")
    assert not stage._not_distributed("resources/assistant/Maya.wav")


def test_a_shipped_voice_missing_its_files_stops_the_build(stage, tmp_path: Path) -> None:
    with pytest.raises(stage.StageError, match="Maya"):
        stage.stage_voice_library(tmp_path / "app", root=tmp_path)


def test_the_repository_holds_every_shipped_voice(stage) -> None:
    for name, (folder, _entry) in stage.SHIPPED_VOICES.items():
        sidecar = json.loads((REPO / folder / f"{name}.json").read_text(encoding="utf-8"))
        assert (REPO / folder / f"{name}.wav").is_file() and sidecar["voice_id"] == name and sidecar["ref_text"]
