from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from tests.rpg.autoplay.progress import state_digest
from tests.rpg.autoplay.manual_turn_driver import (
    load_autoplay_manual_session,
    load_autoplay_simulation_state,
    prepare_autoplay_manual_session,
)


DEFAULT_MAX_STATE_BYTES = 2_000_000
DEFAULT_MAX_ROOT_COUNT = 80
DEFAULT_MAX_LIST_LENGTH = 500
DEFAULT_MAX_DICT_KEYS = 500


AUTHORITATIVE_ROOTS_TO_VALIDATE = [
    "scene",
    "location",
    "runtime",
    "story_arc_state",
    "story_arc_milestone_state",
    "quest_log_state",
    "campaign_journal_state",
    "story_event_queue_state",
    "story_pack_state",
    "campaign_director_state",
    "lore_state",
    "npc_evolution_state",
    "npc_profile_state",
    "npc_progression_state",
    "player_state",
    "social_state",
    "combat_state",
    "memory_state",
    "autoplay_story_hook_state",
]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def stable_json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))


def collect_state_bounds(
    simulation_state: Dict[str, Any],
    *,
    max_state_bytes: int = DEFAULT_MAX_STATE_BYTES,
    max_root_count: int = DEFAULT_MAX_ROOT_COUNT,
    max_list_length: int = DEFAULT_MAX_LIST_LENGTH,
    max_dict_keys: int = DEFAULT_MAX_DICT_KEYS,
) -> Dict[str, Any]:
    state = _safe_dict(simulation_state)
    warnings: List[str] = []
    root_names = sorted(state.keys())
    state_size = stable_json_size(state)

    if state_size > max_state_bytes:
        warnings.append("state_size_limit_exceeded")
    if len(root_names) > max_root_count:
        warnings.append("root_count_limit_exceeded")

    large_lists = []
    large_dicts = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, list):
            if len(value) > max_list_length:
                large_lists.append({"path": path, "length": len(value)})
            for index, item in enumerate(value[:max_list_length + 1]):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, dict):
            if len(value) > max_dict_keys:
                large_dicts.append({"path": path, "keys": len(value)})
            for key, item in list(value.items())[:max_dict_keys + 1]:
                walk(item, f"{path}.{key}" if path else str(key))

    walk(state, "")

    if large_lists:
        warnings.append("large_list_limit_exceeded")
    if large_dicts:
        warnings.append("large_dict_limit_exceeded")

    return {
        "ok": not warnings,
        "warnings": warnings,
        "state_size_bytes": state_size,
        "root_count": len(root_names),
        "root_names": root_names,
        "large_lists": large_lists[:25],
        "large_dicts": large_dicts[:25],
        "limits": {
            "max_state_bytes": max_state_bytes,
            "max_root_count": max_root_count,
            "max_list_length": max_list_length,
            "max_dict_keys": max_dict_keys,
        },
        "digest": state_digest(state),
    }


def _root_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    return {
        key: deepcopy(state.get(key))
        for key in AUTHORITATIVE_ROOTS_TO_VALIDATE
        if key in state
    }


def compare_authoritative_roots(
    before_state: Dict[str, Any],
    after_state: Dict[str, Any],
) -> Dict[str, Any]:
    before = _root_snapshot(before_state)
    after = _root_snapshot(after_state)
    missing_roots = sorted([key for key in before if key not in after])
    changed_roots = sorted(
        [
            key
            for key in before
            if key in after and before.get(key) != after.get(key)
        ]
    )
    return {
        "ok": not missing_roots and not changed_roots,
        "missing_roots": missing_roots,
        "changed_roots": changed_roots,
        "before_root_names": sorted(before.keys()),
        "after_root_names": sorted(after.keys()),
    }


def write_checkpoint_file(
    *,
    checkpoint_dir: Path,
    session_id: str,
    turn_index: int,
    simulation_state: Dict[str, Any],
) -> Dict[str, Any]:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    path = checkpoint_dir / f"{session_id}_turn_{int(turn_index):04d}.json"
    payload = {
        "format_version": "autoplay_checkpoint_v1",
        "session_id": session_id,
        "turn_index": int(turn_index),
        "simulation_state": simulation_state,
        "digest": state_digest(simulation_state),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "path": str(path),
        "digest": payload["digest"],
        "state_size_bytes": stable_json_size(simulation_state),
    }


def load_checkpoint_file(path: str | Path) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _safe_dict(payload)


def validate_save_load_checkpoint(
    *,
    session_id: str,
    turn_index: int,
    checkpoint_dir: Path,
    simulation_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Write checkpoint, reload it through manual session setup, compare roots."""
    before_state = deepcopy(_safe_dict(simulation_state))
    before_digest = state_digest(before_state)
    checkpoint = write_checkpoint_file(
        checkpoint_dir=checkpoint_dir,
        session_id=session_id,
        turn_index=turn_index,
        simulation_state=before_state,
    )
    loaded = load_checkpoint_file(checkpoint["path"])
    loaded_state = _safe_dict(loaded.get("simulation_state"))
    loaded_digest = state_digest(loaded_state)

    # Rehydrate the manual harness session using the loaded checkpoint state.
    prepare_autoplay_manual_session(
        session_id=session_id,
        simulation_state=loaded_state,
        reset_session_state=False,
    )
    reloaded_state = load_autoplay_simulation_state(session_id)
    reloaded_digest = state_digest(reloaded_state)

    root_compare = compare_authoritative_roots(before_state, reloaded_state)
    ok = (
        before_digest["hash"] == loaded_digest["hash"]
        and loaded_digest["hash"] == reloaded_digest["hash"]
        and root_compare.get("ok") is True
    )
    return {
        "ok": ok,
        "turn_index": int(turn_index),
        "checkpoint": checkpoint,
        "before_digest": before_digest,
        "loaded_digest": loaded_digest,
        "reloaded_digest": reloaded_digest,
        "root_compare": root_compare,
        "session_root_count_after_reload": len(_safe_dict(load_autoplay_manual_session(session_id).get("simulation_state"))),
    }