"""Live interactive CLI state bundle/checkpoint hook helpers.

The interactive CLI campaign runner already exposes an ``after_turn_hook`` extension
point.  This module provides a deterministic hook for that live-runtime path so
interactive turns can carry the same state bundle/checkpoint envelope that the
feature-matrix wrapper already attaches to artifact turns.

This layer is intentionally presentation-safe: it records bounded short-session
state and checkpoint metadata, but it does not make narration text authoritative
simulation state.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from app.rpg.interactive_cli_commerce_state import (
    apply_sell_attempt,
    extract_commerce_state,
    is_sell_request,
    normalize_commerce_state,
)
from app.rpg.interactive_cli_equipment_state import (
    apply_ready_command,
    extract_equipment_state,
    normalize_equipment_state,
)
from app.rpg.interactive_cli_memory_state import (
    extract_trail_name,
    normalize_short_session_memory_state,
    remember_trail_name,
)
from app.rpg.interactive_cli_state_bundle import attach_interactive_cli_state_bundle_to_turn
from app.rpg.interactive_cli_state_checkpoint import (
    attach_interactive_cli_state_checkpoint_to_turn,
    save_interactive_cli_state_checkpoint_file,
)
from app.rpg.interactive_cli_travel_response_quality import _is_travel_command
from app.rpg.interactive_cli_travel_state import advance_travel_state, initial_travel_state

LIVE_INTERACTIVE_STATE_SOURCE = "interactive_cli_live_state"
LIVE_INTERACTIVE_STATE_PATCH = "phase_13_71_live_interactive_state_bundle_v1"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _previous_state(previous_bundle: Mapping[str, Any] | None, name: str) -> dict[str, Any]:
    return deepcopy(_safe_dict(_safe_dict(previous_bundle).get("states")).get(name) or {})


def _requested_terms(turn: Mapping[str, Any]) -> list[Any]:
    diagnostics = _safe_dict(turn.get("interactive_cli_intent_diagnostics"))
    final = _safe_dict(diagnostics.get("final_classification"))
    return _safe_list(final.get("requested_terms"))


def _attach_state(turn: Mapping[str, Any], key: str, state: Mapping[str, Any]) -> dict[str, Any]:
    out = deepcopy(_safe_dict(turn))
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    raw_result[f"interactive_cli_{key}_state"] = deepcopy(_safe_dict(state))
    out[f"interactive_cli_{key}_state"] = deepcopy(_safe_dict(state))
    out["raw_result"] = raw_result
    out["result"] = raw_result
    return out


def _ready_command_requested(player_input: str) -> bool:
    text = player_input.lower()
    return "ready" in text and ("sword" in text or "shield" in text or "gear" in text or "weapon" in text)


def enrich_live_interactive_turn_with_state(
    turn: Mapping[str, Any],
    *,
    player_input: str,
    turn_index: int,
    previous_bundle: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach carried bundle/checkpoint state to one live interactive turn.

    The helper advances only the small deterministic state foundations introduced
    for the interactive CLI path: equipment, memory, commerce, and travel/map. It
    then attaches the aggregate bundle and checksum-backed checkpoint envelope.
    """

    out = deepcopy(_safe_dict(turn))
    out["turn_index"] = int(out.get("turn_index") or turn_index or 0)
    out["player_input"] = _safe_str(out.get("player_input") or player_input)
    command = _safe_str(player_input or out.get("player_input"))

    travel_state = _previous_state(previous_bundle, "travel") or initial_travel_state()
    if _is_travel_command(command, out):
        travel_state = advance_travel_state(travel_state, command)
    out = _attach_state(out, "travel", travel_state)

    equipment_state = normalize_equipment_state(_previous_state(previous_bundle, "equipment") or extract_equipment_state(out))
    if _ready_command_requested(command):
        equipment_state = apply_ready_command(equipment_state)
    out = _attach_state(out, "equipment", equipment_state)

    memory_state = normalize_short_session_memory_state(_previous_state(previous_bundle, "memory"))
    trail_name = extract_trail_name(command)
    if trail_name:
        memory_state = remember_trail_name(memory_state, trail_name, npc_name="Bran")
    out = _attach_state(out, "memory", memory_state)

    commerce_state = normalize_commerce_state(_previous_state(previous_bundle, "commerce") or extract_commerce_state(out))
    if is_sell_request(command, _requested_terms(out)):
        commerce_state = apply_sell_attempt(commerce_state, player_input=command, turn_index=int(out.get("turn_index") or 0))
    out = _attach_state(out, "commerce", commerce_state)

    warnings = list(_safe_list(out.get("scenario_warnings")))
    warning = f"{LIVE_INTERACTIVE_STATE_SOURCE}:{LIVE_INTERACTIVE_STATE_PATCH}"
    if warning not in warnings:
        warnings.append(warning)
    out["scenario_warnings"] = warnings
    out["interactive_cli_live_state"] = {
        "ok": True,
        "source": LIVE_INTERACTIVE_STATE_SOURCE,
        "patch": LIVE_INTERACTIVE_STATE_PATCH,
        "turn_index": int(out.get("turn_index") or 0),
    }

    bundled = attach_interactive_cli_state_bundle_to_turn(out)
    return attach_interactive_cli_state_checkpoint_to_turn(bundled)


class LiveInteractiveStateHook:
    """Stateful hook object for ``run_interactive_campaign(after_turn_hook=...)``."""

    def __init__(self, *, checkpoint_dir: str | Path | None = None) -> None:
        self.previous_bundle: dict[str, Any] | None = None
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self.saved_checkpoint_paths: list[str] = []

    def __call__(self, *, turn_summary: dict[str, Any], turn_index: int, player_input: str, **_: Any) -> None:
        enriched = enrich_live_interactive_turn_with_state(
            turn_summary,
            player_input=player_input,
            turn_index=turn_index,
            previous_bundle=self.previous_bundle,
        )
        turn_summary.clear()
        turn_summary.update(enriched)
        self.previous_bundle = deepcopy(_safe_dict(enriched.get("interactive_cli_state_bundle")))

        checkpoint = _safe_dict(enriched.get("interactive_cli_state_checkpoint"))
        if self.checkpoint_dir is not None and checkpoint:
            path = self.checkpoint_dir / f"turn-{int(turn_index):04d}-interactive-cli-state-checkpoint.json"
            saved = save_interactive_cli_state_checkpoint_file(checkpoint, path)
            self.saved_checkpoint_paths.append(str(saved))


def make_live_interactive_state_hook(*, checkpoint_dir: str | Path | None = None) -> Callable[..., None]:
    """Create a carry-forward hook for the live interactive CLI campaign runner."""

    return LiveInteractiveStateHook(checkpoint_dir=checkpoint_dir)
