"""Checkpoint helpers for interactive CLI state bundles.

This layer is intentionally pure and deterministic. It does not write durable save
files yet; it creates a stable snapshot envelope around an existing
``interactive_cli_state_bundle`` so later save/load phases can persist and replay
one validated payload.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

INTERACTIVE_CLI_STATE_CHECKPOINT_VERSION = "interactive_cli_state_checkpoint_v1"
INTERACTIVE_CLI_STATE_CHECKPOINT_PATCH = "phase_13_66_interactive_state_checkpoint_v1"
INTERACTIVE_CLI_STATE_CHECKPOINT_SOURCE = "interactive_cli_state_checkpoint"


class InteractiveCliStateCheckpointError(ValueError):
    """Raised when an interactive CLI state checkpoint cannot be restored."""


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def interactive_cli_state_bundle_checksum(bundle: Mapping[str, Any]) -> str:
    """Return a deterministic checksum for a state bundle payload."""

    canonical = _canonical_json(_safe_dict(bundle))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_interactive_cli_state_checkpoint(
    bundle: Mapping[str, Any],
    *,
    checkpoint_id: str | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    """Wrap a state bundle in a deterministic checkpoint envelope."""

    bundle_copy = deepcopy(_safe_dict(bundle))
    bundle_turn_index = bundle_copy.get("turn_index")
    resolved_turn_index = int(turn_index if turn_index is not None else bundle_turn_index or 0)
    resolved_checkpoint_id = _safe_str(checkpoint_id or f"interactive-cli-turn-{resolved_turn_index}")
    return {
        "version": INTERACTIVE_CLI_STATE_CHECKPOINT_VERSION,
        "patch": INTERACTIVE_CLI_STATE_CHECKPOINT_PATCH,
        "source": INTERACTIVE_CLI_STATE_CHECKPOINT_SOURCE,
        "checkpoint_id": resolved_checkpoint_id,
        "turn_index": resolved_turn_index,
        "bundle_checksum": interactive_cli_state_bundle_checksum(bundle_copy),
        "bundle": bundle_copy,
        "state_versions": deepcopy(_safe_dict(bundle_copy.get("state_versions"))),
    }


def restore_interactive_cli_state_bundle_from_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    verify_checksum: bool = True,
) -> dict[str, Any]:
    """Restore and verify the bundle stored in a checkpoint envelope."""

    checkpoint_dict = _safe_dict(checkpoint)
    if checkpoint_dict.get("version") != INTERACTIVE_CLI_STATE_CHECKPOINT_VERSION:
        raise InteractiveCliStateCheckpointError("unsupported interactive CLI state checkpoint version")
    bundle = deepcopy(_safe_dict(checkpoint_dict.get("bundle")))
    if not bundle:
        raise InteractiveCliStateCheckpointError("interactive CLI state checkpoint is missing a bundle")
    if verify_checksum:
        expected = _safe_str(checkpoint_dict.get("bundle_checksum"))
        actual = interactive_cli_state_bundle_checksum(bundle)
        if not expected or expected != actual:
            raise InteractiveCliStateCheckpointError("interactive CLI state checkpoint checksum mismatch")
    return bundle


def attach_interactive_cli_state_checkpoint_to_turn(turn: Mapping[str, Any]) -> dict[str, Any]:
    """Return a turn copy with a checkpoint for its existing state bundle."""

    out = deepcopy(_safe_dict(turn))
    bundle = _safe_dict(out.get("interactive_cli_state_bundle"))
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    if not bundle:
        bundle = _safe_dict(raw_result.get("interactive_cli_state_bundle"))
    if not bundle:
        return out
    checkpoint = create_interactive_cli_state_checkpoint(
        bundle,
        checkpoint_id=f"interactive-cli-turn-{int(out.get('turn_index') or bundle.get('turn_index') or 0)}",
        turn_index=int(out.get("turn_index") or bundle.get("turn_index") or 0),
    )
    out["interactive_cli_state_checkpoint"] = checkpoint
    out["interactive_cli_state_checkpoint_patch"] = INTERACTIVE_CLI_STATE_CHECKPOINT_PATCH
    raw_result["interactive_cli_state_checkpoint"] = checkpoint
    raw_result["interactive_cli_state_checkpoint_patch"] = INTERACTIVE_CLI_STATE_CHECKPOINT_PATCH
    out["raw_result"] = raw_result
    out["result"] = raw_result
    return out


def apply_interactive_cli_state_checkpoints_to_matrix_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Attach checkpoints to all turns that already carry state bundles."""

    result_dict = _safe_dict(result)
    changed = 0
    scenarios: list[dict[str, Any]] = []
    for item in result_dict.get("results") or []:
        if not isinstance(item, dict):
            continue
        scenario = item.get("scenario")
        scenario_id = _safe_str(getattr(scenario, "scenario_id", "") or _safe_dict(scenario).get("scenario_id"))
        scenario_result = _safe_dict(item.get("result"))
        turns = []
        scenario_changed = 0
        for turn in scenario_result.get("turns") or []:
            turn_dict = _safe_dict(turn)
            checkpointed = attach_interactive_cli_state_checkpoint_to_turn(turn_dict)
            turns.append(checkpointed)
            if checkpointed.get("interactive_cli_state_checkpoint"):
                scenario_changed += 1
        if scenario_result.get("turns") is not None:
            scenario_result["turns"] = turns
            item["result"] = scenario_result
        changed += scenario_changed
        scenarios.append({"scenario_id": scenario_id, "changed_turns": scenario_changed})
    summary = result_dict.get("summary")
    if isinstance(summary, dict):
        summary["interactive_cli_state_checkpoint"] = {
            "ok": True,
            "source": INTERACTIVE_CLI_STATE_CHECKPOINT_SOURCE,
            "patch": INTERACTIVE_CLI_STATE_CHECKPOINT_PATCH,
            "changed_turns": changed,
            "scenarios": scenarios,
        }
    return {
        "ok": True,
        "source": INTERACTIVE_CLI_STATE_CHECKPOINT_SOURCE,
        "patch": INTERACTIVE_CLI_STATE_CHECKPOINT_PATCH,
        "changed_turns": changed,
        "scenarios": scenarios,
    }
