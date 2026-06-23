"""Compatibility wrapper for inline feature jobs.

This package wrapper preserves the existing ``inline_feature_jobs.py`` module
while patching the RPG visible-text projection to evaluate structured
narration against the merged command/restatement context.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_SOURCE_PATH = Path(__file__).resolve().parent.parent / "inline_feature_jobs.py"
_SOURCE_NAME = "app.jobs._inline_feature_jobs_source"

_spec = importlib.util.spec_from_file_location(_SOURCE_NAME, _SOURCE_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - import safety
    raise ImportError(f"Could not load inline feature job source: {_SOURCE_PATH}")
_source = importlib.util.module_from_spec(_spec)
sys.modules[_SOURCE_NAME] = _source
_spec.loader.exec_module(_source)


def _format_rpg_turn_narration(
    source: dict[str, Any],
    restatement_source: dict[str, Any] | None = None,
) -> str | None:
    narration_json = _source._dict_value(source.get("narration_json"))
    if not narration_json:
        return None

    narration = _source._text(narration_json.get("narration"))
    npc = _source._dict_value(narration_json.get("npc")) or _source._dict_value(source.get("npc"))
    speaker = _source._text(npc.get("speaker")) or _source._text(npc.get("name")) or "NPC"
    line = _source._text(npc.get("line")) or _source._text(npc.get("text"))
    if _source._is_non_npc_speaker(speaker):
        speaker = ""
        line = ""

    restatement_context = _source._rpg_turn_restatement_source(source, restatement_source or {})
    if _source._is_player_restatement(line, restatement_context) or _source._is_player_restatement(
        narration,
        restatement_context,
    ):
        return None

    parts = [narration] if narration else []
    if line and speaker:
        parts.append(f'{speaker}: "{_source._normalize_dialogue_quotes(line)}"')
    elif line:
        parts.append(f'NPC: "{_source._normalize_dialogue_quotes(line)}"')
    return "\n\n".join(parts) or None


def _rpg_turn_visible_text(result: dict[str, Any]) -> str | None:
    nested = _source._dict_value(result.get("result"))
    authoritative = _source._dict_value(result.get("authoritative"))
    turn_contract = _source._dict_value(result.get("turn_contract"))
    narration_brief = _source._dict_value(turn_contract.get("narration_brief"))
    restatement_source = _source._rpg_turn_restatement_source(result, nested, authoritative, turn_contract)

    for source in (result, nested, authoritative):
        structured = _format_rpg_turn_narration(source, restatement_source)
        if structured:
            return structured

    for value, source in (
        (nested.get("narration"), nested),
        (authoritative.get("narration"), authoritative),
        (authoritative.get("deterministic_fallback_narration"), authoritative),
        (narration_brief.get("summary"), turn_contract),
    ):
        visible = _source._text(value)
        if visible and not _source._is_player_restatement(
            visible,
            _source._rpg_turn_restatement_source(source, restatement_source),
        ):
            return visible
    return None


_source._format_rpg_turn_narration = _format_rpg_turn_narration
_source._rpg_turn_visible_text = _rpg_turn_visible_text

for _name, _value in vars(_source).items():
    if _name.startswith("__") and _name != "__all__":
        continue
    globals()[_name] = _value

__all__ = [name for name in globals() if not name.startswith("__")]
