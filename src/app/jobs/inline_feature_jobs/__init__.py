"""Compatibility package for the legacy inline feature job module.

The implementation remains in ``inline_feature_jobs.py`` for import compatibility.
RPG visible text is supplied by the canonical presentation module before the
implementation symbols are exported.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from app.rpg.presentation.visible_response import visible_response_text

_SOURCE_PATH = Path(__file__).resolve().parent.parent / "inline_feature_jobs.py"
_SOURCE_NAME = "app.jobs._inline_feature_jobs_source"

_spec = importlib.util.spec_from_file_location(_SOURCE_NAME, _SOURCE_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - import safety
    raise ImportError(f"Could not load inline feature job source: {_SOURCE_PATH}")
_source = importlib.util.module_from_spec(_spec)
sys.modules[_SOURCE_NAME] = _source
_spec.loader.exec_module(_source)


def _canonical_rpg_turn_visible_text(result: dict[str, Any]) -> str | None:
    command = str(result.get("player_input") or "").strip()
    return visible_response_text(result, command)


_source._rpg_turn_visible_text = _canonical_rpg_turn_visible_text

for _name, _value in vars(_source).items():
    if _name.startswith("__") and _name != "__all__":
        continue
    globals()[_name] = _value

globals()["_rpg_turn_visible_text"] = _canonical_rpg_turn_visible_text
__all__ = [name for name in globals() if not name.startswith("__")]
