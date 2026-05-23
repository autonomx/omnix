from __future__ import annotations

"""N125.1/N125.2 real survival metric source repair helpers.

The N123/N124 unit paths used idealized turn-contract rows, while real autoplay
artifacts can project survival state through several nested result/presentation
shapes.  This module normalizes those shapes, records source coverage, and
builds an advisory evidence gate so reports distinguish real-run evidence from
synthetic balance simulations.

N125.2 accepts either explicit turn-contract resource-change source evidence,
persisted authoritative climate state evidence, or compact final transcript rows
that carry both climate values and a real resource_changes payload.  It still
does not fabricate resource deltas, survival actions, suggestions, or relief
rows.
"""

from typing import Any, Dict, Iterable, List

SURVIVAL_METRIC_SOURCE_FORMAT = "n1251_survival_metric_source_summary_v1"
BALANCE_SUMMARY_SOURCE = "n1278_survival_relief_balance_tuning"


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _get_path(root: Dict[str, Any], path: Iterable[str]) -> Any:
    value: Any = root
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _first_dict(root: Dict[str, Any], paths: List[List[str]]) -> Dict[str, Any]:
    for path in paths:
        value = _get_path(root, path)
        if isinstance(value, dict) and value:
            return value
    return {}


def row_contract(row: Dict[str, Any]) -> Dict[str, Any]:
    row = safe_dict(row)
    return _first_dict(row, [
        ["turn_contract"],
        ["contract"],
        ["result", "turn_contract"],
        ["result", "contract"],
        ["authoritative_result", "turn_contract"],
        ["authoritative_result", "contract"],
        ["raw_result", "turn_contract"],
        ["raw_result", "contract"],
        ["turn", "turn_contract"],
    ])


def resolved_action(row: Dict[str, Any]) -> Dict[str, Any]:
    row = safe_dict(row)
    contract = row_contract(row)
    candidates = [
        row.get("resolved_action"),
        row.get("resolved_result"),
        contract.get("resolved_action"),
        contract.get("resolved_result"),
        _get_path(row, ["result", "resolved_action"]),
        _get_path(row, ["result", "resolved_result"]),
        _get_path(row, ["authoritative_result", "resolved_action"]),
        _get_path(row, ["raw_result", "resolved_action"]),
    ]
    for value in candidates:
        if isinstance(value, dict) and value:
            return value
    return {}


def climate_survival(row: Dict[str, Any]) -> Dict[str, Any]:
    row = safe_dict(row)
    contract = row_contract(row)
    resolved = resolved_action(row)
    result = safe_dict(row.get("result"))
    candidates = [
        row.get("climate_survival"),
        row.get("climate_survival_runtime_payload"),
        contract.get("climate_survival"),
        resolved.get("climate_survival"),
        result.get("climate_survival"),
        result.get("climate_survival_runtime_payload"),
        _get_path(result, ["presentation", "climate_survival"]),
        _get_path(result, ["runtime_promotion_panel", "climate_survival"]),
        _get_path(row, ["presentation", "climate_survival"]),
        _get_path(row, ["runtime_promotion_panel", "climate_survival"]),
        _get_path(row, ["authoritative_result", "climate_survival"]),
        _get_path(row, ["raw_result", "climate_survival"]),
    ]
    for value in candidates:
        if isinstance(value, dict) and value:
            return value
    return {}


def survival_values(row: Dict[str, Any]) -> Dict[str, Any]:
    climate = climate_survival(row)
    survival = safe_dict(climate.get("survival"))
    if survival:
        return survival
    values = safe_dict(climate.get("values"))
    if values:
        return values
    resources = _first_dict(safe_dict(row), [["player_state", "resources"], ["simulation_state", "player_state", "resources"], ["state", "player_state", "resources"]])
    if resources:
        return resources
    return {}


def resource_changes(row: Dict[str, Any]) -> Dict[str, Any]:
    row = safe_dict(row)
    contract = row_contract(row)
    resolved = resolved_action(row)
    candidates = [
        row.get("resource_changes"),
        contract.get("resource_changes"),
        resolved.get("resource_changes"),
        _get_path(contract, ["resolved_action", "resource_changes"]),
        _get_path(contract, ["resolved_result", "resource_changes"]),
        _get_path(row, ["result", "resource_changes"]),
        _get_path(row, ["result", "turn_contract", "resource_changes"]),
        _get_path(row, ["result", "turn_contract", "resolved_action", "resource_changes"]),
        _get_path(row, ["result", "resolved_action", "resource_changes"]),
        _get_path(row, ["authoritative_result", "resource_changes"]),
        _get_path(row, ["authoritative_result", "turn_contract", "resource_changes"]),
        _get_path(row, ["raw_result", "resource_changes"]),
    ]
    for value in candidates:
        if isinstance(value, dict) and value:
            return value
    return {}


