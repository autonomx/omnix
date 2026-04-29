from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return the Omnix repository root.

    This file lives at:
      <repo>/src/app/runtime_paths.py

    parents:
      0 runtime_paths.py
      1 app
      2 src
      3 repo root
    """
    return Path(__file__).resolve().parents[2]


def resources_root() -> Path:
    return repo_root() / "resources"


def resources_data_root() -> Path:
    path = resources_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resources_models_root() -> Path:
    path = resources_root() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def rpg_npc_profiles_root() -> Path:
    path = resources_data_root() / "rpg_npc_profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def generated_images_root() -> Path:
    path = resources_data_root() / "generated_images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def rpg_sessions_root() -> Path:
    path = resources_data_root() / "rpg_sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_results_root() -> Path:
    path = resources_data_root() / "test-results"
    path.mkdir(parents=True, exist_ok=True)
    return path