"""Adapters for attaching item coverage payloads to autoplay artifacts."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.rpg.session.item_autoplay_report import (
    build_item_autoplay_report_payload,
    build_item_autoplay_report_rows,
)

ITEM_AUTOPLAY_ADAPTER_SOURCE = "engine_item_autoplay_adapter_v1"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _normalize_runtime_item_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return an item-report-compatible state for live runtime/checkpoint shapes."""

    source = deepcopy(_safe_dict(state))
    if not source:
        return {}

    player = dict(_safe_dict(source.get("player")))
    player_state = _safe_dict(source.get("player_state"))
    inventory_state = _safe_dict(source.get("inventory_state")) or _safe_dict(player_state.get("inventory_state"))
    player_inventory = _safe_dict(player_state.get("inventory"))
    inventory = player_inventory or inventory_state
    items = _safe_list(player.get("inventory")) or _safe_list(inventory.get("items")) or _safe_list(inventory_state.get("items"))
    currency = _safe_dict(player.get("currency")) or _safe_dict(inventory.get("currency")) or _safe_dict(inventory_state.get("currency"))
    equipment = _safe_dict(player.get("equipment")) or _safe_dict(inventory.get("equipment")) or _safe_dict(player_state.get("equipment"))

    if items or currency or equipment:
        if items:
            player["inventory"] = items
        if currency:
            player["currency"] = currency
        if equipment:
            player["equipment"] = equipment
        source["player"] = player

    if "mechanics" not in source:
        source["mechanics"] = {}
    if not source.get("current_turn"):
        turn = source.get("turn_index") or source.get("turn") or source.get("current_turn") or source.get("turn_count")
        if turn is not None:
            source["current_turn"] = turn
    return source


def _has_item_state_shape(state: dict[str, Any]) -> bool:
    player = _safe_dict(state.get("player"))
    mechanics = _safe_dict(state.get("mechanics"))
    if _safe_list(player.get("inventory")):
        return True
    if any("item" in str(key).lower() for key in mechanics.keys()):
        return True
    if _safe_list(_safe_dict(state.get("inventory_state")).get("items")):
        return True
    runtime_inventory = _safe_dict(_safe_dict(state.get("player_state")).get("inventory"))
    if _safe_list(runtime_inventory.get("items")):
        return True
    return bool(state.get("crafting") or state.get("item_market") or state.get("equipment"))


def extract_item_autoplay_state(value: Any) -> dict[str, Any]:
    """Extract the most likely RPG state payload from a turn/session artifact."""

    payload = _safe_dict(value)
    direct_state = _safe_dict(payload.get("state"))
    if direct_state:
        return _normalize_runtime_item_state(direct_state)
    simulation_state = _safe_dict(payload.get("simulation_state"))
    if simulation_state:
        return _normalize_runtime_item_state(simulation_state)
    final_state = _safe_dict(payload.get("final_state"))
    if final_state:
        return _normalize_runtime_item_state(final_state)
    game = _safe_dict(payload.get("game"))
    if game:
        return _normalize_runtime_item_state(game)
    session = _safe_dict(payload.get("session"))
    session_state = _safe_dict(session.get("state"))
    if session_state:
        return _normalize_runtime_item_state(session_state)
    result = _safe_dict(payload.get("result") or payload.get("turn_result"))
    if result and result is not payload:
        return extract_item_autoplay_state(result)
    normalized = _normalize_runtime_item_state(payload)
    return normalized if _has_item_state_shape(normalized) else {}


def attach_item_autoplay_report(
    artifact: dict[str, Any],
    *,
    station: str | None = None,
    genre: str = "classic_fantasy",
    objective_limit: int = 8,
    scenario_limit: int = 8,
    recent_trace_limit: int = 8,
    target_key: str = "item_autoplay_report",
) -> dict[str, Any]:
    """Return a copy of an artifact with deterministic item coverage attached."""

    output = deepcopy(_safe_dict(artifact))
    state = extract_item_autoplay_state(output)
    if not state:
        output[target_key] = {
            "ok": False,
            "error": "item_autoplay_state_not_found",
            "mechanics_source": ITEM_AUTOPLAY_ADAPTER_SOURCE,
        }
        return output
    payload = build_item_autoplay_report_payload(
        state,
        station=station,
        genre=genre,
        objective_limit=objective_limit,
        scenario_limit=scenario_limit,
        recent_trace_limit=recent_trace_limit,
    )
    output[target_key] = payload
    output[f"{target_key}_rows"] = build_item_autoplay_report_rows(payload)
    output.setdefault("mechanics_sources", [])
    sources = _safe_list(output.get("mechanics_sources"))
    if ITEM_AUTOPLAY_ADAPTER_SOURCE not in sources:
        output["mechanics_sources"] = [*sources, ITEM_AUTOPLAY_ADAPTER_SOURCE]
    return output


def summarize_item_autoplay_reports(artifacts: list[dict[str, Any]], *, report_key: str = "item_autoplay_report") -> dict[str, Any]:
    """Summarize item report payloads across multiple autoplay artifacts."""

    reports = [_safe_dict(artifact.get(report_key)) for artifact in artifacts]
    valid_reports = [report for report in reports if report.get("ok") is True]
    summaries = [_safe_dict(report.get("summary")) for report in valid_reports]
    scores = [_safe_float(summary.get("coverage_score")) for summary in summaries]
    gap_count = sum(int(summary.get("coverage_gap_count") or 0) for summary in summaries)
    objective_count = sum(int(summary.get("objective_count") or 0) for summary in summaries)
    return {
        "ok": True,
        "artifact_count": len(artifacts),
        "report_count": len(valid_reports),
        "max_coverage_score": max(scores) if scores else 0,
        "min_coverage_score": min(scores) if scores else 0,
        "coverage_gap_count": gap_count,
        "objective_count": objective_count,
        "mechanics_source": ITEM_AUTOPLAY_ADAPTER_SOURCE,
    }
