"""Launcher interpreters come from settings, not a developer's home directory (WP-11.4)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.composition.launcher.config import load_launcher_config

ROOT = Path(__file__).resolve().parents[4]


def _python_in(env_dir: Path) -> str:
    return str(env_dir / "python.exe" if os.name == "nt" else env_dir / "bin" / "python")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in ("RPG_FLUX_PYTHON", "RPG_TTS_PYTHON", "RPG_STT_PYTHON", "CONDA_ROOT"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_use_the_named_conda_environments_under_the_home_directory(tmp_path):
    config = load_launcher_config(tmp_path)
    assert config.python("app") == _python_in(Path.home() / "miniconda3" / "envs" / "rpg-flux")
    assert config.python("stt") == _python_in(Path.home() / "miniconda3" / "envs" / "rpg-stt")


def test_the_file_sets_the_conda_root_environments_and_explicit_paths(tmp_path):
    settings = tmp_path / "resources" / "config" / "launcher.toml"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '[python]\nconda_root = "D:/conda"\n'
        '[python.environments]\ntts = "omnix-tts"\n'
        '[python.paths]\nstt = "E:/stt/python.exe"\n',
        encoding="utf-8",
    )
    config = load_launcher_config(tmp_path)
    assert config.python("tts") == _python_in(Path("D:/conda") / "envs" / "omnix-tts")
    assert config.python("app") == _python_in(Path("D:/conda") / "envs" / "rpg-flux")
    assert config.python("stt") == "E:/stt/python.exe"


def test_environment_variables_win(tmp_path, monkeypatch):
    monkeypatch.setenv("RPG_TTS_PYTHON", "/opt/tts/bin/python")
    monkeypatch.setenv("CONDA_ROOT", "/opt/conda")
    config = load_launcher_config(tmp_path)
    assert config.python("tts") == "/opt/tts/bin/python"
    assert config.python("app") == _python_in(Path("/opt/conda") / "envs" / "rpg-flux")


def test_the_committed_template_parses_to_the_defaults():
    template = (ROOT / "resources/config/launcher.example.toml").read_text(encoding="utf-8")
    import tomllib

    assert tomllib.loads(template)["python"]["environments"] == {"app": "rpg-flux", "tts": "rpg-tts", "stt": "rpg-stt"}


def test_no_launcher_source_names_a_developer_home_directory():
    for path in (ROOT / "src/app/composition/launcher").glob("*.py"):
        assert "unx47" not in path.read_text(encoding="utf-8"), path
