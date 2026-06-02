from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List

from app.rpg.session.package_bridge import package_to_session, session_to_package
from app.rpg.session.replay_checkpoint import build_session_checkpoint, compare_session_checkpoints
from app.rpg.session.replay_turn_sequence import validate_replay_turn_sequence

SOURCE = "deterministic_phase7_save_load_replay_roundtrip_gate"

SaveSession = Callable[[Dict[str, Any]], Dict[str, Any]]
LoadSession = Callable[[str], Dict[str, Any] | None]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _session_id(session: Dict[str, Any]) -> str:
    manifest = _safe_dict(session.get("manifest"))
    return _safe_str(manifest.get("session_id") or manifest.get("id") or "session:unknown")


def _default_save_session(session: Dict[str, Any]) -> Dict[str, Any]:
    from app.rpg.session.durable_store import save_session_to_disk

    return save_session_to_disk(session, compact=True)


def _default_load_session(session_id: str) -> Dict[str, Any] | None:
    from app.rpg.session.durable_store import load_session_from_disk

    return load_session_from_disk(session_id)


def _checkpoint(label: str, session: Dict[str, Any]) -> Dict[str, Any]:
    return build_session_checkpoint(session, label=label, turn_index=0)


def _compare(label: str, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    comparison = compare_session_checkpoints(before, after)
    return {"label": label, **comparison, "source": SOURCE}


def run_save_load_replay_persistence_roundtrip(
    session: Dict[str, Any],
    commands: List[Dict[str, Any]],
    *,
    save_session: SaveSession | None = None,
    load_session: LoadSession | None = None,
    label: str = "phase7.3",
) -> Dict[str, Any]:
    """Persist through package and durable-store paths, then replay from the loaded checkpoint."""
    session = deepcopy(_safe_dict(session))
    save_fn = save_session or _default_save_session
    load_fn = load_session or _default_load_session

    original_checkpoint = _checkpoint(f"{label}:original", session)

    package_payload = session_to_package(session)
    package_result = package_to_session(package_payload)
    if package_result.get("ok") is not True:
        return {"ok": False, "reason": "package_roundtrip_failed", "package_result": package_result, "source": SOURCE}
    package_session = _safe_dict(package_result.get("session"))
    package_checkpoint = _checkpoint(f"{label}:package", package_session)
    package_comparison = _compare("package_roundtrip", original_checkpoint, package_checkpoint)

    saved_session = save_fn(deepcopy(session))
    loaded_session = load_fn(_session_id(saved_session))
    if not isinstance(loaded_session, dict):
        return {"ok": False, "reason": "disk_roundtrip_missing_session", "source": SOURCE}
    disk_checkpoint = _checkpoint(f"{label}:disk", loaded_session)
    disk_comparison = _compare("disk_roundtrip", original_checkpoint, disk_checkpoint)

    replay_validation = validate_replay_turn_sequence(disk_checkpoint, _safe_list(commands), label=f"{label}:disk_replay")
    final_replay_checkpoint = _safe_dict(_safe_dict(replay_validation.get("first")).get("final_checkpoint"))
    expected_validation = validate_replay_turn_sequence(
        original_checkpoint,
        _safe_list(commands),
        expected_final_checkpoint=final_replay_checkpoint,
        label=f"{label}:original_replay",
    )

    comparisons = [package_comparison, disk_comparison]
    blockers = []
    for comparison in comparisons:
        if comparison.get("deterministic_match") is not True:
            blockers.append(
                {
                    "kind": f"{comparison.get('label')}_digest_drift",
                    "changed_sections": _safe_list(comparison.get("changed_sections")),
                    "before_digest": _safe_str(comparison.get("before_digest")),
                    "after_digest": _safe_str(comparison.get("after_digest")),
                    "source": SOURCE,
                }
            )
    if replay_validation.get("ok") is not True:
        blockers.append({"kind": "loaded_checkpoint_replay_failed", "source": SOURCE})
    if expected_validation.get("ok") is not True:
        blockers.append({"kind": "original_vs_loaded_replay_drift", "source": SOURCE})

    return {
        "ok": not blockers,
        "reason": "save_load_replay_persistence_roundtrip_validated" if not blockers else "save_load_replay_persistence_roundtrip_drift_detected",
        "session_id": _session_id(session),
        "original_checkpoint": original_checkpoint,
        "package_checkpoint": package_checkpoint,
        "disk_checkpoint": disk_checkpoint,
        "comparisons": comparisons,
        "replay_validation": replay_validation,
        "expected_validation": expected_validation,
        "blockers": blockers,
        "source": SOURCE,
    }


def build_save_load_replay_roundtrip_contract(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    return {
        "source": SOURCE,
        "allowed_roundtrip_claims": [
            f"Roundtrip result: {_safe_str(result.get('reason'))}",
            f"Session id: {_safe_str(result.get('session_id'))}",
            f"Blocker count: {len(_safe_list(result.get('blockers')))}",
        ],
        "forbidden_roundtrip_claims": [
            "Do not call providers or LLMs while saving, loading, restoring, or replaying deterministic checkpoints.",
            "Do not invent a new persistence layer when durable store or package bridge paths already cover the roundtrip.",
            "Do not ignore package, disk, checkpoint, or replay digest drift.",
            "Do not treat volatile timing/provider diagnostics as authoritative persistence state.",
        ],
    }


def assert_phase7_save_load_replay_roundtrip_ready() -> Dict[str, Any]:
    import tempfile

    from app.rpg.locations.discovery import discover_location, discover_route, unblock_route
    from app.rpg.session import durable_store

    session = {
        "manifest": {"id": "phase7:roundtrip", "session_id": "phase7:roundtrip", "title": "Phase 7.3 Roundtrip"},
        "installed_packs": ["base"],
        "simulation_state": {
            "player_state": {
                "inventory_state": {"items": [{"item_id": "ration", "qty": 2}, {"item_id": "water_skin", "qty": 3}]},
                "survival_state": {"hunger": 10, "thirst": 10},
                "currency": {"silver": 5},
            },
            "quest_state": {"active_quests": [{"quest_id": "quest:old_mill", "status": "active"}]},
        },
        "runtime_state": {"elapsed_ms": 999, "provider_latency_ms": 100},
    }
    state = _safe_dict(session["simulation_state"])
    discover_location(state, location_id="location:old_mill", reason="phase7_roundtrip_seed", turn_index=0)
    discover_route(state, edge_id="route:old_road:old_mill", reason="phase7_roundtrip_seed", turn_index=0)
    unblock_route(state, edge_id="route:old_road:old_mill", reason="phase7_roundtrip_seed", turn_index=0)
    commands = [
        {"type": "travel", "command_text": "go to the old road", "roll_encounter": False},
        {"type": "travel", "command_text": "go to the old mill", "roll_encounter": False},
    ]

    original_dir = durable_store._SESSION_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        durable_store._SESSION_DIR = durable_store.Path(tmpdir)
        try:
            result = run_save_load_replay_persistence_roundtrip(session, commands, label="phase7.3")
        finally:
            durable_store._SESSION_DIR = original_dir

    contract = build_save_load_replay_roundtrip_contract(result)
    blockers = list(_safe_list(result.get("blockers")))
    if result.get("ok") is not True:
        blockers.append({"kind": "roundtrip_not_validated", "source": SOURCE})
    if not contract.get("forbidden_roundtrip_claims"):
        blockers.append({"kind": "missing_roundtrip_guardrails", "source": SOURCE})
    return {
        "ok": not blockers,
        "reason": "phase7_save_load_replay_roundtrip_ready" if not blockers else "phase7_save_load_replay_roundtrip_not_ready",
        "result": result,
        "contract": contract,
        "blockers": blockers,
        "source": SOURCE,
    }
