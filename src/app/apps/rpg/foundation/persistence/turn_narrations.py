"""What was narrated for each turn, kept outside the campaign document (RQ-1.4, roadmap §4.1).

The document's readers still find a turn's narration at ``runtime_state.narration_artifacts`` and
``narration_artifacts_by_turn``: persistence takes them out when it stores the document (into
``omnix_rpg_turn_narrations``) and puts the kept ones back when it loads it. A narration that finishes after its
turn committed is therefore no change to the document and no campaign revision.
"""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict

TURN_NARRATION_KEYS = ("narration_artifacts", "narration_artifacts_by_turn")


def split_turn_narrations(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """The document without its turns' narrations, and the narrations by turn id (kept outside it).

    A narration is in the document twice, in the list and by turn; the turn's entry wins.
    """
    runtime = document.get("runtime_state")
    if not isinstance(runtime, dict) or not any(key in runtime for key in TURN_NARRATION_KEYS):
        return document, {}
    narrations: dict[str, dict[str, Any]] = {}
    for artifact in runtime.get("narration_artifacts") or ():
        if isinstance(artifact, dict) and str(artifact.get("turn_id") or "").strip():
            narrations[str(artifact["turn_id"]).strip()] = artifact
    for turn_id, artifact in _safe_dict(runtime.get("narration_artifacts_by_turn")).items():
        if isinstance(artifact, dict) and str(turn_id).strip():
            narrations[str(turn_id).strip()] = artifact
    document["runtime_state"] = {key: value for key, value in runtime.items() if key not in TURN_NARRATION_KEYS}
    return document, narrations


def with_turn_narrations(document: dict[str, Any], narrations: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """The document as its readers expect it, with its kept turn narrations (oldest first) back in place."""
    if not narrations:
        return document
    runtime = _safe_dict(document.get("runtime_state"))
    kept = dict(narrations)
    by_turn = {**_safe_dict(runtime.get("narration_artifacts_by_turn")), **kept}
    listed = [artifact for artifact in runtime.get("narration_artifacts") or ()
              if isinstance(artifact, dict) and str(artifact.get("turn_id") or "").strip() not in kept]
    document["runtime_state"] = {**runtime, "narration_artifacts": [*listed, *(value for _, value in narrations)],
                                 "narration_artifacts_by_turn": by_turn}
    return document


__all__ = ["TURN_NARRATION_KEYS", "split_turn_narrations", "with_turn_narrations"]