def effect_result(row: Dict[str, Any]) -> Dict[str, Any]:
    row = safe_dict(row)
    contract = row_contract(row)
    resolved = resolved_action(row)
    candidates = [
        row.get("effect_result"),
        contract.get("effect_result"),
        resolved.get("effect_result"),
        _get_path(contract, ["resolved_action", "effect_result"]),
        _get_path(contract, ["resolved_result", "effect_result"]),
        _get_path(row, ["result", "effect_result"]),
        _get_path(row, ["result", "turn_contract", "effect_result"]),
        _get_path(row, ["result", "turn_contract", "resolved_action", "effect_result"]),
        _get_path(row, ["authoritative_result", "effect_result"]),
        _get_path(row, ["raw_result", "effect_result"]),
    ]
    for value in candidates:
        if isinstance(value, dict) and value:
            return value
    return {}


def survival_action(row: Dict[str, Any]) -> Dict[str, Any]:
    row = safe_dict(row)
    contract = row_contract(row)
    resolved = resolved_action(row)
    changes = resource_changes(row)
    candidates = [
        row.get("survival_action"),
        contract.get("survival_action"),
        resolved.get("survival_action"),
        _get_path(contract, ["resolved_action", "survival_action"]),
        _get_path(contract, ["resolved_result", "survival_action"]),
        _get_path(row, ["result", "survival_action"]),
        _get_path(row, ["result", "turn_contract", "survival_action"]),
        _get_path(row, ["authoritative_result", "survival_action"]),
        changes.get("survival_action"),
    ]
    for value in candidates:
        if isinstance(value, dict) and value:
            return value
    return {}


