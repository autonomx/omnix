from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.rpg.session.survival_metrics import (
    build_survival_metric_source_summary,
    build_survival_pressure_relief_summary,
    climate_survival,
    flat_delta,
    resource_changes,
    safe_dict,
    safe_int,
    safe_list,
    survival_action,
    survival_suggestions,
    survival_values,
)

FORMAT_VERSION = "n1271_survival_autoplay_evidence_summary_v1"
GATE_SOURCE = "n1271_survival_autoplay_evidence"
NEEDS = ("hunger", "thirst", "fatigue")


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _turn_index(row: Dict[str, Any], default: int) -> int:
    return safe_int(row.get("turn_index") or row.get("turn"), default)


def _climate_suggestions(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    climate = climate_survival(row)
    rows = safe_list(climate.get("survival_suggestions")) or safe_list(climate.get("suggestions"))
    if rows:
        return [safe_dict(item) for item in rows if isinstance(item, dict)]
    return []


def _all_suggestions(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = survival_suggestions(row)
    if rows:
        return rows
    return _climate_suggestions(row)


def _action_kind(action: Dict[str, Any]) -> str:
    action = safe_dict(action)
    return _safe_str(action.get("action_kind") or action.get("action") or action.get("kind") or action.get("need"))


def _inventory_consumed_rows(action: Dict[str, Any]) -> List[Dict[str, Any]]:
    action = safe_dict(action)
    candidates = [action.get("inventory_consumed"), safe_dict(action.get("resource_changes")).get("inventory_consumed")]
    rows: List[Dict[str, Any]] = []
    for candidate in candidates:
        if isinstance(candidate, list):
            rows.extend(safe_dict(item) for item in candidate if isinstance(item, dict))
        elif isinstance(candidate, dict) and candidate:
            rows.append(candidate)
    return rows


def _inventory_consumed_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        for item in _inventory_consumed_rows(survival_action(row)):
            if item.get("consumed") is False:
                continue
            item_id = _safe_str(item.get("item_id") or item.get("id") or item.get("name") or "unknown_item")
            name = _safe_str(item.get("name") or item_id)
            quantity = abs(safe_int(item.get("quantity_delta"), 0)) or safe_int(item.get("quantity"), 1) or 1
            bucket = buckets.setdefault(item_id, {"item_id": item_id, "name": name, "quantity": 0})
            bucket["quantity"] += quantity
    return sorted(buckets.values(), key=lambda item: item["item_id"])


def _service_purchase_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        action = survival_action(row)
        action_changes = safe_dict(action.get("resource_changes"))
        purchase = safe_dict(action.get("purchase") or action_changes.get("purchase"))
        if not purchase:
            purchase = safe_dict(safe_dict(resource_changes(row).get("survival_action")).get("purchase"))
        if not purchase:
            continue
        kind = _action_kind(action) or "service_relief"
        if kind.startswith("buy_"):
            kind = kind[4:]
        bucket = buckets.setdefault(kind, {"service_kind": kind, "count": 0, "blocked_count": 0, "total_price": {"gold": 0, "silver": 0, "copper": 0}})
        bucket["count"] += 1
        if purchase.get("blocked") or purchase.get("blocked_reason") or purchase.get("applied") is False:
            bucket["blocked_count"] += 1
        price = safe_dict(purchase.get("price"))
        for unit in ("gold", "silver", "copper"):
            bucket["total_price"][unit] += safe_int(price.get(unit), 0)
    return sorted(buckets.values(), key=lambda item: item["service_kind"])


def _relief_action_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for index, row in enumerate(rows, start=1):
        action = survival_action(row)
        if not action:
            continue
        if action.get("applied") or action.get("matched") or action.get("action_kind") or action.get("action") or action.get("need"):
            result.append({
                "turn_index": _turn_index(row, index),
                "action_kind": _action_kind(action),
                "applied": bool(action.get("applied")),
                "blocked": bool(action.get("blocked") or action.get("blocked_reason")),
                "blocked_reason": _safe_str(action.get("blocked_reason")),
                "inventory_consumed": _inventory_consumed_rows(action),
            })
    return result


def _pressure_response_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        values = survival_values(row)
        if not values and not climate_survival(row):
            continue
        action = survival_action(row)
        suggestions = _all_suggestions(row)
        output.append({
            "turn_index": _turn_index(row, index),
            "needs": {need: safe_int(values.get(need), 0) for need in NEEDS},
            "suggestion_count": len(suggestions),
            "suggestions": suggestions[:5],
            "relief_action_kind": _action_kind(action),
            "relief_applied": bool(action.get("applied")),
            "relief_blocked": bool(action.get("blocked") or action.get("blocked_reason")),
            "resource_deltas": {f"{need}_delta": flat_delta(row, f"{need}_delta") for need in NEEDS},
            "inventory_consumed": _inventory_consumed_rows(action),
        })
    return output


def _carry_forward_evidence(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    examples: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        values = survival_values(row)
        if not values:
            continue
        for need in NEEDS:
            delta = flat_delta(row, f"{need}_delta")
            if delta >= 0:
                continue
            after_value = safe_int(values.get(need), 0)
            before_value = after_value - delta
            if after_value < before_value:
                examples.append({"turn_index": _turn_index(row, index), "need": need, "before_estimate": before_value, "after": after_value, "delta": delta})
                break
        if len(examples) >= 8:
            break
    return {"ok": bool(examples), "example_count": len(examples), "examples": examples}


def _suggestion_row_count(rows: List[Dict[str, Any]]) -> int:
    return sum(1 for row in rows if _all_suggestions(row))


def build_survival_autoplay_evidence_summary(transcript: Iterable[Dict[str, Any]], *, strict: bool = False) -> Dict[str, Any]:
    rows = [safe_dict(row) for row in (transcript if isinstance(transcript, list) else list(transcript or []))]
    source_summary = build_survival_metric_source_summary(rows)
    pressure_summary = build_survival_pressure_relief_summary(rows)
    source_coverage = safe_dict(source_summary.get("coverage"))
    relief_rows = _relief_action_rows(rows)
    consumed = _inventory_consumed_summary(rows) or safe_list(pressure_summary.get("inventory_consumed_summary"))
    service_purchases = _service_purchase_summary(rows) or safe_list(pressure_summary.get("service_relief_purchases_summary"))
    carry = _carry_forward_evidence(rows)
    pressure_rows = _pressure_response_rows(rows)
    suggestion_rows = _suggestion_row_count(rows) or safe_int(source_coverage.get("survival_suggestion_rows"), 0)
    relief_applied_rows = sum(1 for row in relief_rows if row.get("applied")) or safe_int(source_coverage.get("relief_applied_rows"), 0)
    gates = {
        "survival_pressure_seen": safe_int(pressure_summary.get("pressure_turn_count"), 0) > 0 or safe_int(source_coverage.get("climate_survival_rows"), 0) > 0,
        "survival_suggestions_seen": suggestion_rows > 0,
        "survival_relief_actions_seen": relief_applied_rows > 0 or safe_int(pressure_summary.get("relief_action_count"), 0) > 0,
        "survival_inventory_consumed_seen": bool(consumed),
        "survival_state_carry_forward_seen": bool(carry.get("ok")),
    }
    failed = [key for key, value in gates.items() if not value]
    gate = {"gate": "survival_autoplay_evidence_ok", "ok": not failed, "advisory_only": not strict, "source": GATE_SOURCE, "reasons": failed, "gates": gates}
    return {
        "format_version": FORMAT_VERSION,
        "source": "final_transcript_rows.turn_contract.runtime_survival_evidence",
        "strict": bool(strict),
        "ok": bool(gate["ok"]),
        "evidence_gate": gate,
        "gates": gates,
        "failed_gates": failed,
        "turn_count": len(rows),
        "pressure_turn_count": safe_int(pressure_summary.get("pressure_turn_count"), 0),
        "survival_warning_count": safe_int(pressure_summary.get("survival_warning_count"), 0),
        "survival_suggestion_rows": suggestion_rows,
        "relief_action_count": relief_applied_rows or safe_int(pressure_summary.get("relief_action_count"), 0),
        "blocked_relief_count": safe_int(pressure_summary.get("blocked_relief_count"), 0),
        "inventory_consumed_summary": consumed,
        "service_relief_purchases_summary": service_purchases,
        "carry_forward_evidence": carry,
        "net_resource_deltas": safe_dict(pressure_summary.get("net_resource_deltas")),
        "max_needs": safe_dict(pressure_summary.get("max_needs")),
        "final_needs": safe_dict(pressure_summary.get("final_needs")),
        "pressure_response_rows": pressure_rows[:25],
        "relief_action_rows": relief_rows[:25],
        "source_coverage_summary": source_summary,
        "artifact_files": {"summary": "survival-autoplay-evidence-summary.json", "gate": "survival-autoplay-evidence-gate.json", "pressure_response_rows": "survival-autoplay-pressure-response-rows.json"},
    }


def render_survival_autoplay_evidence_report_section(summary: Dict[str, Any]) -> str:
    summary = safe_dict(summary)
    gate = safe_dict(summary.get("evidence_gate"))
    gates = safe_dict(summary.get("gates"))
    consumed = safe_list(summary.get("inventory_consumed_summary"))
    services = safe_list(summary.get("service_relief_purchases_summary"))
    rows = safe_list(summary.get("pressure_response_rows"))[:12]

    def esc(value: Any) -> str:
        text = _safe_str(value)
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    gate_rows = "".join("<tr><td>" + esc(key) + "</td><td>" + ("PASS" if value else "ADVISORY GAP") + "</td></tr>" for key, value in gates.items())
    consumed_rows = "".join("<tr><td>" + esc(item.get("item_id")) + "</td><td>" + esc(item.get("name")) + "</td><td>" + esc(item.get("quantity")) + "</td></tr>" for item in consumed) or "<tr><td colspan='3'>No inventory consumption observed.</td></tr>"
    service_rows = "".join("<tr><td>" + esc(item.get("service_kind")) + "</td><td>" + esc(item.get("count")) + "</td><td>" + esc(item.get("blocked_count")) + "</td></tr>" for item in services) or "<tr><td colspan='3'>No service relief purchases observed.</td></tr>"
    timeline_rows = "".join("<tr><td>" + esc(row.get("turn_index")) + "</td><td>H " + esc(safe_dict(row.get("needs")).get("hunger")) + " / T " + esc(safe_dict(row.get("needs")).get("thirst")) + " / F " + esc(safe_dict(row.get("needs")).get("fatigue")) + "</td><td>" + esc(row.get("suggestion_count")) + "</td><td>" + esc(row.get("relief_action_kind")) + "</td><td>" + ("yes" if row.get("relief_applied") else "no") + "</td></tr>" for row in rows) or "<tr><td colspan='5'>No survival pressure rows observed.</td></tr>"
    return (
        "<section id='n1271-survival-autoplay-evidence'>"
        "<h2>N127.1 Survival Autoplay Evidence</h2>"
        "<p><strong>Evidence gate:</strong> " + ("PASS" if gate.get("ok") else "ADVISORY GAP") + " (advisory=" + esc(gate.get("advisory_only")) + ")</p>"
        "<table><thead><tr><th>Gate</th><th>Status</th></tr></thead><tbody>" + gate_rows + "</tbody></table>"
        "<h3>Pressure to suggestion to response</h3>"
        "<table><thead><tr><th>Turn</th><th>Needs</th><th>Suggestions</th><th>Relief</th><th>Applied</th></tr></thead><tbody>" + timeline_rows + "</tbody></table>"
        "<h3>Inventory consumed</h3><table><thead><tr><th>Item</th><th>Name</th><th>Qty</th></tr></thead><tbody>" + consumed_rows + "</tbody></table>"
        "<h3>Service relief purchases</h3><table><thead><tr><th>Service</th><th>Count</th><th>Blocked</th></tr></thead><tbody>" + service_rows + "</tbody></table>"
        "</section>"
    )