def survival_suggestions(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    row = safe_dict(row)
    contract = row_contract(row)
    presentation = _first_dict(row, [["presentation"], ["result", "presentation"], ["turn_contract", "presentation"]])
    candidates = [
        row.get("survival_suggested_actions"),
        contract.get("survival_suggested_actions"),
        presentation.get("survival_suggested_actions"),
        _get_path(row, ["result", "survival_suggested_actions"]),
        _get_path(row, ["result", "turn_contract", "survival_suggested_actions"]),
    ]
    for value in candidates:
        rows = safe_list(value)
        if rows:
            return [safe_dict(item) for item in rows]
    all_suggestions = safe_list(row.get("suggested_actions") or contract.get("suggested_actions") or presentation.get("available_actions"))
    return [safe_dict(item) for item in all_suggestions if safe_dict(item).get("type") == "survival_relief"]


def warning_types(row: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    survival = survival_values(row)
    warnings.extend(str(item) for item in safe_list(survival.get("warnings")) if item)
    effect = effect_result(row)
    warnings.extend(str(item) for item in safe_list(effect.get("warnings")) if item)
    climate_effect = safe_dict(effect.get("climate_survival"))
    warnings.extend(str(item) for item in safe_list(climate_effect.get("warnings")) if item)
    return sorted(set(warnings))


def _climate_state_has_authoritative_tick_source(climate: Dict[str, Any]) -> bool:
    climate = safe_dict(climate)
    source = _safe_str(climate.get("source"))
    format_version = _safe_str(climate.get("format_version"))
    if source == "deterministic_authoritative_turn_tick":
        return True
    if source == "n1252_projected_resource_change_backed_climate_survival":
        return True
    if source == "n1252_projected_final_transcript_climate_survival":
        return True
    if source == "n1252_projected_turn_contract_climate_survival":
        return True
    if format_version == "n1231_climate_survival_state_v1":
        return True
    if climate.get("runtime_enforced") is True and format_version.startswith("n1231_"):
        return True
    return False


def _climate_has_need_values(climate: Dict[str, Any]) -> bool:
    climate = safe_dict(climate)
    survival = safe_dict(climate.get("survival") or climate.get("values"))
    return all(key in survival for key in ("hunger", "thirst", "fatigue"))


def has_climate_tick_source(row: Dict[str, Any]) -> bool:
    climate = climate_survival(row)
    if _climate_state_has_authoritative_tick_source(climate):
        return True
    changes = resource_changes(row)
    if changes.get("source") == "n1231_climate_survival_tick":
        return True
    climate_changes = safe_dict(changes.get("climate_survival"))
    if climate_changes.get("source") == "n1231_climate_survival_tick":
        return True
    effect = effect_result(row)
    if effect.get("source") == "n1231_climate_survival_tick":
        return True
    if safe_dict(effect.get("climate_survival")).get("source") == "n1231_climate_survival_tick":
        return True
    if climate and changes and _climate_has_need_values(climate):
        return True
    return False


def flat_delta(row: Dict[str, Any], key: str) -> int:
    changes = resource_changes(row)
    if changes.get(key) is not None:
        return safe_int(changes.get(key), 0)
    return safe_int(safe_dict(changes.get("climate_survival")).get(key), 0) + safe_int(safe_dict(changes.get("survival_action")).get(key), 0)


def build_survival_metric_source_summary(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = safe_list(transcript)
    coverage = {
        "row_count": len(rows),
        "climate_survival_rows": 0,
        "resource_change_rows": 0,
        "climate_tick_source_rows": 0,
        "survival_action_rows": 0,
        "survival_suggestion_rows": 0,
        "relief_applied_rows": 0,
        "warning_rows": 0,
        "nonzero_need_rows": 0,
        "nonzero_delta_rows": 0,
    }
    example_missing = []
    for index, row in enumerate(rows, start=1):
        survival = survival_values(row)
        changes = resource_changes(row)
        action = survival_action(row)
        suggestions = survival_suggestions(row)
        warnings = warning_types(row)
        if climate_survival(row):
            coverage["climate_survival_rows"] += 1
        if changes:
            coverage["resource_change_rows"] += 1
        if has_climate_tick_source(row):
            coverage["climate_tick_source_rows"] += 1
        if action:
            coverage["survival_action_rows"] += 1
        if suggestions:
            coverage["survival_suggestion_rows"] += 1
        if action.get("applied"):
            coverage["relief_applied_rows"] += 1
        if warnings:
            coverage["warning_rows"] += 1
        if any(safe_int(survival.get(key), 0) for key in ("hunger", "thirst", "fatigue")):
            coverage["nonzero_need_rows"] += 1
        if any(flat_delta(row, key) for key in ("hunger_delta", "thirst_delta", "fatigue_delta")):
            coverage["nonzero_delta_rows"] += 1
        if len(example_missing) < 5 and climate_survival(row) and not changes:
            example_missing.append({"turn_index": safe_int(row.get("turn_index") or row.get("turn"), index), "missing": "resource_changes"})
    return {
        "format_version": SURVIVAL_METRIC_SOURCE_FORMAT,
        "source": "final_transcript_rows",
        "coverage": coverage,
        "source_coverage_rate": (coverage["climate_tick_source_rows"] / len(rows)) if rows else 0.0,
        "example_missing_source_rows": example_missing,
        "notes": [
            "climate_survival_rows proves values are projected into transcript rows.",
            "climate_tick_source_rows proves authoritative N123.1 tick evidence is measurable from resource_changes/effect_result or persisted climate_survival state.",
            "survival_suggestion_rows and relief_applied_rows prove autoplay response evidence is measurable.",
        ],
    }


def build_survival_metric_source_gate(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = safe_dict(summary)
    coverage = safe_dict(summary.get("coverage"))
    reasons: List[str] = []
    row_count = safe_int(coverage.get("row_count"), 0)
    climate_rows = safe_int(coverage.get("climate_survival_rows"), 0)
    source_rows = safe_int(coverage.get("climate_tick_source_rows"), 0)
    resource_rows = safe_int(coverage.get("resource_change_rows"), 0)
    if row_count <= 0:
        reasons.append("no_transcript_rows")
    if climate_rows <= 0:
        reasons.append("missing_climate_survival_rows")
    if resource_rows <= 0 and source_rows <= 0:
        reasons.append("missing_resource_change_rows")
    if source_rows <= 0:
        reasons.append("missing_climate_tick_source_rows")
    ok = not reasons
    return {
        "gate": "survival_metric_source_ok",
        "ok": ok,
        "advisory_only": True,
        "source": "n1251_survival_metric_source_repair",
        "reasons": reasons,
        "coverage": coverage,
        "message": "Real-run survival metrics must be backed by transcript row source evidence, not only synthetic balance simulation.",
    }


def _longest_capped_streak(rows: List[Dict[str, Any]], need: str, cap: int = 100) -> int:
    longest = 0
    current = 0
    for row in rows:
        if safe_int(row.get(need), 0) >= cap:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _relief_rows_by_need(rows: List[Dict[str, Any]], need: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        kind = _safe_str(row.get("relief_action_kind"))
        applied = bool(row.get("relief_applied"))
        if not applied:
            continue
        if need == "thirst" and kind in {"drink_water", "drink_waterskin", "buy_drink"}:
            out.append(row)
        if need == "hunger" and kind in {"eat_food", "eat_trail_ration", "buy_meal"}:
            out.append(row)
        if need == "fatigue" and kind in {"rest", "sleep", "buy_lodging"}:
            out.append(row)
    return out


def build_survival_balance_summary(trend_rows: List[Dict[str, Any]], inventory_consumed_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = safe_list(trend_rows)
    capped = {need: sum(1 for row in rows if safe_int(safe_dict(row).get(need), 0) >= 100) for need in ("hunger", "thirst", "fatigue")}
    longest = {need: _longest_capped_streak([safe_dict(row) for row in rows], need) for need in ("hunger", "thirst", "fatigue")}
    applied = {need: len(_relief_rows_by_need([safe_dict(row) for row in rows], need)) for need in ("hunger", "thirst", "fatigue")}
    consumed_ids = [_safe_str(safe_dict(item).get("item_id")) for item in safe_list(inventory_consumed_summary)]
    drink_consumed = [item for item in consumed_ids if "water" in item or "drink" in item or "waterskin" in item]
    food_consumed = [item for item in consumed_ids if "ration" in item or "food" in item or "meal" in item]
    thirst_relieved = applied["thirst"] > 0 and bool(drink_consumed)
    hunger_relieved = applied["hunger"] > 0 and bool(food_consumed)
    return {
        "format_version": "n1278_survival_balance_summary_v1",
        "source": BALANCE_SUMMARY_SOURCE,
        "turn_count": len(rows),
        "capped_turn_counts": capped,
        "longest_capped_streaks": longest,
        "applied_relief_counts_by_need": applied,
        "drink_inventory_consumed_count": len(drink_consumed),
        "food_inventory_consumed_count": len(food_consumed),
        "thirst_relieved_by_consumption": thirst_relieved,
        "hunger_relieved_by_consumption": hunger_relieved,
        "thirst_balance_attention": longest.get("thirst", 0) >= 10 or capped.get("thirst", 0) >= 15,
        "notes": [
            "N127.8 keeps this advisory: capped thirst can still be acceptable in stress tests, but it should be visible.",
            "drink/food consumption must be explicit inventory-backed evidence, not simulated-only relief.",
        ],
    }


def build_survival_pressure_relief_summary(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = safe_list(transcript)
    trend_rows: List[Dict[str, Any]] = []
    warnings_by_type: Dict[str, int] = {}
    relief_by_kind: Dict[str, int] = {}
    blocked_by_reason: Dict[str, int] = {}
    pressure_turns = 0
    warning_count = 0
    relief_count = 0
    blocked_count = 0
    final_needs = {"hunger": 0, "thirst": 0, "fatigue": 0}
    net_deltas = {"hunger_delta": 0, "thirst_delta": 0, "fatigue_delta": 0}
    inventory_consumed: Dict[str, Dict[str, Any]] = {}
    service_purchases: Dict[str, Dict[str, Any]] = {}

    for index, row in enumerate(rows, start=1):
        row = safe_dict(row)
        survival = survival_values(row)
        action = survival_action(row)
        changes = resource_changes(row)
        action_changes = safe_dict(action.get("resource_changes")) or safe_dict(changes.get("survival_action"))
        warnings = warning_types(row)
        for warning in warnings:
            warnings_by_type[warning] = warnings_by_type.get(warning, 0) + 1
        warning_count += len(warnings)
        needs = {key: safe_int(survival.get(key), safe_int(row.get(key), 0)) for key in ("hunger", "thirst", "fatigue")}
        final_needs = needs
        deltas = {key: flat_delta(row, key) for key in ("hunger_delta", "thirst_delta", "fatigue_delta")}
        for key, value in deltas.items():
            net_deltas[key] += value
        if has_climate_tick_source(row) or any(value > 0 for value in deltas.values()) or warnings:
            pressure_turns += 1
        if action.get("matched") or action.get("action_kind"):
            kind = str(action.get("action_kind") or action_changes.get("action_kind") or "unknown_survival_action")
            relief_by_kind[kind] = relief_by_kind.get(kind, 0) + 1
            if action.get("applied"):
                relief_count += 1
            if action.get("blocked") or action.get("blocked_reason"):
                blocked_count += 1
                reason = str(action.get("blocked_reason") or action_changes.get("blocked_reason") or "unknown")
                blocked_by_reason[reason] = blocked_by_reason.get(reason, 0) + 1
            consumed = safe_dict(action_changes.get("inventory_consumed") or action.get("inventory_consumed"))
            if consumed.get("consumed"):
                item_id = str(consumed.get("item_id") or consumed.get("name") or "unknown_item")
                bucket = inventory_consumed.setdefault(item_id, {"item_id": item_id, "name": str(consumed.get("name") or item_id), "quantity": 0})
                bucket["quantity"] += max(1, safe_int(consumed.get("quantity"), 1))
            purchase = safe_dict(action_changes.get("purchase") or action.get("purchase"))
            if purchase:
                service_kind = kind.replace("buy_", "") if kind.startswith("buy_") else kind
                bucket = service_purchases.setdefault(service_kind, {"service_kind": service_kind, "count": 0, "blocked_count": 0, "total_price": {"gold": 0, "silver": 0, "copper": 0}})
                bucket["count"] += 1
                if purchase.get("blocked") or purchase.get("blocked_reason") or purchase.get("applied") is False:
                    bucket["blocked_count"] += 1
                price = safe_dict(purchase.get("price"))
                for unit in ("gold", "silver", "copper"):
                    bucket["total_price"][unit] += safe_int(price.get(unit), 0)
        trend_rows.append({
            "turn_index": safe_int(row.get("turn_index") or row.get("turn"), index),
            **needs,
            **deltas,
            "warning_count": len(warnings),
            "warnings": warnings,
            "relief_action_kind": action.get("action_kind") or action_changes.get("action_kind") or "",
            "relief_applied": bool(action.get("applied")),
            "relief_blocked": bool(action.get("blocked") or action.get("blocked_reason")),
            "source_present": has_climate_tick_source(row),
        })
    max_needs = {key: max([safe_int(row.get(key), 0) for row in trend_rows] or [0]) for key in ("hunger", "thirst", "fatigue")}
    source_summary = build_survival_metric_source_summary(rows)
    inventory_summary = sorted(inventory_consumed.values(), key=lambda item: item["item_id"])
    return {
        "format_version": "n1234_survival_pressure_relief_summary_v2_n1251",
        "source": "final_transcript_rows.turn_contract.climate_survival.resource_changes.effect_result.survival_action",
        "turn_count": len(rows),
        "trend_rows": trend_rows,
        "trend_row_count": len(trend_rows),
        "pressure_turn_count": pressure_turns,
        "survival_warning_count": warning_count,
        "warning_counts_by_type": warnings_by_type,
        "relief_action_count": relief_count,
        "relief_counts_by_kind": relief_by_kind,
        "blocked_relief_count": blocked_count,
        "blocked_counts_by_reason": blocked_by_reason,
        "inventory_consumed_summary": inventory_summary,
        "service_relief_purchases_summary": sorted(service_purchases.values(), key=lambda item: item["service_kind"]),
        "net_resource_deltas": net_deltas,
        "max_needs": max_needs,
        "final_needs": final_needs,
        "balance_summary": build_survival_balance_summary(trend_rows, inventory_summary),
        "source_coverage_summary": source_summary,
        "source_gate": build_survival_metric_source_gate(source_summary),
        "artifact_files": {"summary": "survival-pressure-relief-summary.json", "trend_rows": "survival-pressure-trend-rows.json", "source_summary": "survival-metric-source-summary.json"},
        "report_section_title": "N125.1 Real Survival Metric Source Evidence",
    }